"""Shared helpers for loading external (read-only) keyword entries.

These loaders are advisory UI data only: any load/parse failure degrades to
an empty list instead of surfacing an error to users.
"""

from dataclasses import dataclass
from pathlib import Path

import hyprland_config


@dataclass(frozen=True, slots=True)
class ExternalKeywordEntry:
    """One keyword occurrence from outside hyprmod's managed config file."""

    key: str
    value: str
    source_path: Path
    lineno: int


def load_external_keyword_entries(
    root_path: Path,
    managed_path: Path,
    keywords: tuple[str, ...],
    *,
    migrate_doc: bool = False,
) -> list[ExternalKeywordEntry]:
    """Load keyword entries from *root_path* + sources, excluding *managed_path*.

    Set ``migrate_doc=True`` when callers need ``hyprland_config.migrate`` to
    normalize deprecated syntax before parsing individual lines.
    """
    if not root_path.exists():
        return []
    try:
        doc = hyprland_config.load_any(root_path, follow_sources=True, lenient=True)
    except (OSError, hyprland_config.ParseError, hyprland_config.SourceCycleError):
        return []

    if migrate_doc:
        hyprland_config.migrate(doc)

    managed_str = str(managed_path)
    external: list[ExternalKeywordEntry] = []
    for keyword in keywords:
        for entry in doc.find_all(keyword):
            if entry.source_name == managed_str:
                continue
            external.append(
                ExternalKeywordEntry(
                    key=entry.key,
                    value=entry.value,
                    source_path=Path(entry.source_name),
                    lineno=entry.lineno,
                )
            )
    return external
