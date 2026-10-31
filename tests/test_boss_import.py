"""Tests for the Adversary Log importer: sheet parsers and --fill-missing merge."""

import csv
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from import_adversary_log_from_csv import (  # noqa: E402
    TODO_STRATEGY,
    AdversaryFight,
    EnemyStats,
    FightVariant,
    find_column_shifts,
    generate_boss_id,
    parse_new_export_file,
    parse_notes_file,
    run_fill_missing,
)


def _write_csv(path: Path, rows: list[list[str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(rows)
    return path


def _enemy(name: str = "Boss", **overrides) -> EnemyStats:
    stats = {
        "level": 75,
        "shields": 30,
        "weaknesses": ["fire", "sword"],
        "hp": 1000,
        "sp": 0,
        "p_atk": 1,
        "p_def": 200,
        "e_atk": 1,
        "e_def": 210,
        "speed": 300,
        "crit": 0,
        "crit_def": 0,
        "equip_atk": 0,
    }
    stats.update(overrides)
    return EnemyStats(name=name, **stats)


def _fight(name: str, source: str = "Sheet A", **variants: EnemyStats) -> AdversaryFight:
    return AdversaryFight(
        fight_name=name,
        level_tier="75",
        is_multi_enemy=False,
        variants={rank: FightVariant(rank=rank, enemies=[e]) for rank, e in variants.items()},
        source=source,
    )


def test_generate_boss_id_folds_to_ascii():
    assert generate_boss_id("９Ｓ？") == "adversary-9s"
    assert generate_boss_id("Kainé?") == "adversary-kaine"
    assert generate_boss_id("Captain Tristan\n&\n2x Mercenary") == (
        "adversary-captain-tristan-2x-mercenary"
    )


def test_parse_new_export_reads_single_and_multi_enemy_blocks(tmp_path):
    rows = [[""] * 20 for _ in range(16)]
    # Single-enemy EX3 block at column 1: shields sit right of the "Notes" column.
    rows[3][1], rows[3][3], rows[5][1] = "Lyblac", "EX3", "Enemy Stats"
    rows[6][2], rows[6][4], rows[12][3] = "Lyblac", "40", "Notes"
    for r, value in zip(range(7, 16), ["5,467,528", "2,398", "644", "3,240", "741", "382"]):
        rows[r][2] = value
    # Multi-enemy Rank 1 block at column 10: enemies are numbered, shields are a table.
    rows[3][10], rows[3][14], rows[5][10] = "Rondo", "Rank 1", "Enemy Stats"
    rows[12][14] = "Notes"
    for col, (number, hp, speed) in zip(
        (11, 12, 13), [("1", "429,120", "271"), ("2", "66,666", "294"), ("3", "66,666", "305")]
    ):
        rows[6][col], rows[7][col], rows[12][col] = number, hp, speed
    for r, (number, shields) in zip((6, 7, 8), [("1", "9"), ("2", "13"), ("3", "11")]):
        rows[r][14], rows[r][15] = number, shields

    lyblac, rondo = parse_new_export_file(_write_csv(tmp_path / "sheet.csv", rows), "75")

    boss = lyblac.variants["ex3"].enemies[0]
    assert (boss.name, boss.hp, boss.shields, boss.speed) == ("Lyblac", 5467528, 40, 382)
    assert (boss.p_atk, boss.p_def, boss.e_atk, boss.e_def) == (2398, 644, 3240, 741)
    assert boss.weaknesses == [] and boss.level == 0

    enemies = rondo.variants["rank1"].enemies
    assert rondo.is_multi_enemy
    assert [e.name for e in enemies] == ["Rondo", "Enemy 2", "Enemy 3"]
    assert [e.shields for e in enemies] == [9, 13, 11]
    assert [e.hp for e in enemies] == [429120, 66666, 66666]


def test_parse_notes_keeps_first_fight_and_nesting(tmp_path):
    path = _write_csv(
        tmp_path / "notes.csv",
        [
            ["By Wigglytuff"],
            ["Fight Name \n(Exactly as in the Adversary Log)", "", "Name"],
            ["Airy", "", "Gains regen\nbelow 50%"],
            ["", "", "", "Pattern does not change"],
            ["Rosso", "", "", "Only a nested note"],
        ],
    )

    assert parse_notes_file(path) == {
        "Airy": ["- Gains regen below 50%", "  - Pattern does not change"],
        "Rosso": ["- Only a nested note"],
    }


CURATED_EX1 = """\
# Hand-curated header comment
id: adversary-boss-ex1
display_name: "Boss EX1"
content_type: adversary_log
difficulty: extreme
base_boss_id: adversary-boss
ex_rank: ex1
speed: 999  # curated, differs from sheet

general_strategy: |
  Curated strategy stays.

recommended_weakness_coverage: []  # No weaknesses parsed

data_source: "Game8 JP"
"""

TODO_BASE = f"""\
id: adversary-boss
display_name: "Boss"
content_type: adversary_log
difficulty: extreme
hp: 1000
general_strategy: |
  {TODO_STRATEGY}
data_source: "Sheet A"
"""

CONFLICTING_EX2 = """\
id: adversary-boss-ex2
display_name: "Boss EX2"
content_type: adversary_log
difficulty: extreme
base_boss_id: adversary-boss
ex_rank: ex2
hp: 5
"""


def test_fill_missing_fills_gaps_without_overwriting(tmp_path):
    (tmp_path / "adversary-boss-ex1.yaml").write_text(CURATED_EX1, encoding="utf-8")
    (tmp_path / "adversary-boss.yaml").write_text(TODO_BASE, encoding="utf-8")
    (tmp_path / "adversary-boss-ex2.yaml").write_text(CONFLICTING_EX2, encoding="utf-8")
    fight = _fight(
        "Boss",
        rank1=_enemy(),
        ex1=_enemy(hp=4000, speed=450),
        ex2=_enemy(hp=6000, shields=0, weaknesses=[]),
    )
    fight.notes = ["- Tip one", "  - Nested tip"]

    run_fill_missing([fight], tmp_path, dry_run=False)

    ex1_text = (tmp_path / "adversary-boss-ex1.yaml").read_text(encoding="utf-8")
    ex1 = yaml.safe_load(ex1_text)
    assert "# Hand-curated header comment" in ex1_text
    assert "speed: 999  # curated, differs from sheet" in ex1_text
    assert ex1["hp"] == 4000 and ex1["shield_count"] == 30 and ex1["level"] == 75
    assert ex1["weaknesses"] == {"elements": ["fire"], "weapons": ["sword"]}
    assert ex1["recommended_weakness_coverage"] == ["sword", "fire"]
    assert ex1["general_strategy"] == "Curated strategy stays.\n"
    assert ex1["data_source"] == "Game8 JP; Sheet A"

    base = yaml.safe_load((tmp_path / "adversary-boss.yaml").read_text(encoding="utf-8"))
    assert base["general_strategy"] == "- Tip one\n  - Nested tip\n"
    assert base["data_source"] == "Sheet A; Community Spreadsheet (Wigglytuff) Fight Notes"

    assert (tmp_path / "adversary-boss-ex2.yaml").read_text(encoding="utf-8") == CONFLICTING_EX2

    snapshot = {p.name: p.read_text(encoding="utf-8") for p in tmp_path.glob("*.yaml")}
    run_fill_missing([fight], tmp_path, dry_run=False)
    assert {p.name: p.read_text(encoding="utf-8") for p in tmp_path.glob("*.yaml")} == snapshot


def test_fill_missing_creates_base_only_when_ex_files_reference_it(tmp_path):
    (tmp_path / "adversary-rondo-ex3.yaml").write_text(
        "id: adversary-rondo-ex3\ndisplay_name: Rondo EX3\ncontent_type: adversary_log\n"
        "difficulty: extreme\nbase_boss_id: adversary-rondo\nex_rank: ex3\nhp: 7\n",
        encoding="utf-8",
    )
    referenced = _fight("Rondo", rank1=_enemy("Rondo", level=0, weaknesses=[]))
    unreferenced = _fight("Stranger", rank1=_enemy("Stranger"))

    run_fill_missing([referenced, unreferenced], tmp_path, dry_run=False)

    base = yaml.safe_load((tmp_path / "adversary-rondo.yaml").read_text(encoding="utf-8"))
    assert (base["hp"], base["shield_count"], base["speed"]) == (1000, 30, 300)
    assert "level" not in base
    assert not (tmp_path / "adversary-stranger.yaml").exists()


def test_find_column_shifts_flags_values_from_another_column_only():
    # Gertrude EX3 row: P.Def 819, E.Atk 4054, Speed 455, Crit 522.
    row = _enemy(hp=9457718, p_def=819, e_atk=4054, speed=455, crit=522, level=120)
    curated = {"hp": 9457718, "speed": 819, "p_def": 4054, "e_atk": 522, "level": 100}

    assert find_column_shifts(curated, row) == {
        "speed": (819, 455, ["p_def"]),
        "p_def": (4054, 819, ["e_atk"]),
        "e_atk": (522, 4054, ["crit"]),
    }


def test_fill_missing_dry_run_writes_nothing(tmp_path):
    (tmp_path / "adversary-boss-ex1.yaml").write_text(CURATED_EX1, encoding="utf-8")

    run_fill_missing([_fight("Boss", ex1=_enemy(hp=4000))], tmp_path, dry_run=True)

    assert (tmp_path / "adversary-boss-ex1.yaml").read_text(encoding="utf-8") == CURATED_EX1
