"""Tests for workspace-rule parsing, serialization, and summarisation.

Workspace rules use ``workspace = SELECTOR, key:value, …`` — a selector
(numeric / named / range / per-monitor / special) followed by zero or
more ``key:value`` overrides. All 13 fields documented by Hyprland round
trip through the model; unknown tokens survive via the ``extra`` list so
plugin / future-Hyprland fields aren't lost on edit.
"""

from hyprmod.core import config
from hyprmod.core.workspaces import (
    WORKSPACE_RULE_KEYWORDS,
    WorkspaceRule,
    parse_workspace_rule_body,
    parse_workspace_rule_lines,
    serialize,
    summarize_rule,
    summarize_selector,
    summarize_settings,
)

# ---------------------------------------------------------------------------
# Selector parsing
# ---------------------------------------------------------------------------


class TestParseSelector:
    """The selector token (first CSV item) is preserved verbatim."""

    def test_numeric(self) -> None:
        rule = parse_workspace_rule_body("1, monitor:DP-1")
        assert rule is not None
        assert rule.workspace == "1"

    def test_named(self) -> None:
        rule = parse_workspace_rule_body("name:work, monitor:DP-1")
        assert rule is not None
        assert rule.workspace == "name:work"

    def test_special(self) -> None:
        rule = parse_workspace_rule_body("special:scratchpad, on-created-empty:kitty")
        assert rule is not None
        assert rule.workspace == "special:scratchpad"

    def test_range(self) -> None:
        rule = parse_workspace_rule_body("r[1-10], gapsin:5")
        assert rule is not None
        assert rule.workspace == "r[1-10]"

    def test_per_monitor(self) -> None:
        rule = parse_workspace_rule_body("m[1-3], persistent:true")
        assert rule is not None
        assert rule.workspace == "m[1-3]"

    def test_empty_body_returns_none(self) -> None:
        assert parse_workspace_rule_body("") is None
        assert parse_workspace_rule_body("   ") is None


# ---------------------------------------------------------------------------
# Field parsing — one case per field type
# ---------------------------------------------------------------------------


class TestParseFields:
    def test_monitor(self) -> None:
        rule = parse_workspace_rule_body("1, monitor:DP-1")
        assert rule is not None and rule.monitor == "DP-1"

    def test_default(self) -> None:
        rule = parse_workspace_rule_body("1, default:true")
        assert rule is not None and rule.default is True

    def test_persistent(self) -> None:
        rule = parse_workspace_rule_body("1, persistent:true")
        assert rule is not None and rule.persistent is True

    def test_gaps_scalar(self) -> None:
        rule = parse_workspace_rule_body("1, gapsin:5")
        assert rule is not None and rule.gaps_in == 5

    def test_gaps_four_value(self) -> None:
        rule = parse_workspace_rule_body("1, gapsout:5 10 15 20")
        assert rule is not None
        assert rule.gaps_out == (5, 10, 15, 20)

    def test_gaps_two_value_css_shorthand(self) -> None:
        # 2 values: vertical, horizontal.
        rule = parse_workspace_rule_body("1, gapsin:5 10")
        assert rule is not None
        assert rule.gaps_in == (5, 10, 5, 10)

    def test_gaps_three_value_css_shorthand(self) -> None:
        # 3 values: top, horizontal, bottom.
        rule = parse_workspace_rule_body("1, gapsin:5 10 15")
        assert rule is not None
        assert rule.gaps_in == (5, 10, 15, 10)

    def test_border_size(self) -> None:
        rule = parse_workspace_rule_body("1, bordersize:3")
        assert rule is not None and rule.border_size == 3

    def test_border_false(self) -> None:
        # Hyprlang positive sense — model stays positive too.
        rule = parse_workspace_rule_body("1, border:false")
        assert rule is not None and rule.border is False

    def test_rounding_true(self) -> None:
        rule = parse_workspace_rule_body("1, rounding:true")
        assert rule is not None and rule.rounding is True

    def test_shadow_false(self) -> None:
        rule = parse_workspace_rule_body("1, shadow:false")
        assert rule is not None and rule.shadow is False

    def test_decorate(self) -> None:
        rule = parse_workspace_rule_body("1, decorate:false")
        assert rule is not None and rule.decorate is False

    def test_default_name(self) -> None:
        rule = parse_workspace_rule_body("1, defaultName:work")
        assert rule is not None and rule.default_name == "work"

    def test_on_created_empty(self) -> None:
        rule = parse_workspace_rule_body("1, on-created-empty:kitty")
        assert rule is not None and rule.on_created_empty == "kitty"

    def test_unknown_field_passes_through_extra(self) -> None:
        # Plugin / future-Hyprland fields survive a round-trip via the
        # ``extra`` list — we don't know how to surface them but we
        # also don't drop them.
        rule = parse_workspace_rule_body("1, plugin_field:42")
        assert rule is not None
        assert "plugin_field:42" in rule.extra


