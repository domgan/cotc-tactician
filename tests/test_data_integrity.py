"""Cross-file integrity checks over the real data/ directory."""

from pathlib import Path

import pytest

from src.data_loader import DataLoader

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def data():
    characters, bosses, teams = DataLoader(DATA_DIR).load_all()
    return {c.id: c for c in characters}, {b.id: b for b in bosses}, {t.id: t for t in teams}


def _data_files(kind: str) -> list[Path]:
    return [p for p in (DATA_DIR / kind).glob("*.yaml") if not p.name.startswith("_")]


@pytest.mark.parametrize("kind", ["characters", "bosses", "teams"])
def test_every_file_loads_and_id_matches_filename(data, kind):
    loaded = dict(zip(["characters", "bosses", "teams"], data, strict=True))[kind]
    assert sorted(loaded) == sorted(p.stem for p in _data_files(kind))


def test_team_bosses_exist(data):
    _, bosses, teams = data
    missing = {t.id: t.boss_id for t in teams.values() if t.boss_id and t.boss_id not in bosses}
    assert not missing


def test_team_character_refs_exist_or_are_declared_unresolved(data):
    characters, _, teams = data
    problems = {}
    for team in teams.values():
        unknown = set(team.character_ids()) - set(characters) - set(team.unresolved_character_ids)
        stale = set(team.unresolved_character_ids) & set(characters)
        if unknown or stale:
            problems[team.id] = {"unknown": sorted(unknown), "now_resolvable": sorted(stale)}
    assert not problems
