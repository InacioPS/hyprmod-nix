"""Profile management — self-contained with IPC activate().

Profiles are stored in HYPRMOD_DIR/<profile_id>/ directories. Each
profile's snapshot is whichever format hyprmod was writing at snapshot
time (``.conf`` or ``.lua``); on activation the snapshot is loaded
format-agnostically via :func:`hyprland_config.load_any` and re-written
in the format the user is currently on.
"""

import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

import hyprland_config
from hyprland_config import Assignment, atomic_write, load_any, serialize_any
from hyprland_state import HyprlandState

from hyprmod.core.config import HYPRMOD_DIR, invalidate_cache, managed_path

_PROFILES_DIR = HYPRMOD_DIR / "profiles"
_META_FILE = "meta.json"
_ACTIVE_FILE = HYPRMOD_DIR / "active_profile"

# Profile IDs are 12 hex chars (48 bits) — long enough that collisions are
# astronomically unlikely, short enough that the directory name stays readable.
_PROFILE_ID_LEN = 12


def _profile_dir(profile_id: str) -> Path:
    return _PROFILES_DIR / profile_id


def _read_meta(profile_id: str) -> dict:
    meta_path = _profile_dir(profile_id) / _META_FILE
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"name": profile_id}


def _write_meta(profile_id: str, meta: dict) -> None:
    meta_path = _profile_dir(profile_id) / _META_FILE
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(meta_path, json.dumps(meta, indent=2) + "\n")


def _find_snapshot(profile_id: str) -> Path | None:
    """Return the snapshot inside the profile dir, or ``None`` if absent.

    Looks up the snapshot's filename from the profile's meta (recorded at
    save time). Profiles written before the meta entry existed don't have
    the field; we fall back to a best-effort lookup that prefers the
    active managed-path basename and finally the legacy default name.
    """
    pdir = _profile_dir(profile_id)
    meta = _read_meta(profile_id)
    recorded = meta.get("snapshot")
    if isinstance(recorded, str) and recorded:
        candidate = pdir / recorded
        if candidate.exists():
            return candidate

    # Legacy fallback for profiles created before ``snapshot`` was tracked.
    # TODO: remove after legacy profiles are migrated in the field.
    active = pdir / managed_path().name
    if active.exists():
        return active
    for suffix in (".lua", ".conf"):
        candidate = pdir / f"hyprland-gui{suffix}"
        if candidate.exists():
            return candidate
    return None


def _snapshot_current(pdir: Path) -> str | None:
    """Copy the live managed file into *pdir*, preserving its suffix.

    Returns the snapshot's basename when a copy was made, or ``None`` if
    the managed file is absent. Callers persist the basename in the
    profile meta so :func:`_find_snapshot` can locate it without
    inferring the format from the active mode.
    """
    src = managed_path()
    if not src.exists():
        return None
    pdir.mkdir(parents=True, exist_ok=True)
    atomic_write(pdir / src.name, src.read_text())
    return src.name


def _write_managed_from_snapshot(snapshot: Path) -> None:
    """Write *snapshot* to ``managed_path()``, transcoding format if needed.

    Profiles created in one mode (e.g. Hyprlang) need to survive a switch
    to the other (Lua) — re-emit through the right serializer when the
    suffixes diverge.
    """
    target = managed_path()
    if snapshot.suffix == target.suffix:
        atomic_write(target, snapshot.read_text())
    else:
        atomic_write(target, serialize_any(load_any(snapshot), target))
    invalidate_cache()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def get_active_id() -> str | None:
    """Return the ID of the currently active profile, or ``None``."""
    if _ACTIVE_FILE.exists():
        try:
            return _ACTIVE_FILE.read_text().strip() or None
        except OSError:
            pass
    return None


def set_active_id(profile_id: str | None) -> None:
    """Set (or clear) the active profile ID."""
    _ACTIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(_ACTIVE_FILE, (profile_id or "") + "\n")


