"""Lua-mode integration tests.

Hyprland 0.55.0 made Lua the default config language. When the user has
``~/.config/hypr/hyprland.lua`` present, hyprmod must:

- Write its managed file as ``hyprland-gui.lua`` (not ``.conf``).
- Inject ``dofile("…")`` into ``hyprland.lua`` during first-run setup
  instead of ``source = …`` into ``hyprland.conf``.
"""

from types import SimpleNamespace

import pytest
from hyprland_config import load_lua

from hyprmod.core import config, setup


@pytest.fixture
def lua_mode(tmp_path, monkeypatch):
    """Simulate a Lua-mode Hyprland setup rooted in *tmp_path*."""
    hypr_dir = tmp_path / "hypr"
    hypr_dir.mkdir()
    user_lua = hypr_dir / "hyprland.lua"
    user_conf = hypr_dir / "hyprland.conf"
    managed_base = hypr_dir / "hyprland-gui"
    user_lua.touch()  # presence flips Lua mode on

    # Both ``config.is_lua_mode`` and ``setup`` lookups go through
    # ``hyprland_config.default_lua_entrypoint`` / ``default_hyprlang_entrypoint``,
    # so redirecting the config-dir helper is enough.
    def _config_dir():
        return hypr_dir

    monkeypatch.setattr("hyprland_config.default_config_dir", _config_dir)
    # The default-entrypoint helpers re-read default_config_dir at call
    # time, so they pick up the override automatically.
    config.set_managed_path(managed_base)
    yield SimpleNamespace(
        user_lua=user_lua,
        user_conf=user_conf,
        managed_conf=managed_base.with_suffix(".conf"),
        managed_lua=managed_base.with_suffix(".lua"),
    )
    config.set_managed_path(None)


@pytest.fixture
def hyprlang_mode(tmp_path, monkeypatch):
    """Simulate a legacy Hyprlang setup (hyprland.conf only, no hyprland.lua)."""
    hypr_dir = tmp_path / "hypr"
    hypr_dir.mkdir()
    user_lua = hypr_dir / "hyprland.lua"  # deliberately not created
    user_conf = hypr_dir / "hyprland.conf"
    managed_base = hypr_dir / "hyprland-gui"
    user_conf.write_text("# user main config\n")

    def _config_dir():
        return hypr_dir

    monkeypatch.setattr("hyprland_config.default_config_dir", _config_dir)
    config.set_managed_path(managed_base)
    yield SimpleNamespace(
        user_lua=user_lua,
        user_conf=user_conf,
        managed_conf=managed_base.with_suffix(".conf"),
        managed_lua=managed_base.with_suffix(".lua"),
    )
    config.set_managed_path(None)


class TestIsLuaMode:
    def test_present_hyprland_lua_means_lua_mode(self, lua_mode) -> None:
        assert config.is_lua_mode() is True

    def test_absent_hyprland_lua_means_hyprlang_mode(self, hyprlang_mode) -> None:
        assert config.is_lua_mode() is False


class TestSupportsLuaMigration:
    """Gate the migration banner by running-Hyprland version.

    The Lua parser only exists from 0.55.0 onwards; offering migration
    on anything older would point the converter at a compositor that
    can't load the result.
    """

    def test_055_supported(self) -> None:
        assert config.supports_lua_migration("0.55.0") is True

    def test_newer_supported(self) -> None:
        assert config.supports_lua_migration("0.56.0") is True
        assert config.supports_lua_migration("1.0.0") is True

    def test_v_prefix_accepted(self) -> None:
        assert config.supports_lua_migration("v0.55.0") is True

    def test_054_unsupported(self) -> None:
        assert config.supports_lua_migration("0.54.3") is False
        assert config.supports_lua_migration("0.54.0") is False

    def test_pre_055_majors_unsupported(self) -> None:
        assert config.supports_lua_migration("0.50.0") is False
        assert config.supports_lua_migration("0.42.0") is False

    def test_none_or_empty_unsupported(self) -> None:
        assert config.supports_lua_migration(None) is False
        assert config.supports_lua_migration("") is False

    def test_malformed_unsupported(self) -> None:
        assert config.supports_lua_migration("not-a-version") is False
        assert config.supports_lua_migration("0.55.x") is False


