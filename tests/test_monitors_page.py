"""Tests for MonitorsPage state behaviour that doesn't require the GTK UI to be built."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from hyprland_monitors import MonitorState
from hyprland_monitors.monitors import lines_from_monitors

from hyprmod.core import config
from hyprmod.pages.monitors.page import MonitorsPage


def _make_monitor(name: str, description: str = "") -> MonitorState:
    return MonitorState(
        name=name,
        make="Acme",
        model="Pixel",
        width=1920,
        height=1080,
        refresh_rate=60.0,
        x=0,
        y=0,
        scale=1.0,
        description=description,
    )


def _make_window(get_all_results: list[list[MonitorState]]) -> SimpleNamespace:
    """Build a minimal window stub that returns successive monitor lists from IPC."""
    monitors = MagicMock()
    monitors.get_all.side_effect = get_all_results
    monitors.apply.return_value = True
    hypr = SimpleNamespace(monitors=monitors, on_change=MagicMock(), document=None)
    # Pages now read managed sections through ``window.saved_sections``
    # rather than re-parsing per call; mirror that by reading once here.
    _, saved_sections, _rules = config.read_all_sections()
    return SimpleNamespace(
        hypr=hypr,
        show_toast=MagicMock(),
        show_bug_toast=MagicMock(),
        saved_sections=saved_sections,
    )


class TestRefreshAfterPortChange:
    """Regression: refreshing after a desc-tracked monitor moved to a new port
    must not show phantom pending changes.

    The bug: ``_on_refresh`` reloaded ``self._monitors`` (with the new port name)
    and rebuilt ownership against the new port — but ``_saved_monitors`` still
    held the snapshot taken at the *old* port. ``is_dirty()`` filtered the
    snapshot by the new ownership and got an empty list, falsely flagging the
    monitor as dirty.
    """

    def test_no_phantom_dirty_after_refresh_with_new_port(self, gui_conf_tmp):
        gui_conf_tmp.write_text(
            "monitor = desc:Acme Pixel 5000, 1920x1080@60.00Hz, 0x0, 1\n",
            encoding="utf-8",
        )
        window = _make_window(
            [
                [_make_monitor("DP-1", "Acme Pixel 5000 SN12345")],  # initial load
                [_make_monitor("HDMI-A-1", "Acme Pixel 5000 SN12345")],  # after refresh
            ],
        )
        page = MonitorsPage(window)
        assert page.is_dirty() is False

        page._on_refresh(None)

        assert page.is_dirty() is False

    def test_port_form_clean_after_refresh(self, gui_conf_tmp):
        # Sanity check: same scenario but with port-form saved config and matching IPC.
        gui_conf_tmp.write_text(
            "monitor = DP-1, 1920x1080@60.00Hz, 0x0, 1\n",
            encoding="utf-8",
        )
        window = _make_window(
            [
                [_make_monitor("DP-1", "Acme Pixel 5000")],
                [_make_monitor("DP-1", "Acme Pixel 5000")],
            ],
        )
        page = MonitorsPage(window)
        assert page.is_dirty() is False
        page._on_refresh(None)
        assert page.is_dirty() is False


@pytest.fixture
def page_with_monitors(gui_conf_tmp):
    """Build a MonitorsPage seeded with a saved-config file and IPC reads."""

    def _factory(saved_text: str, ipc_reads: list[list[MonitorState]]) -> MonitorsPage:
        gui_conf_tmp.write_text(saved_text, encoding="utf-8")
        window = _make_window(ipc_reads)
        return MonitorsPage(window)

    return _factory


class TestDescIdentifierResolution:
    """End-to-end: desc-form saved lines resolve to the live connector after a port change."""

    def test_desc_resolves_to_new_port_on_initial_load(self, page_with_monitors):
        page = page_with_monitors(
            "monitor = desc:Acme Pixel 5000, 1920x1080@60.00Hz, 0x0, 1\n",
            [[_make_monitor("HDMI-A-1", "Acme Pixel 5000 SN12345")]],
        )
        # Ownership is keyed by the live connector — desc: resolved to HDMI-A-1.
        assert page._ownership.is_owned("HDMI-A-1")
        # The toggle is restored from the saved line.
        assert page._monitors[0].identify_by_description is True


class TestRefreshPreservesPendingEdits:
    """Refreshing must not silently drop unsaved monitor edits or the dirty flag.

    ``_on_refresh`` re-reads live IPC and re-applies the saved config (which
    flattens extra fields and resets ownership). It used to then re-snapshot the
    baseline, adopting the edited live state as "saved" and clearing dirty. Now
    pending edits are captured and layered back on, and the baseline is kept.
    """

    def test_resolution_edit_survives_refresh(self, page_with_monitors):
        page = page_with_monitors(
            "monitor = DP-1, 1920x1080@60.00Hz, 0x0, 1\n",
            # Second IPC read reflects the applied change, as a live apply would.
            [
                [_make_monitor("DP-1", "Acme Pixel 5000")],
                [_make_monitor("DP-1", "Acme Pixel 5000")],
            ],
        )
        assert page.is_dirty() is False

        # Simulate an applied resolution change (what _apply_change leaves behind).
        mon = page._monitors[0]
        mon.width, mon.height, mon.mode = 2560, 1440, None
        page._ownership.own("DP-1")
        assert page.is_dirty() is True

        page._on_refresh(None)

        assert page.is_dirty() is True
        assert (page._monitors[0].width, page._monitors[0].height) == (2560, 1440)

    def test_extra_field_edit_survives_refresh(self, page_with_monitors):
        # vrr is the tricky case: IPC reports it as a bool, so the reload can't
        # recover the user's "2" — it must come from the captured pending edit.
        page = page_with_monitors(
            "monitor = DP-1, 1920x1080@60.00Hz, 0x0, 1\n",
            [
                [_make_monitor("DP-1", "Acme Pixel 5000")],
                [_make_monitor("DP-1", "Acme Pixel 5000")],
            ],
        )
        mon = page._monitors[0]
        mon.vrr = "2"
        page._ownership.own("DP-1")
        assert page.is_dirty() is True

        page._on_refresh(None)

        assert page._monitors[0].vrr == "2"
        assert page.is_dirty() is True

    def test_added_monitor_survives_refresh(self, page_with_monitors):
        # A monitor the user started managing (not in saved config) must stay
        # owned and dirty across a refresh.
        page = page_with_monitors(
            "",
            [
                [_make_monitor("DP-1", "Acme Pixel 5000")],
                [_make_monitor("DP-1", "Acme Pixel 5000")],
            ],
        )
        mon = page._monitors[0]
        mon.scale = 1.25
        page._ownership.own("DP-1")
        assert page.is_dirty() is True

        page._on_refresh(None)

        assert page._ownership.is_owned("DP-1") is True
        assert page.is_dirty() is True


class TestHdrExtras:
    def test_new_luminance_fields_round_trip(self, page_with_monitors):
        page = page_with_monitors(
            "monitor = DP-1, 1920x1080@60.00Hz, 0x0, 1, "
            "cm, hdr, sdr_min_luminance, 0.3, sdr_max_luminance, 120, "
            "min_luminance, 0.01, max_luminance, 1000, max_avg_luminance, 400\n",
            [[_make_monitor("DP-1", "Acme Pixel 5000")]],
        )

        mon = page._monitors[0]
        assert mon.sdr_min_luminance == "0.3"
        assert mon.sdr_max_luminance == "120"
        assert mon.min_luminance == "0.01"
        assert mon.max_luminance == "1000"
        assert mon.max_avg_luminance == "400"
        assert page.is_dirty() is False
        assert "sdr_min_luminance, 0.3" in lines_from_monitors([mon])[0]
