"""Shared character ID normalization for import scripts."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

# Keep existing YAML filenames for legacy accent slug mismatches.
LEGACY_ID_ALIASES: dict[str, str] = {
    "agnes": "agn-s",
    "agne-s": "agn-s",
    "jose": "jos",
    "throne": "thron",
}


def create_character_id(name: str) -> str:
    """Create a URL-safe ID from a display name (Unicode-aware)."""
    id_str = unicodedata.normalize("NFKD", name)
    id_str = "".join(c for c in id_str if not unicodedata.combining(c))
    id_str = id_str.lower()
    id_str = re.sub(r"[''`]", "", id_str)
    id_str = re.sub(r"[^a-z0-9]+", "-", id_str)
    id_str = re.sub(r"-+", "-", id_str)
    return id_str.strip("-")


def resolve_character_id(name: str) -> str:
    """Return canonical character ID, applying legacy alias overrides."""
    char_id = create_character_id(name)
    return LEGACY_ID_ALIASES.get(char_id, char_id)


def extract_character_name_from_md(filename: str) -> str:
    """Extract character name from Notion markdown filename."""
    return re.sub(r"\s+[a-f0-9]{32}\.md$", "", filename)


def find_default_character_csv(project_root: Path) -> Path | None:
    """
    Locate the newest/largest *_all.csv in resources/Character List/.

    Falls back to resources/Character List all.csv if no nested export exists.
    """
    char_list_dir = project_root / "resources" / "Character List"
    candidates = list(char_list_dir.glob("*_all.csv")) if char_list_dir.exists() else []
    if candidates:
        return max(candidates, key=lambda p: (p.stat().st_size, p.stat().st_mtime))

    fallback = project_root / "resources" / "Character List all.csv"
    return fallback if fallback.exists() else None