class TestWriteAll:
    def test_lua_mode_writes_only_lua(self, lua_mode) -> None:
        config.write_all({"general:gaps_in": "5"}, config.ConfigSections())
        assert lua_mode.managed_lua.exists()
        assert not lua_mode.managed_conf.exists(), (
            "Lua-only path: no .conf sidecar should be written in Lua mode"
        )

    def test_hyprlang_mode_writes_only_conf(self, hyprlang_mode) -> None:
        config.write_all({"general:gaps_in": "5"}, config.ConfigSections())
        assert hyprlang_mode.managed_conf.exists()
        assert not hyprlang_mode.managed_lua.exists()

    def test_lua_output_contains_hl_config_call(self, lua_mode) -> None:
        config.write_all({"general:gaps_in": "5"}, config.ConfigSections())
        out = lua_mode.managed_lua.read_text()
        assert "hl.config(" in out
        assert "gaps_in = 5" in out

    def test_lua_output_translates_env_keyword(self, lua_mode) -> None:
        config.write_all({}, config.ConfigSections(env=["env = XCURSOR_SIZE, 24\n"]))
        out = lua_mode.managed_lua.read_text()
        assert 'hl.env("XCURSOR_SIZE", "24")' in out

    def test_lua_output_translates_bind_keyword(self, lua_mode) -> None:
        config.write_all({}, config.ConfigSections(binds=["bind = SUPER, Q, killactive,\n"]))
        out = lua_mode.managed_lua.read_text()
        assert 'hl.bind("SUPER + Q"' in out
        assert "hl.dsp.window.close()" in out

    def test_lua_output_regenerated_on_each_save(self, lua_mode) -> None:
        config.write_all({"general:gaps_in": "5"}, config.ConfigSections())
        config.write_all({"general:gaps_in": "10"}, config.ConfigSections())
        out = lua_mode.managed_lua.read_text()
        assert "gaps_in = 10" in out
        assert "gaps_in = 5" not in out


class TestReadAllSectionsRoundTrip:
    """Saved Lua → read_all_sections returns the same shape as Hyprlang would."""

    def test_lua_round_trip_options(self, lua_mode) -> None:
        config.write_all({"general:gaps_in": "5"}, config.ConfigSections())
        options, _sections, _rules = config.read_all_sections()
        assert options.get("general:gaps_in") == "5"

    def test_lua_round_trip_keyword_section(self, lua_mode) -> None:
        config.write_all({}, config.ConfigSections(env=["env = XCURSOR_SIZE, 24\n"]))
        _options, sections, _rules = config.read_all_sections()
        # Lua reader synthesises Hyprlang-style raw lines, so the
        # collected env section matches what we'd see in Hyprlang mode.
        env_lines = sections.get("env", [])
        assert any("XCURSOR_SIZE" in line for line in env_lines)


class TestRunSetup:
    def test_lua_mode_appends_dofile_to_hyprland_lua(self, lua_mode) -> None:
        lua_mode.user_lua.write_text("-- existing user content\n")
        setup.run_setup()
        out = lua_mode.user_lua.read_text()
        assert "-- existing user content" in out
        assert f'dofile("{lua_mode.managed_lua}")' in out
        assert "# HyprMod managed settings" not in out, (
            "Lua entrypoint must use Lua-style `--` comments, not Hyprlang `#`"
        )

    def test_lua_mode_does_not_touch_hyprland_conf(self, lua_mode) -> None:
        setup.run_setup()
        assert not lua_mode.user_conf.exists()

    def test_hyprlang_mode_appends_source_to_hyprland_conf(self, hyprlang_mode) -> None:
        setup.run_setup()
        out = hyprlang_mode.user_conf.read_text()
        assert f"source = {hyprlang_mode.managed_conf}" in out

    def test_hyprlang_mode_does_not_touch_hyprland_lua(self, hyprlang_mode) -> None:
        setup.run_setup()
        assert not hyprlang_mode.user_lua.exists()

    def test_idempotent_in_lua_mode(self, lua_mode) -> None:
        setup.run_setup()
        first = lua_mode.user_lua.read_text()
        setup.run_setup()
        assert lua_mode.user_lua.read_text() == first

    def test_idempotent_in_hyprlang_mode(self, hyprlang_mode) -> None:
        setup.run_setup()
        first = hyprlang_mode.user_conf.read_text()
        setup.run_setup()
        assert hyprlang_mode.user_conf.read_text() == first


