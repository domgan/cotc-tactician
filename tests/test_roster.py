"""Tests for player roster load/save and team feasibility scoring."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from src.data_loader import DataLoader
from src.models import PlayerRoster, RosterEntry, Team
from src.roster import (
    battle_skill_slot_count,
    load_roster,
    load_roster_with_meta,
    owned_character_ids,
    resolve_roster,
    resolve_roster_character_ids,
    roster_entry_for_character,
    sanitize_roster_entries,
    save_roster,
    score_team_feasibility,
    sort_teams_by_roster_feasibility,
    upsert_roster_characters,
    validate_character_ids_strict,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture
def roster_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "roster.yaml"
    monkeypatch.setenv("COTC_ROSTER_FILE", str(path))
    return path


@pytest.fixture
def known_ids() -> set[str]:
    loader = DataLoader(DATA_DIR)
    return {c.id for c in loader.load_characters()}


@pytest.fixture
def crickari_team() -> Team:
    loader = DataLoader(DATA_DIR)
    teams = loader.load_teams()
    team = next(t for t in teams if t.id == "adversary-ex3-crickari-f2p")
    return team


def test_save_and_load_round_trip(roster_path: Path, known_ids: set[str]) -> None:
    roster = PlayerRoster(
        characters={
            "solon": RosterEntry(awakening=4, au=True, ult_level=20),
            "phenn": RosterEntry(awakening=1, au=False, ult_level=0),
        }
    )
    save_roster(roster, roster_path, known_ids=known_ids)
    loaded = load_roster(roster_path)
    assert loaded is not None
    assert loaded.characters["solon"].awakening == 4
    assert loaded.characters["solon"].au is True
    assert owned_character_ids(loaded) == ["phenn", "solon"]


def test_lenient_load_drops_unknown_ids(roster_path: Path, known_ids: set[str]) -> None:
    payload = {
        "schema_version": "1.0",
        "characters": {
            "solon": {"awakening": 4, "au": True, "ult_level": 20},
            "rinyu-ex": {"awakening": 0, "au": False, "ult_level": 0},
        },
    }
    roster_path.parent.mkdir(parents=True, exist_ok=True)
    with roster_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f)

    meta = load_roster_with_meta(roster_path, known_ids=known_ids)
    assert meta["owned_count"] == 1
    assert "solon" in meta["characters"]
    assert "rinyu-ex" in meta["skipped_invalid_ids"]


def test_strict_write_rejects_unknown_id(roster_path: Path, known_ids: set[str]) -> None:
    roster = PlayerRoster(characters={"not-a-real-char": RosterEntry()})
    with pytest.raises(ValueError, match="Unknown character"):
        save_roster(roster, roster_path, known_ids=known_ids)


def test_validate_character_ids_strict_suggestion(known_ids: set[str]) -> None:
    _, errors = validate_character_ids_strict(["rinyu-ex"], known_ids)
    assert len(errors) == 1
    assert "Did you mean" in errors[0] or "Unknown character" in errors[0]


def test_score_team_feasibility_full(crickari_team: Team) -> None:
    roster = PlayerRoster(
        characters={
            "hikari-ex": RosterEntry(awakening=4),
            "canary": RosterEntry(awakening=3),
            "sazantos-ex": RosterEntry(awakening=3),
            "billy": RosterEntry(awakening=3),
            "shana": RosterEntry(awakening=3),
            "crick": RosterEntry(awakening=3),
            "eunice": RosterEntry(awakening=2),
            "lynette": RosterEntry(awakening=3),
        }
    )
    score = score_team_feasibility(crickari_team, roster)
    assert score["feasibility"] == "full"
    assert score["owned_count"] == 8
    assert score["investment_gap_count"] == 0


def test_score_team_feasibility_with_owned_substitutes(crickari_team: Team) -> None:
    roster = PlayerRoster(
        characters={
            "hikari": RosterEntry(awakening=4),
            "canary": RosterEntry(awakening=3),
            "sazantos": RosterEntry(awakening=3),
            "billy": RosterEntry(awakening=3),
            "shana": RosterEntry(awakening=3),
            "crick": RosterEntry(awakening=3),
            "eunice": RosterEntry(awakening=2),
            "lynette-ex": RosterEntry(awakening=3),
        }
    )
    score = score_team_feasibility(crickari_team, roster)
    assert score["feasibility"] == "full"
    assert score["owned_count"] == 8
    assert score["has_owned_substitutes"] is True
    assert any(s["use_instead"] == "hikari" for s in score["suggested_substitutions"])


def test_battle_skill_slot_count_by_awakening() -> None:
    assert battle_skill_slot_count(0) == 3
    assert battle_skill_slot_count(1) == 3
    assert battle_skill_slot_count(2) == 4
    assert battle_skill_slot_count(4) == 4


def test_roster_entry_includes_battle_skill_slots() -> None:
    roster = PlayerRoster(characters={"oskha": RosterEntry(awakening=1)})
    entry = roster_entry_for_character(roster, "oskha")
    assert entry is not None
    assert entry["awakening"] == 1
    assert entry["battle_skill_slots"] == 3

    roster.characters["oskha"] = RosterEntry(awakening=2)
    entry = roster_entry_for_character(roster, "oskha")
    assert entry["battle_skill_slots"] == 4


def test_score_team_feasibility_partial(crickari_team: Team) -> None:
    roster = PlayerRoster(
        characters={
            "hikari-ex": RosterEntry(awakening=4),
            "canary": RosterEntry(awakening=3),
            "crick": RosterEntry(awakening=3),
            "shana": RosterEntry(awakening=3),
        }
    )
    score = score_team_feasibility(crickari_team, roster)
    assert score["feasibility"] == "partial"
    assert score["owned_count"] == 4
    assert len(score["missing_characters"]) == 4


def test_score_team_feasibility_unavailable(crickari_team: Team) -> None:
    score = score_team_feasibility(crickari_team, PlayerRoster())
    assert score["feasibility"] == "unavailable"
    assert score["owned_count"] == 0


def test_sort_teams_by_roster_feasibility() -> None:
    scored = [
        {"feasibility": "unavailable", "owned_count": 0, "investment_gap_count": 0,
         "has_owned_substitutes": False, "investment_level": "whale", "team_id": "z"},
        {"feasibility": "full", "owned_count": 8, "investment_gap_count": 0,
         "has_owned_substitutes": False, "investment_level": "low", "team_id": "a"},
        {"feasibility": "partial", "owned_count": 6, "investment_gap_count": 1,
         "has_owned_substitutes": True, "investment_level": "medium", "team_id": "b"},
        {"feasibility": "partial", "owned_count": 5, "investment_gap_count": 0,
         "has_owned_substitutes": False, "investment_level": "low", "team_id": "c"},
    ]
    ordered = sort_teams_by_roster_feasibility(scored)
    assert [s["team_id"] for s in ordered] == ["a", "b", "c", "z"]


def test_resolve_roster_explicit_overrides_file(roster_path: Path, known_ids: set[str]) -> None:
    upsert_roster_characters(
        {"solon": RosterEntry(awakening=4)},
        path=roster_path,
        known_ids=known_ids,
    )
    assert resolve_roster_character_ids(["phenn"], roster_path) == ["phenn"]
    assert resolve_roster_character_ids(None, roster_path) == ["solon"]


def test_resolve_roster_missing_file_returns_none(roster_path: Path) -> None:
    assert resolve_roster_character_ids(None, roster_path) is None


def test_load_roster_sanitizes_with_known_ids(roster_path: Path, known_ids: set[str]) -> None:
    payload = {
        "schema_version": "1.0",
        "characters": {
            "solon": {"awakening": 4, "au": True, "ult_level": 20},
            "rinyu-ex": {"awakening": 0, "au": False, "ult_level": 0},
        },
    }
    roster_path.parent.mkdir(parents=True, exist_ok=True)
    with roster_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f)

    roster = load_roster(roster_path, known_ids=known_ids)
    assert roster is not None
    assert "solon" in roster.characters
    assert "rinyu-ex" not in roster.characters


def test_resolve_roster_single_disk_read(roster_path: Path, known_ids: set[str]) -> None:
    upsert_roster_characters(
        {"solon": RosterEntry(awakening=4)},
        path=roster_path,
        known_ids=known_ids,
    )
    call_count = 0
    original = load_roster

    def counting_load(path=None, known_ids=None):
        nonlocal call_count
        call_count += 1
        return original(path, known_ids)

    with patch("src.roster.load_roster", side_effect=counting_load):
        ids, roster = resolve_roster(None, roster_path, known_ids=known_ids)
    assert ids == ["solon"]
    assert roster is not None
    assert call_count == 1


def test_resolve_roster_fresh_read_no_cache(roster_path: Path, known_ids: set[str]) -> None:
    call_count = 0
    original = load_roster

    def counting_load(path=None, known_ids=None):
        nonlocal call_count
        call_count += 1
        return original(path, known_ids)

    with patch("src.roster.load_roster", side_effect=counting_load):
        resolve_roster(None, roster_path, known_ids=known_ids)
        resolve_roster(None, roster_path, known_ids=known_ids)
    assert call_count == 2


def test_sanitize_roster_entries(known_ids: set[str]) -> None:
    roster = PlayerRoster(
        characters={
            "solon": RosterEntry(awakening=4),
            "bad-id": RosterEntry(),
        }
    )
    cleaned, skipped = sanitize_roster_entries(roster, known_ids)
    assert skipped == ["bad-id"]
    assert "solon" in cleaned.characters
    assert "bad-id" not in cleaned.characters
