"""
Search community-sourced notes in data/reference/community/*.yaml.

Files differ in layout, so each top-level section is split into units (list items or
dict children) and matched as YAML text. Everything returned is community_unverified.
"""

import re
from pathlib import Path

import yaml

META_KEYS = {"schema_version", "data_confidence", "last_updated"}
MAX_TEXT = 2000


def _units(data: dict) -> list[tuple[str, object]]:
    units: list[tuple[str, object]] = []
    for key, value in data.items():
        if key in META_KEYS:
            continue
        if isinstance(value, list):
            units.extend((f"{key}[{i}]", item) for i, item in enumerate(value))
        elif isinstance(value, dict):
            units.extend((f"{key}.{sub}", item) for sub, item in value.items())
        else:
            units.append((key, value))
    return units


def _load_units(data_dir: Path) -> list[dict]:
    loaded = []
    for path in sorted((data_dir / "reference" / "community").glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for section, value in _units(data):
            text = yaml.safe_dump(value, sort_keys=False, allow_unicode=True, width=120)
            loaded.append({"file": path.name, "section": section, "text": text})
    return loaded


def _mentions(text: str, character_id: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(character_id)}(?![\w-])", text) is not None


def search_community_notes(
    data_dir: Path,
    terms: list[str] | None = None,
    character_id: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Units matching every term (case-insensitive regex) and mentioning character_id."""
    patterns = []
    for term in terms or []:
        try:
            patterns.append(re.compile(term, re.IGNORECASE))
        except re.error:
            patterns.append(re.compile(re.escape(term), re.IGNORECASE))

    results = []
    for unit in _load_units(data_dir):
        text = unit["text"]
        if character_id and not _mentions(text, character_id):
            continue
        if not all(p.search(text) for p in patterns):
            continue
        clipped = text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "\n[truncated]"
        results.append({**unit, "text": clipped, "data_confidence": "community_unverified"})
    return results[:limit]


def count_character_notes(data_dir: Path, character_id: str) -> int:
    return sum(1 for unit in _load_units(data_dir) if _mentions(unit["text"], character_id))
