"""Cross-file integrity checks over the real data/ directory."""

import re
import sys
from pathlib import Path

import pytest

from src.data_loader import DataLoader
from src.models import Character

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from import_skills_from_markdown import split_sentences  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
AGENT_CURATED = "Kit-derived (agent"
STAT_PATTERNS = [
    ("atk", r"Atk"),
    ("def", r"Def"),
    ("res", r"Res"),
    ("damage", r"damage"),
    ("potency", r"potency"),
    ("crit", r"Crit|critical"),
]


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


def _kit_sentences(char: Character) -> list[str]:
    texts = []
    for skill in char.skills:
        texts += [
            *skill.effects,
            *skill.upgrades,
            skill.limit_break_upgrade or "",
            skill.notes or "",
        ]
    for passive in char.passives:
        texts += [passive.effect, *passive.upgrades, passive.limit_break_upgrade or ""]
    if char.a4_accessory:
        texts.append(char.a4_accessory.passive_effect)
    return [s for text in texts if text for s in split_sentences(text)]


def _supported(entry_type: str, value: int, sentences: list[str], debuff: bool) -> bool:
    stat = next((rx for key, rx in STAT_PATTERNS if key in entry_type), None)
    verb = r"lower|down|reduce|inflict" if debuff else r"raise|up|grant|impart|increase|augment"
    return any(
        re.search(rf"(?<!\d){value}%", s)
        and (stat is None or re.search(stat, s, re.IGNORECASE))
        and re.search(verb, s, re.IGNORECASE)
        for s in sentences
    )


def test_agent_curated_categories_are_backed_by_kit_text(data):
    characters, _, _ = data
    unsupported = []
    for char in characters.values():
        if AGENT_CURATED not in (char.role_notes or ""):
            continue
        sentences = _kit_sentences(char)
        for debuff, categories in ((False, char.buff_categories), (True, char.debuff_categories)):
            if categories is None:
                continue
            for bucket, entries in categories.model_dump().items():
                for entry in entries:
                    if not _supported(entry["type"], entry["value"], sentences, debuff):
                        unsupported.append((char.id, bucket, entry["type"], entry["value"]))
    assert not unsupported


def test_tank_type_implies_tank_role(data):
    characters, _, _ = data
    mismatched = [
        c.id
        for c in characters.values()
        if c.tank_type and c.tank_type.value != "none" and "tank" not in {r.value for r in c.roles}
    ]
    assert not mismatched
