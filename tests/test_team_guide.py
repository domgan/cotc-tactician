"""Tests for team building guide loader."""

from pathlib import Path

from src.team_guide import _load_llm_guidelines_yaml, load_team_building_guide

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def test_load_team_building_guide_includes_signa_and_cecil():
    guide = load_team_building_guide(DATA_DIR)
    debuffer_picks = guide["role_priorities"]["debuffer"]["top_picks"]
    assert debuffer_picks[0] == "signa"
    assert "signa" in debuffer_picks

    tank_ex_notes = guide["role_priorities"]["tank"]["ex_notes"]
    assert "cecil" in tank_ex_notes.lower()
    assert "fiore-ex" in guide["role_priorities"]["tank"]["top_picks"]


def test_load_team_building_guide_cached():
    _load_llm_guidelines_yaml.cache_clear()
    load_team_building_guide(DATA_DIR)
    info_after_first = _load_llm_guidelines_yaml.cache_info()
    load_team_building_guide(DATA_DIR)
    info_after_second = _load_llm_guidelines_yaml.cache_info()

    assert info_after_first.misses == 1
    assert info_after_second.hits == 1
    assert info_after_second.misses == 1

    _load_llm_guidelines_yaml.cache_clear()
