"""Application-wide constants shared across modules.

Pulling these into one module avoids hard-coded duplication across
``main``, ``window``, ``ui.about``, the window-rule self-target gate,
and the GSettings schema.
"""

# HyprMod's Flatpak-style application id. Must stay in sync with:
# - ``data/applications/io.github.bluemancz.hyprmod.desktop`` (Icon,
#   StartupWMClass, file basename).
# - ``data/metainfo/io.github.bluemancz.hyprmod.metainfo.xml``.
# - ``hyprmod/data/io.github.bluemancz.hyprmod.gschema.xml`` (schema id +
#   path-derived directory).
# It doubles as the GSettings schema id and the value Hyprland reports
# as ``class`` for our window (used by :func:`matches_hyprmod` to gate
# self-targeting window rules behind a confirmation dialog).
APPLICATION_ID: str = "io.github.bluemancz.hyprmod"
