"""Tests for character import helpers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from _character_ids import create_character_id, resolve_character_id  # noqa: E402


def test_create_character_id_strips_accents():
    assert create_character_id("Agnès") == "agnes"
    assert create_character_id("José") == "jose"
    assert create_character_id("Throné") == "throne"


def test_resolve_character_id_legacy_aliases():
    assert resolve_character_id("Agnès") == "agn-s"
    assert resolve_character_id("José") == "jos"
    assert resolve_character_id("Throné") == "thron"


def test_support_skills_parser_finds_passives():
    from import_skills_from_markdown import parse_markdown_file

    md_path = (
        Path(__file__).resolve().parent.parent
        / "resources"
        / "Character List"
        / "Aviete 6272a618231982b8b29f011235837ce8.md"
    )
    if not md_path.exists():
        return

    parsed = parse_markdown_file(md_path)
    assert len(parsed["skills"]) > 0
    assert len(parsed["passives"]) > 0