class TestNeedsSetup:
    def test_returns_true_when_lua_mode_missing_dofile(self, lua_mode) -> None:
        assert setup.needs_setup() is True

    def test_returns_false_after_run_setup_in_lua_mode(self, lua_mode) -> None:
        setup.run_setup()
        assert setup.needs_setup() is False

    def test_returns_true_when_hyprlang_mode_missing_source(self, hyprlang_mode) -> None:
        assert setup.needs_setup() is True

    def test_returns_false_after_run_setup_in_hyprlang_mode(self, hyprlang_mode) -> None:
        setup.run_setup()
        assert setup.needs_setup() is False

    def test_dofile_through_symlink_is_recognised(self, lua_mode, tmp_path) -> None:
        # Symlinked dotfile repos: a dofile written against one path must
        # match managed_lua_path() pointed at the other path when both
        # resolve to the same file.
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        real_lua = real_dir / "hyprland-gui.lua"
        real_lua.write_text("")
        symlink = lua_mode.user_lua.parent / "hyprland-gui-symlinked.lua"
        symlink.symlink_to(real_lua)

        config.set_managed_path(symlink)
        assert config.managed_lua_path() == symlink

        lua_mode.user_lua.write_text(f'dofile("{real_lua}")\n')
        assert setup.needs_setup() is False, (
            "dofile() through the resolved path must match managed_lua_path() "
            "through the symlink — both refer to the same file"
        )


class TestLoadLuaReaderError:
    """LuaReaderError now inherits from ParseError — confirm one ``except`` catches both."""

    def test_lua_reader_error_caught_as_parse_error(self) -> None:
        from hyprland_config import LuaReaderError, ParseError

        assert issubclass(LuaReaderError, ParseError)
        with pytest.raises(ParseError):
            load_lua("/nonexistent/path/to/hyprland.lua")