def list_profiles_and_active() -> tuple[list[dict], str | None]:
    """Return (profiles_list, active_id).

    Each profile dict has keys: id, name, description, created_at, modified_at.
    """
    profiles = []
    if _PROFILES_DIR.exists():
        for d in sorted(_PROFILES_DIR.iterdir()):
            if d.is_dir() and (d / _META_FILE).exists():
                meta = _read_meta(d.name)
                profiles.append(
                    {
                        "id": d.name,
                        "name": meta.get("name", d.name),
                        "description": meta.get("description", ""),
                        "created_at": meta.get("created_at", ""),
                        "modified_at": meta.get("modified_at", ""),
                    }
                )
    return profiles, get_active_id()


def read_profile_values(profile_id: str) -> dict[str, str]:
    """Read the saved option values for a profile (format-agnostic)."""
    snapshot = _find_snapshot(profile_id)
    if snapshot is None:
        return {}
    try:
        doc = load_any(snapshot, follow_sources=False, lenient=True)
    except (OSError, hyprland_config.ParseError):
        return {}
    return {line.full_key: line.value for line in doc.lines if isinstance(line, Assignment)}


def save_current_as(name: str, description: str = "") -> str:
    """Snapshot the current managed config as a new profile. Returns the profile ID."""
    profile_id = uuid.uuid4().hex[:_PROFILE_ID_LEN]
    snapshot_name = _snapshot_current(_profile_dir(profile_id))
    now = _now_iso()
    meta: dict = {
        "name": name,
        "description": description,
        "created_at": now,
        "modified_at": now,
    }
    if snapshot_name is not None:
        meta["snapshot"] = snapshot_name
    _write_meta(profile_id, meta)
    set_active_id(profile_id)
    return profile_id


def update(profile_id: str) -> None:
    """Update an existing profile with the current config."""
    pdir = _profile_dir(profile_id)
    if not pdir.exists():
        return
    snapshot_name = _snapshot_current(pdir)
    meta = _read_meta(profile_id)
    meta["modified_at"] = _now_iso()
    if snapshot_name is not None:
        meta["snapshot"] = snapshot_name
    _write_meta(profile_id, meta)


def activate_meta(profile_id: str) -> bool:
    """Set a profile as active and write its snapshot to the managed path."""
    snapshot = _find_snapshot(profile_id)
    if snapshot is None:
        return False
    _write_managed_from_snapshot(snapshot)
    set_active_id(profile_id)
    return True


def activate(profile_id: str, hypr: HyprlandState) -> bool:
    """Load a profile: apply all values via IPC, copy to the managed config, reload."""
    values = read_profile_values(profile_id)
    if values:
        hypr.apply_batch(list(values.items()), validate=False)

    if not activate_meta(profile_id):
        return False

    hypr.reload_compositor()
    return True


def delete(profile_id: str) -> None:
    """Delete a profile directory."""
    pdir = _profile_dir(profile_id)
    if pdir.exists():
        shutil.rmtree(pdir)
    if get_active_id() == profile_id:
        set_active_id(None)


def rename(profile_id: str, new_name: str) -> None:
    """Rename a profile (display name only, not the directory)."""
    meta = _read_meta(profile_id)
    meta["name"] = new_name
    _write_meta(profile_id, meta)


def update_description(profile_id: str, description: str) -> None:
    """Update a profile's description."""
    meta = _read_meta(profile_id)
    meta["description"] = description
    _write_meta(profile_id, meta)


def duplicate(profile_id: str) -> str:
    """Duplicate a profile. Returns the new profile ID."""
    meta = _read_meta(profile_id)
    new_id = uuid.uuid4().hex[:_PROFILE_ID_LEN]
    src = _profile_dir(profile_id)
    dst = _profile_dir(new_id)
    if src.exists():
        shutil.copytree(src, dst)
    now = _now_iso()
    new_meta: dict = {
        "name": f"{meta.get('name', 'Untitled')} (copy)",
        "description": meta.get("description", ""),
        "created_at": now,
        "modified_at": now,
    }
    if "snapshot" in meta:
        new_meta["snapshot"] = meta["snapshot"]
    _write_meta(new_id, new_meta)
    return new_id
