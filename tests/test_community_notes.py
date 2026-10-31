"""Tests for community note search."""

from pathlib import Path

from src.community_notes import count_character_notes, search_community_notes


def _data_dir(tmp_path: Path) -> Path:
    community = tmp_path / "reference" / "community"
    community.mkdir(parents=True)
    (community / "notes.yaml").write_text(
        "schema_version: '1.0'\n"
        "data_confidence: community_unverified\n"
        "mechanics:\n"
        "  - topic: Ultimate potency does not stack\n"
        "    characters: [aviete, rocbouquet]\n"
        "  - topic: Debuff cap to 50%\n"
        "    characters: [dark-priestess]\n"
        "planning:\n"
        "  rocbouquet-ex: future unit\n",
        encoding="utf-8",
    )
    return tmp_path


def test_search_by_terms_and_character(tmp_path):
    data_dir = _data_dir(tmp_path)

    by_term = search_community_notes(data_dir, terms=["potency", "stack"])
    assert [r["section"] for r in by_term] == ["mechanics[0]"]
    assert by_term[0]["data_confidence"] == "community_unverified"

    by_char = search_community_notes(data_dir, character_id="rocbouquet")
    assert [r["section"] for r in by_char] == ["mechanics[0]"]


def test_character_match_is_whole_id(tmp_path):
    data_dir = _data_dir(tmp_path)
    assert count_character_notes(data_dir, "rocbouquet") == 1
    assert count_character_notes(data_dir, "priestess") == 0
