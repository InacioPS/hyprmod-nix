"""First-run setup — inject the include line into the user's top-level config."""

import re
import shutil
from pathlib import Path

from hyprland_config import Source, atomic_write, load, serialize_hyprlang

from hyprmod.core import config

# Matches a literal ``dofile("...")`` or ``dofile('...')`` call. We don't
# pretend to parse Lua — the entrypoint file is tiny and any dofile line
# the user or wizard cares about is written by us, so the literal form is
# enough. Resolution is path-based, not string-based, so the regex only
# has to *find* the candidate target.
_DOFILE_RE = re.compile(r"""dofile\s*\(\s*['"]([^'"]+)['"]\s*\)""")


def needs_setup() -> bool:
    """Return ``True`` when the user's entrypoint still needs our include line."""
    entry = config.user_entry_path()
    if not entry.exists():
        return False
    if config.is_lua_target(entry):
        return not _has_dofile(entry.read_text(encoding="utf-8"), config.managed_lua_path())
    doc = load(entry, follow_sources=False)
    return _find_source_node(doc, config.managed_conf_path()) is None


def run_setup() -> None:
    """Append our include line to the user's top-level config.

    In Lua mode: ensure ``managed_lua_path()`` exists, then append
    ``dofile("…")`` to ``hyprland.lua``. In Hyprlang mode: ensure
    ``managed_conf_path()`` exists, then append ``source = …`` to
    ``hyprland.conf``.
    """
    entry = config.user_entry_path()
    if config.is_lua_target(entry):
        target = config.managed_lua_path()
        target.touch(exist_ok=True)
        _append_lua_include(entry, target)
        return

    target = config.managed_conf_path()
    target.touch(exist_ok=True)
    doc = load(entry, follow_sources=False)
    if _find_source_node(doc, target) is not None:
        return
    content = serialize_hyprlang(doc)
    if content and not content.endswith("\n"):
        content += "\n"
    content += f"\n# HyprMod managed settings\nsource = {target}\n"
    atomic_write(entry, content)


def _append_lua_include(entry: Path, target: Path) -> None:
    """Append ``dofile("...")`` to *entry* if it's not already present."""
    existing = entry.read_text(encoding="utf-8") if entry.exists() else ""
    if _has_dofile(existing, target):
        return
    if existing and not existing.endswith("\n"):
        existing += "\n"
    existing += f'\n-- HyprMod managed settings\ndofile("{target}")\n'
    atomic_write(entry, existing)


def _has_dofile(text: str, target: Path) -> bool:
    """Return ``True`` when *text* contains a ``dofile()`` pointing at *target*.

    Path comparison goes through ``.resolve()`` so symlinked-dotfile setups
    (``~/.config/hypr → ~/dotfiles/hypr``) match either spelling. Lines
    where ``--`` appears before the ``dofile`` token are treated as
    commented out — handles both standalone ``-- dofile("...")`` and
    trailing ``code() -- dofile("...")``.
    """
    resolved_target = target.resolve()
    for line in text.splitlines():
        dofile_at = line.find("dofile")
        if dofile_at == -1:
            continue
        comment_at = line.find("--")
        if comment_at != -1 and comment_at < dofile_at:
            continue
        for match in _DOFILE_RE.finditer(line):
            if Path(match.group(1)).expanduser().resolve() == resolved_target:
                return True
    return False


def _find_source_node(doc, target: Path) -> Source | None:
    """Find the Source node in *doc* that resolves to *target*."""
    resolved = target.resolve()
    for line in doc.lines:
        if isinstance(line, Source) and Path(line.path_str).expanduser().resolve() == resolved:
            return line
    return None


def migrate_config_path(old_path: Path, new_path: Path) -> None:
    """Move the managed file and update the include line in the user's entrypoint.

    The user's entrypoint format decides which include statement is
    rewritten — Lua entrypoints get their ``dofile("…")`` updated,
    Hyprlang entrypoints get their ``source = …`` updated. *old_path*
    and *new_path* are the literal paths from the caller; their suffix
    should match the active mode so the rewritten include points at a
    file Hyprland can actually load.
    """
    new_path.parent.mkdir(parents=True, exist_ok=True)
    if old_path.exists():
        shutil.move(old_path, new_path)

    entry = config.user_entry_path()
    if not entry.exists():
        return

    if config.is_lua_target(entry):
        _migrate_lua_dofile(entry, old_path, new_path)
    else:
        _migrate_hyprlang_source(entry, old_path, new_path)


def _migrate_hyprlang_source(entry: Path, old_path: Path, new_path: Path) -> None:
    doc = load(entry, follow_sources=False)
    old_node = _find_source_node(doc, old_path)
    if old_node is not None:
        new_raw = old_node.raw.replace(str(old_path), str(new_path))
        if new_raw == old_node.raw:
            new_raw = f"source = {new_path}\n"
        content = serialize_hyprlang(doc).replace(old_node.raw, new_raw, 1)
        atomic_write(entry, content)
    elif _find_source_node(doc, new_path) is None:
        content = serialize_hyprlang(doc)
        if content and not content.endswith("\n"):
            content += "\n"
        content += f"\n# HyprMod managed settings\nsource = {new_path}\n"
        atomic_write(entry, content)


def _migrate_lua_dofile(entry: Path, old_path: Path, new_path: Path) -> None:
    existing = entry.read_text(encoding="utf-8")
    resolved_old = old_path.resolve()
    updated = existing
    changed = False
    for match in _DOFILE_RE.finditer(existing):
        candidate = Path(match.group(1)).expanduser().resolve()
        if candidate == resolved_old:
            updated = updated.replace(match.group(0), f'dofile("{new_path}")', 1)
            changed = True
    if changed:
        atomic_write(entry, updated)
    elif not _has_dofile(existing, new_path):
        if updated and not updated.endswith("\n"):
            updated += "\n"
        updated += f'\n-- HyprMod managed settings\ndofile("{new_path}")\n'
        atomic_write(entry, updated)