class TestLuaReplacementForStoredPath:
    """Helper that repoints a stored .conf config-path at its .lua sibling.

    Used by the Lua-migration wizard to fix users whose ``config-path``
    GSetting is locked to a .conf file the post-migration Hyprland never
    loads.
    """

    def test_swaps_when_lua_sibling_was_written(self, tmp_path) -> None:
        stored = tmp_path / "gui" / "managed.conf"
        lua = stored.with_suffix(".lua")
        assert config.lua_replacement_for_stored_path(str(stored), [lua]) == str(lua)

    def test_no_swap_when_stored_is_empty(self, tmp_path) -> None:
        lua = tmp_path / "managed.lua"
        # Empty *stored* means "use default" — the mode-driven suffix
        # already handles the transition, nothing to repoint.
        assert config.lua_replacement_for_stored_path("", [lua]) is None

    def test_no_swap_when_stored_is_already_lua(self, tmp_path) -> None:
        stored = tmp_path / "managed.lua"
        assert config.lua_replacement_for_stored_path(str(stored), [stored]) is None

    def test_no_swap_when_lua_sibling_not_in_written(self, tmp_path) -> None:
        stored = tmp_path / "managed.conf"
        other = tmp_path / "unrelated.lua"
        # The converter didn't produce our .lua — we'd be pointing at a
        # phantom file. Bail out and let the user fix it manually.
        assert config.lua_replacement_for_stored_path(str(stored), [other]) is None

    def test_no_swap_when_written_is_empty(self, tmp_path) -> None:
        stored = tmp_path / "managed.conf"
        assert config.lua_replacement_for_stored_path(str(stored), []) is None

    def test_expands_tilde_in_stored_path(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        lua = tmp_path / "managed.lua"
        assert config.lua_replacement_for_stored_path("~/managed.conf", [lua]) == str(lua)


class TestEnsureManagedPathMatchesMode:
    """Startup repoint when the user switched Hyprland config language out-of-band.

    Covers the failure mode where a custom ``config-path`` GSetting was
    set under one config language and the user later switched Hyprland
    to the other — hyprmod would otherwise silently write the wrong
    format to a file the live compositor never loads.
    """

    def test_swaps_when_lua_sibling_exists(self, lua_mode, tmp_path) -> None:
        stored = tmp_path / "managed.conf"
        stored.write_text("general {\n  gaps_in = 5\n}\n")
        lua = stored.with_suffix(".lua")
        lua.write_text("-- pre-existing lua\n")
        result = config.ensure_managed_path_matches_mode(str(stored))
        assert result == str(lua)
        # Existing .lua wins — we don't overwrite a sibling the user
        # already converted (possibly with edits we don't know about).
        assert lua.read_text() == "-- pre-existing lua\n"

    def test_converts_conf_when_no_lua_sibling(self, lua_mode, tmp_path) -> None:
        stored = tmp_path / "managed.conf"
        stored.write_text("general {\n  gaps_in = 5\n}\n")
        lua = stored.with_suffix(".lua")
        result = config.ensure_managed_path_matches_mode(str(stored))
        assert result == str(lua)
        # Conversion ran: .lua now exists with Lua syntax derived from
        # the .conf content, .conf is left as-is for the user to clean
        # up on their own terms.
        assert lua.exists()
        lua_text = lua.read_text()
        assert "hl.config(" in lua_text
        assert "gaps_in = 5" in lua_text
        assert stored.exists()

    def test_returns_lua_path_when_neither_exists(self, lua_mode, tmp_path) -> None:
        stored = tmp_path / "managed.conf"
        lua = stored.with_suffix(".lua")
        # Nothing to convert, but still need to repoint so the next
        # write_all() lands on .lua instead of .conf.
        result = config.ensure_managed_path_matches_mode(str(stored))
        assert result == str(lua)
        assert not lua.exists()

    def test_no_op_when_suffix_already_matches_lua_mode(self, lua_mode, tmp_path) -> None:
        stored = tmp_path / "managed.lua"
        stored.write_text("")
        assert config.ensure_managed_path_matches_mode(str(stored)) is None

    def test_no_op_when_stored_is_empty(self, lua_mode) -> None:
        # Empty stored means "use default" — mode-driven suffix already
        # adapts via managed_path(), nothing to repoint.
        assert config.ensure_managed_path_matches_mode("") is None

    def test_no_op_for_unmanaged_suffix(self, lua_mode, tmp_path) -> None:
        stored = tmp_path / "managed.txt"
        stored.write_text("")
        # Not a managed suffix — don't touch paths we don't recognise.
        assert config.ensure_managed_path_matches_mode(str(stored)) is None

    def test_reverse_direction_converts_lua_to_conf(self, hyprlang_mode, tmp_path) -> None:
        # Symmetric case: user reverts to Hyprlang (deletes hyprland.lua)
        # while config-path still points at a .lua managed file.
        stored = tmp_path / "managed.lua"
        stored.write_text("hl.config({general = {gaps_in = 5}})\n")
        conf = stored.with_suffix(".conf")
        result = config.ensure_managed_path_matches_mode(str(stored))
        assert result == str(conf)
        assert conf.exists()
        assert "gaps_in = 5" in conf.read_text()

    def test_expands_tilde_in_stored_path(self, lua_mode, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        stored = tmp_path / "managed.conf"
        stored.write_text("")
        lua = tmp_path / "managed.lua"
        assert config.ensure_managed_path_matches_mode("~/managed.conf") == str(lua)

    def test_bails_without_repointing_on_conversion_failure(
        self, lua_mode, tmp_path, monkeypatch
    ) -> None:
        # Simulate an unreadable .conf by making atomic_write raise.
        # Pre-existing user data lives in .conf — better to keep
        # writing there (broken-but-recoverable) than to silently
        # repoint at a half-written or empty .lua.
        stored = tmp_path / "managed.conf"
        stored.write_text("general {\n  gaps_in = 5\n}\n")
        lua = stored.with_suffix(".lua")

        def boom(*_args, **_kwargs):
            raise OSError("disk full")

        monkeypatch.setattr("hyprmod.core.config.atomic_write", boom)
        assert config.ensure_managed_path_matches_mode(str(stored)) is None
        assert not lua.exists()


class TestMigrationActionable:
    """Shared gate for the Lua-migration banner and menu action.

    Both UI surfaces hide themselves on pre-0.55 Hyprland or when the
    user is already in Lua mode — the wizard has nothing useful to do.
    The dismissed-banner flag intentionally lives outside this gate so
    the menu action stays reachable after the user dismisses the banner.
    """

    def test_actionable_in_hyprlang_mode_on_055(self, hyprlang_mode) -> None:
        from hyprmod.ui.lua_migration_controller import _migration_actionable

        assert _migration_actionable("0.55.0") is True

    def test_actionable_in_hyprlang_mode_on_newer(self, hyprlang_mode) -> None:
        from hyprmod.ui.lua_migration_controller import _migration_actionable

        assert _migration_actionable("0.56.0") is True

    def test_not_actionable_in_lua_mode(self, lua_mode) -> None:
        from hyprmod.ui.lua_migration_controller import _migration_actionable

        # User is already on Lua — the wizard refuses to run, action
        # should be greyed out.
        assert _migration_actionable("0.55.0") is False

    def test_not_actionable_on_pre_055(self, hyprlang_mode) -> None:
        from hyprmod.ui.lua_migration_controller import _migration_actionable

        assert _migration_actionable("0.54.0") is False

    def test_not_actionable_on_unknown_version(self, hyprlang_mode) -> None:
        from hyprmod.ui.lua_migration_controller import _migration_actionable

        assert _migration_actionable(None) is False
        assert _migration_actionable("") is False