# ---------------------------------------------------------------------------
# Round-trip stability
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_full_field_round_trip(self) -> None:
        source = (
            "workspace = 1, monitor:DP-2, default:true, persistent:true, "
            "gapsin:5 10 5 10, gapsout:0, bordersize:2, border:false, "
            "rounding:false, shadow:true, decorate:false, defaultName:work, "
            "on-created-empty:kitty"
        )
        rules = parse_workspace_rule_lines([source])
        assert len(rules) == 1
        # Re-serialising must contain every field; order is fixed by the
        # catalogue so we can compare byte-for-byte.
        rebuilt = serialize(rules)[0]
        # ``extra`` slot stays empty for known fields → exact match.
        for token in [
            "monitor:DP-2",
            "default:true",
            "persistent:true",
            "gapsin:5 10 5 10",
            "gapsout:0",
            "bordersize:2",
            "border:false",
            "rounding:false",
            "shadow:true",
            "decorate:false",
            "defaultName:work",
            "on-created-empty:kitty",
        ]:
            assert token in rebuilt, f"{token!r} missing from re-serialised line:\n{rebuilt}"

    def test_empty_rule_serialises_to_selector_only(self) -> None:
        rule = WorkspaceRule(workspace="1")
        assert rule.body() == "1"
        assert rule.to_line() == "workspace = 1"

    def test_unknown_field_preserved_through_round_trip(self) -> None:
        rules = parse_workspace_rule_lines(["workspace = 1, plugin_field:42"])
        assert len(rules) == 1
        rebuilt = serialize(rules)[0]
        assert "plugin_field:42" in rebuilt

    def test_parse_skips_non_workspace_lines(self) -> None:
        # Anything that isn't ``workspace = …`` should be silently ignored.
        rules = parse_workspace_rule_lines(
            [
                "workspace = 1, monitor:DP-1",
                "monitor = DP-1, preferred, auto, 1",  # different keyword
                "windowrule = float, class:^firefox$",  # different keyword
            ]
        )
        assert len(rules) == 1
        assert rules[0].workspace == "1"


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------


class TestSummaries:
    def test_numeric_selector_title(self) -> None:
        rule = WorkspaceRule(workspace="1", monitor="DP-1", default=True)
        assert summarize_selector(rule) == "Workspace 1"

    def test_named_selector_title(self) -> None:
        rule = WorkspaceRule(workspace="name:work")
        assert summarize_selector(rule) == "Named workspace “work”"

    def test_special_selector_title(self) -> None:
        rule = WorkspaceRule(workspace="special:scratchpad")
        assert summarize_selector(rule) == "Special workspace “scratchpad”"

    def test_range_selector_title_uses_verbatim_form(self) -> None:
        rule = WorkspaceRule(workspace="r[1-10]")
        assert summarize_selector(rule) == "Workspace r[1-10]"

    def test_empty_rule_subtitle(self) -> None:
        rule = WorkspaceRule(workspace="1")
        assert summarize_settings(rule) == "(no overrides)"

    def test_subtitle_includes_monitor_and_default(self) -> None:
        rule = WorkspaceRule(workspace="1", monitor="DP-1", default=True)
        assert "on DP-1" in summarize_settings(rule)
        assert "default" in summarize_settings(rule)

    def test_subtitle_includes_negated_decoration_only_when_false(self) -> None:
        # ``border = True`` is the default; only ``False`` (override) is noisy
        # enough to surface in a compact subtitle.
        on_rule = WorkspaceRule(workspace="1", border=True)
        off_rule = WorkspaceRule(workspace="1", border=False)
        assert "no border" not in summarize_settings(on_rule)
        assert "no border" in summarize_settings(off_rule)

    def test_summarize_rule_returns_pair(self) -> None:
        rule = WorkspaceRule(workspace="1", monitor="DP-1", default=True)
        title, subtitle = summarize_rule(rule)
        assert title == "Workspace 1"
        assert "DP-1" in subtitle


# ---------------------------------------------------------------------------
# Config-section integration
# ---------------------------------------------------------------------------


class TestSectionIntegration:
    def test_keyword_registered(self) -> None:
        assert config.KEYWORD_WORKSPACE == "workspace"
        assert config.KEYWORD_WORKSPACE in WORKSPACE_RULE_KEYWORDS

    def test_managed_section_detection(self) -> None:
        # Verify the workspace keyword is in hyprmod's managed-keyword
        # catalogue so ``read_all_sections`` collects it like the others.
        from hyprmod.core.config import _is_managed_keyword

        assert _is_managed_keyword(config.KEYWORD_WORKSPACE)
