"""HyprMod application entry point."""

import signal
import sys
from pathlib import Path

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from hyprmod.constants import APPLICATION_ID
from hyprmod.core.setup import needs_setup, run_setup
from hyprmod.ui import try_with_toast
from hyprmod.ui.onboarding_dialog import OnboardingDialog
from hyprmod.window import HyprModWindow


class HyprModApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id=APPLICATION_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )

    def do_startup(self):
        Adw.Application.do_startup(self)
        icon_dir = str(Path(__file__).resolve().parent / "data" / "icons")
        display = Gdk.Display.get_default()
        if display is not None:
            theme = Gtk.IconTheme.get_for_display(display)
            paths = theme.get_search_path() or []
            theme.set_search_path([icon_dir, *paths])

    def do_activate(self):
        win = self.props.active_window
        if not isinstance(win, HyprModWindow):
            win = HyprModWindow(application=self)

        if needs_setup():
            window = win  # locally typed for the closure below

            def _on_setup() -> None:
                try_with_toast(window.show_toast, "Setup failed", run_setup)

            OnboardingDialog(on_setup=_on_setup).present(win)

        win.present()


def main():
    app = HyprModApp()

    # Route SIGINT/SIGTERM through the GLib main loop so Ctrl-C from the
    # terminal (or `kill`) shuts the app down cleanly. Python's default
    # SIGINT handler can't interrupt GLib's C-level loop — the exception
    # only surfaces when control next returns to Python, which typically
    # produces a stray traceback after the UI has already been frozen.
    def _on_signal(*_args) -> bool:
        app.quit()
        return GLib.SOURCE_REMOVE

    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, _on_signal)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, _on_signal)

    return app.run(sys.argv)


if __name__ == "__main__":
    main()
