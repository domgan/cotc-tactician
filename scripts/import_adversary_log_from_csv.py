#!/usr/bin/env python3
"""
Import Adversary Log boss data from CSV files.

This script parses the community spreadsheet CSV exports and generates
YAML boss files for the COTC Tactician database.

CRITICAL: Each EX variant gets its OWN YAML file for RAG indexing!
  - adversary-boss-name.yaml       (Base with Rank 1-3)
  - adversary-boss-name-ex1.yaml   (EX1 variant)
  - adversary-boss-name-ex2.yaml   (EX2 variant)
  - adversary-boss-name-ex3.yaml   (EX3 variant)

Sources:
- resources/Adversary Log/ (one row per rank, includes weaknesses):
  - EN OT_ COTC _ Adversary Log Enemy Index - Lv. X~.csv (stats)
  - EN OT_ COTC _ Adversary Log Enemy Index - Fights coming on October 2nd.csv (stats)
  - EN OT_ COTC _ Adversary Log Enemy Index - Lv. X~ Fight Notes.csv (tips)
- resources/Adversary Log New/ (one column block per fight, EX3 or Rank 1 only).
  Weakness icons do not survive the CSV export, so this source never provides
  weaknesses. The 120 NPCs sheet has no rank labels and is not read.

Modes:
- default: create files that do not exist yet (Adversary Log sources only).
- --overwrite: regenerate existing files.
- --fill-missing: fill empty fields of existing files from every source without
  overwriting curated values. A file is skipped when its HP or shield count
  contradicts the source. A base file is created only when EX files reference
  it and the sources contain its Rank 1 stats.

Usage:
    python scripts/import_adversary_log_from_csv.py
    python scripts/import_adversary_log_from_csv.py --dry-run
    python scripts/import_adversary_log_from_csv.py --overwrite
    python scripts/import_adversary_log_from_csv.py --fill-missing --dry-run
"""

import argparse
import csv
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

LEGACY_DIR = "Adversary Log"
NEW_EXPORT_DIR = "Adversary Log New"
LEGACY_PREFIX = "EN OT_ COTC _ Adversary Log Enemy Index - "
NEW_EXPORT_PREFIX = "Adversary Log CotC - "

LEGACY_STATS_FILES = [
    ("Lv. 1~", "1"),
    ("Lv. 25~", "25"),
    ("Lv. 50~", "50"),
    ("Lv. 75~", "75"),
    ("Fights coming on October 2nd", "75"),
]
LEGACY_NOTES_FILES = ["Lv. 1~ Fight Notes", "Lv. 50~ Fight Notes", "Lv. 75~ Fight Notes"]
NEW_EXPORT_FILES = [
    ("Lvl 1", "1"),
    ("Lvl 25", "25"),
    ("Lvl 50", "50"),
    ("Lvl 75", "75"),
    ("Solistia Lvl 1", "1"),
    ("Solistia Lvl 25", "25"),
    ("Solistia Lvl 50", "50"),
    ("Solistia Lvl 75", "75"),
]

LEGACY_SOURCE = "Community Spreadsheet (Wigglytuff)"
NEW_EXPORT_SOURCE = "Adversary Log New spreadsheet"
NOTES_SOURCE = "Community Spreadsheet (Wigglytuff) Fight Notes"

TODO_STRATEGY = "TODO: Add strategy notes for this fight."
ELEMENTS = ["fire", "ice", "lightning", "wind", "light", "dark"]
WEAPONS = ["sword", "polearm", "dagger", "axe", "bow", "staff", "tome", "fan"]
RANKS = ("rank1", "rank2", "rank3", "ex1", "ex2", "ex3")
EX_RANKS = ("ex1", "ex2", "ex3")
STAT_FIELDS = ("level", "shield_count", "hp", "speed", "p_atk", "p_def", "e_atk", "e_def")
SHEET_COLUMNS = (*STAT_FIELDS, "sp", "crit", "crit_def", "equip_atk")
# Stats the Boss model reads; p_atk/e_atk are written by the generators but not loaded.
FILL_FIELDS = ("level", "shield_count", "hp", "speed", "p_def", "e_def")
# Keys after which missing stat lines are inserted, in order of preference.
STAT_ANCHORS = (
    "e_def",
    "p_def",
    "e_atk",
    "p_atk",
    "speed",
    "hp",
    "shield_count",
    "level",
    "provoke_immunity",
    "actions_per_turn",
    "ex_rank",
    "base_boss_id",
    "location",
    "difficulty",
    "content_type",
    "display_name",
    "id",
)
STRATEGY_ANCHORS = ("required_roles", "recommended_weakness_coverage", "data_confidence")
COVERAGE_ANCHORS = ("data_confidence", "data_source", "last_updated")

# Row offsets inside a New export column block.
NEW_TITLE_ROW = 3
NEW_HEADER_ROW = 5
NEW_NAME_ROW = 6
NEW_STAT_ROWS = {
    "hp": 7,
    "p_atk": 8,
    "p_def": 9,
    "e_atk": 10,
    "e_def": 11,
    "speed": 12,
    "crit": 13,
    "crit_def": 14,
    "equip_atk": 15,
}


@dataclass
class EnemyStats:
    """Stats for a single enemy at a specific rank."""

    name: str
    level: int
    shields: int
    weaknesses: list[str]
    hp: int
    sp: int
    p_atk: int
    p_def: int
    e_atk: int
    e_def: int
    speed: int
    crit: int
    crit_def: int
    equip_atk: int
    weaknesses_rotate: bool = False

    @property
    def shield_count(self) -> int:
        return self.shields


@dataclass
class FightVariant:
    """A single fight variant (Rank 1, 2, 3, EX1, EX2, EX3)."""

    rank: str  # "rank1", "rank2", "rank3", "ex1", "ex2", "ex3"
    enemies: list[EnemyStats] = field(default_factory=list)


@dataclass
class AdversaryFight:
    """An Adversary Log fight with all variants."""

    fight_name: str
    level_tier: str  # "1", "25", "50", "75"
    is_multi_enemy: bool
    variants: dict[str, FightVariant] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    source: str = LEGACY_SOURCE


def parse_weakness_string(weakness_str: str) -> list[str]:
    """Parse weakness string into list of weakness types."""
    if not weakness_str or weakness_str.lower() == "none":
        return []

    # Normalize names
    weakness_map = {
        "sword": "sword",
        "spear": "polearm",
        "polearm": "polearm",
        "dagger": "dagger",
        "axe": "axe",
        "bow": "bow",
        "staff": "staff",
        "tome": "tome",
        "fan": "fan",
        "fire": "fire",
        "ice": "ice",
        "lightning": "lightning",
        "wind": "wind",
        "light": "light",
        "dark": "dark",
    }

    # Handle multi-line weakness strings (weakness cycling)
    # Just take the first set for now
    first_line = weakness_str.split("\n")[0].strip()

    # Split by spaces
    parts = first_line.lower().split()

    weaknesses = []
    for part in parts:
        part = part.strip()
        if part in weakness_map:
            weaknesses.append(weakness_map[part])

    return weaknesses


def parse_int_safe(val: str) -> int:
    """Safely parse integer, returning 0 on failure."""
    if not val:
        return 0
    try:
        # Remove commas and other formatting
        val = val.replace(",", "").strip()
        return int(float(val))
    except (ValueError, TypeError):
        return 0


def parse_shields(val: str) -> int:
    """Parse shield count, handling special cases like '9 -> 12'."""
    if not val:
        return 0
    # Take first number if there's a range
    match = re.search(r"(\d+)", val)
    if match:
        return int(match.group(1))
    return 0


def normalize_rank(rank_str: str) -> str:
    """Normalize rank string to standard format."""
    rank_str = rank_str.strip().lower()
    if "rank 1" in rank_str or rank_str == "rank1":
        return "rank1"
    if "rank 2" in rank_str or rank_str == "rank2":
        return "rank2"
    if "rank 3" in rank_str or rank_str == "rank3":
        return "rank3"
    if "ex1" in rank_str or "ex 1" in rank_str:
        return "ex1"
    if "ex2" in rank_str or "ex 2" in rank_str:
        return "ex2"
    if "ex3" in rank_str or "ex 3" in rank_str:
        return "ex3"
    return rank_str


def normalize_name(name: str) -> str:
    """Collapse whitespace so names match across stats and notes sheets."""
    return " ".join(name.split())


def _ascii_fold(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def generate_boss_id(fight_name: str) -> str:
    """Generate an ASCII boss ID from the fight name."""
    name = _ascii_fold(fight_name).lower()
    name = re.sub(r"[&\n]", " ", name)
    name = re.sub(r"[^a-z0-9\s-]", "", name)
    name = re.sub(r"\s+", "-", name.strip())
    name = re.sub(r"-+", "-", name)
    name = name.strip("-")

    # Add prefix based on content
    return f"adversary-{name}"


def _data_start(rows: list[list[str]]) -> int:
    """Index of the first data row, just below the 'Fight Name' header row."""
    for i, row in enumerate(rows[:10]):
        if row and row[0].strip().startswith("Fight Name"):
            return i + 1
    return 1


def _enemy_from_legacy_row(name: str, row: list[str]) -> EnemyStats:
    weaknesses = row[6].strip()
    return EnemyStats(
        name=name,
        level=parse_int_safe(row[4].strip()),
        shields=parse_shields(row[5].strip()),
        weaknesses=parse_weakness_string(weaknesses),
        weaknesses_rotate="\n" in weaknesses,
        hp=parse_int_safe(row[7].strip()),
        sp=parse_int_safe(row[8].strip()),
        p_atk=parse_int_safe(row[10].strip()),
        p_def=parse_int_safe(row[11].strip()),
        e_atk=parse_int_safe(row[12].strip()),
        e_def=parse_int_safe(row[13].strip()),
        speed=parse_int_safe(row[14].strip()),
        crit=parse_int_safe(row[15].strip()),
        crit_def=parse_int_safe(row[16].strip()),
        equip_atk=parse_int_safe(row[17].strip()),
    )


def parse_csv_file(
    csv_path: Path, level_tier: str, source: str = LEGACY_SOURCE
) -> list[AdversaryFight]:
    """Parse a single CSV file and extract fight data."""
    fights = []
    current_fight = None
    current_variant = None

    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.reader(f))

    for row in rows[_data_start(rows) :]:
        row = row + [""] * (20 - len(row))

        fight_name = row[0].strip()
        rank_col = row[2].strip()  # For multi-enemy: "Rank 1", "EX1", etc.
        name_col = row[3].strip()  # Enemy name for multi-enemy fights
        level = row[4].strip()
        hp = row[7].strip()

        # New fight detected (fight_name in column 0)
        if fight_name:
            if current_fight and current_fight.variants:
                fights.append(current_fight)

            current_fight = AdversaryFight(
                fight_name=fight_name,
                level_tier=level_tier,
                is_multi_enemy="&" in fight_name
                or "x2" in fight_name.lower()
                or "x3" in fight_name.lower(),
                source=source,
            )
            current_variant = None

        if not current_fight:
            continue

        # CASE 1: Multi-enemy fight - rank in col 2, enemy name in col 3
        if rank_col and current_fight.is_multi_enemy:
            normalized_rank = normalize_rank(rank_col)
            if normalized_rank in RANKS:
                current_variant = FightVariant(rank=normalized_rank)
                current_fight.variants[normalized_rank] = current_variant

        if current_fight.is_multi_enemy:
            if name_col and level and hp and current_variant is not None:
                current_variant.enemies.append(_enemy_from_legacy_row(name_col, row))

        # CASE 2: Single enemy fight - rank embedded in col 2 with name
        elif rank_col and level and hp:
            # Check for rank pattern in rank_col (e.g., "Francesca Rank 1" or "Francesca EX1")
            rank_match = re.search(r"(Rank\s*\d+|EX\d+)", rank_col, re.IGNORECASE)
            if not rank_match:
                continue
            normalized_rank = normalize_rank(rank_match.group(1))
            if normalized_rank not in RANKS:
                continue

            current_variant = current_fight.variants.setdefault(
                normalized_rank, FightVariant(rank=normalized_rank)
            )

            # Extract base name (remove rank suffix)
            base_name = re.sub(
                r"\s*(Rank\s*\d+|EX\d+)\s*$", "", rank_col, flags=re.IGNORECASE
            ).strip()
            if not base_name:
                base_name = current_fight.fight_name.split("\n")[0].strip()

            current_variant.enemies.append(_enemy_from_legacy_row(base_name, row))

    # Don't forget the last fight
    if current_fight and current_fight.variants:
        fights.append(current_fight)

    # Placeholder fight names ("Seed Story 4 Boss (Name Pending)") take the enemy name.
    for fight in fights:
        rank1 = fight.variants.get("rank1")
        if "name pending" in fight.fight_name.lower() and rank1 and rank1.enemies:
            fight.fight_name = rank1.enemies[0].name

    return fights


def _parse_new_export_block(
    rows: list[list[str]], start: int, end: int, level_tier: str, source: str
) -> AdversaryFight | None:
    title = rows[NEW_TITLE_ROW][start].strip()
    rank = next(
        (
            normalize_rank(cell)
            for cell in rows[NEW_TITLE_ROW][start + 1 : end]
            if normalize_rank(cell) in RANKS
        ),
        None,
    )
    if not title or rank is None:
        return None

    speed_row = rows[NEW_STAT_ROWS["speed"]]
    notes_col = next((c for c in range(start + 1, end) if speed_row[c].strip() == "Notes"), end)
    enemy_cols = [
        c for c in range(start + 1, notes_col) if parse_int_safe(rows[NEW_STAT_ROWS["hp"]][c])
    ]
    if not enemy_cols:
        return None

    # Shields sit right of the "Notes" column: "<enemy #>, <shields>" pairs for
    # multi-enemy blocks, a lone value on the name row for single-enemy blocks.
    shields: dict[int, int] = {}
    if notes_col + 1 < end:
        for r in range(NEW_NAME_ROW, NEW_STAT_ROWS["equip_atk"] + 1):
            idx, value = rows[r][notes_col].strip(), rows[r][notes_col + 1].strip()
            if not value.isdigit():
                continue
            if idx.isdigit():
                shields[int(idx)] = int(value)
            elif not idx and r == NEW_NAME_ROW:
                shields[1] = int(value)

    # Multi-enemy blocks number their enemies instead of naming them; #1 is the boss.
    enemies = []
    for number, col in enumerate(enemy_cols, start=1):
        raw_name = rows[NEW_NAME_ROW][col].strip()
        if number == 1:
            name = title
        else:
            name = f"Enemy {number}" if raw_name.isdigit() else raw_name
        stats = {key: parse_int_safe(rows[r][col]) for key, r in NEW_STAT_ROWS.items()}
        enemies.append(
            EnemyStats(
                name=name,
                level=0,
                shields=shields.get(number, 0),
                weaknesses=[],
                sp=0,
                **stats,
            )
        )

    return AdversaryFight(
        fight_name=title,
        level_tier=level_tier,
        is_multi_enemy=len(enemies) > 1,
        variants={rank: FightVariant(rank=rank, enemies=enemies)},
        source=source,
    )


def parse_new_export_file(
    csv_path: Path, level_tier: str, source: str = NEW_EXPORT_SOURCE
) -> list[AdversaryFight]:
    """Parse an 'Adversary Log New' sheet: one column block per fight."""
    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if len(rows) <= NEW_STAT_ROWS["equip_atk"]:
        return []

    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    starts = [c for c, cell in enumerate(rows[NEW_HEADER_ROW]) if cell.strip() == "Enemy Stats"]

    fights = []
    for start, next_start in zip(starts, [*starts[1:], width + 1]):
        fight = _parse_new_export_block(rows, start, next_start - 1, level_tier, source)
        if fight:
            fights.append(fight)
    return fights


def parse_notes_file(notes_path: Path) -> dict[str, list[str]]:
    """Parse a Fight Notes CSV into bullet lines keyed by normalized fight name."""
    notes: dict[str, list[str]] = {}

    if not notes_path.exists():
        return notes

    with open(notes_path, encoding="utf-8") as f:
        rows = list(csv.reader(f))

    current_fight = None
    for row in rows[_data_start(rows) :]:
        row = row + [""] * (5 - len(row))

        if row[0].strip():
            current_fight = normalize_name(row[0])
            notes.setdefault(current_fight, [])
        if not current_fight:
            continue

        if top_level := normalize_name(row[2]):
            notes[current_fight].append(f"- {top_level}")
        if nested := normalize_name(row[3]):
            # A literal block's indentation comes from its first line, so it must be top-level.
            indent = "  " if notes[current_fight] else ""
            notes[current_fight].append(f"{indent}- {nested}")

    return {name: lines for name, lines in notes.items() if lines}


def format_weaknesses_yaml(weaknesses: list[str], indent: int = 0) -> list[str]:
    """Format weaknesses as YAML lines."""
    lines = []
    prefix = "  " * indent

    elements = [w for w in weaknesses if w in ELEMENTS]
    weapons = [w for w in weaknesses if w in WEAPONS]

    if elements or weapons:
        lines.append(f"{prefix}weaknesses:")
        if elements:
            lines.append(f"{prefix}  elements:")
            for e in elements:
                lines.append(f"{prefix}    - {e}")
        if weapons:
            lines.append(f"{prefix}  weapons:")
            for w in weapons:
                lines.append(f"{prefix}    - {w}")

    return lines


def generate_base_yaml(fight: AdversaryFight) -> str:
    """Generate YAML content for the BASE fight (Rank 1-3)."""
    boss_id = generate_boss_id(fight.fight_name)
    today = date.today().isoformat()

    # Get main enemy from rank1
    rank1 = fight.variants.get("rank1")
    main_enemy = rank1.enemies[0] if rank1 and rank1.enemies else None

    if not main_enemy:
        return None

    # Determine difficulty based on level tier
    difficulty_map = {
        "1": "normal",
        "25": "hard",
        "50": "very_hard",
        "75": "extreme",
    }
    difficulty = difficulty_map.get(fight.level_tier, "hard")

    lines = []
    lines.append(f"# Adversary Log Boss: {fight.fight_name.replace(chr(10), ' ')}")
    lines.append(f"# SOURCE: {fight.source}")
    lines.append("#")
    lines.append("# Base version with Rank 1-3 variants.")
    lines.append("# See separate -ex1, -ex2, -ex3 files for EX variants.")
    lines.append("")
    lines.append(f"id: {boss_id}")
    lines.append(f'display_name: "{main_enemy.name}"')
    lines.append("content_type: adversary_log")
    lines.append(f"difficulty: {difficulty}")
    lines.append('location: "Adversary Log (宿敵の写記)"')
    lines.append("")

    # Rank 1 base stats (what RAG will index); unknown (0) values are omitted
    lines.append("# ===========================================================================")
    lines.append("# BASE STATS (Rank 1)")
    lines.append("# ===========================================================================")
    for key in STAT_FIELDS:
        if value := getattr(main_enemy, key):
            lines.append(f"{key}: {value}")
    lines.append("")

    # Weaknesses
    lines.extend(format_weaknesses_yaml(main_enemy.weaknesses))

    # Rank 2 and 3 as structured data
    lines.append("")
    lines.append("# ===========================================================================")
    lines.append("# RANK VARIANTS (for progression)")
    lines.append("# ===========================================================================")
    lines.append("rank_variants:")

    for rank_key in ["rank1", "rank2", "rank3"]:
        variant = fight.variants.get(rank_key)
        if variant and variant.enemies:
            main = variant.enemies[0]
            rank_num = rank_key.replace("rank", "")
            lines.append(f"  rank{rank_num}:")
            for key in ("shield_count", "hp", "speed", "level"):
                if value := getattr(main, key):
                    lines.append(f"    {key}: {value}")

    # Multi-enemy encounter
    if fight.is_multi_enemy and rank1 and len(rank1.enemies) > 1:
        lines.append("")
        lines.append(
            "# ==========================================================================="
        )
        lines.append("# MULTI-ENEMY ENCOUNTER")
        lines.append(
            "# ==========================================================================="
        )
        lines.append("enemies:")
        for idx, enemy in enumerate(rank1.enemies):
            lines.append(f'  - name: "{enemy.name}"')
            if idx == 0:
                lines.append("    is_main_target: true")
            lines.append(f"    shield_count: {enemy.shields}")
            lines.append(f"    hp: {enemy.hp}")
            lines.append(f"    speed: {enemy.speed}")
            lines.extend(
                [f"  {line}" for line in format_weaknesses_yaml(enemy.weaknesses, indent=1)]
            )
            lines.append("")

    # Notes as actual strategy field (RAG-indexable!)
    lines.append("")
    lines.append("# ===========================================================================")
    lines.append("# STRATEGY")
    lines.append("# ===========================================================================")
    lines.append("general_strategy: |")
    if fight.notes:
        lines.extend(f"  {note}" for note in fight.notes)
    else:
        lines.append(f"  {TODO_STRATEGY}")

    lines.append("")

    # Team requirements
    lines.append("required_roles:")
    lines.append("  - role: breaker")
    lines.append("    priority: required")
    lines.append('    reason: "Break to deal damage and control fight"')
    lines.append("  - role: dps")
    lines.append("    priority: required")
    lines.append('    reason: "Deal damage during break windows"')

    # Recommended weakness coverage
    elements = [w for w in main_enemy.weaknesses if w in ELEMENTS]
    weapons = [w for w in main_enemy.weaknesses if w in WEAPONS]

    lines.append("")
    if weapons or elements:
        lines.append("recommended_weakness_coverage:")
        for w in weapons + elements:
            lines.append(f"  - {w}")
    else:
        lines.append("recommended_weakness_coverage: []  # No weaknesses parsed")

    lines.append("")

    # Metadata
    sources = f"{fight.source}; {NOTES_SOURCE}" if fight.notes else fight.source
    lines.append("# ===========================================================================")
    lines.append("# METADATA")
    lines.append("# ===========================================================================")
    lines.append("data_confidence: incomplete")
    lines.append(f'data_source: "{sources}"')
    lines.append(f"last_updated: {today}")

    return "\n".join(lines) + "\n"


def generate_ex_yaml(fight: AdversaryFight, ex_rank: str) -> str:
    """Generate YAML content for an EX variant file."""
    base_boss_id = generate_boss_id(fight.fight_name)
    boss_id = f"{base_boss_id}-{ex_rank}"
    today = date.today().isoformat()

    variant = fight.variants.get(ex_rank)
    if not variant or not variant.enemies:
        return None

    main_enemy = variant.enemies[0]

    # Get rank1 for comparison
    rank1 = fight.variants.get("rank1")
    rank1_main = rank1.enemies[0] if rank1 and rank1.enemies else None

    # Calculate scaling from rank1
    hp_multiplier = 1.0
    if rank1_main and rank1_main.hp > 0:
        hp_multiplier = main_enemy.hp / rank1_main.hp

    # Determine actions per turn based on EX rank
    actions_per_turn = 2 if ex_rank in ["ex1", "ex2"] else 3

    ex_display = ex_rank.upper()

    lines = []
    lines.append(f"# Adversary Log Boss: {fight.fight_name.replace(chr(10), ' ')} {ex_display}")
    lines.append(f"# SOURCE: {fight.source}")
    lines.append("#")
    lines.append(f"# {ex_display} variant with increased stats and difficulty.")
    lines.append("")
    lines.append(f"id: {boss_id}")
    lines.append(f'display_name: "{main_enemy.name} {ex_display}"')
    lines.append("content_type: adversary_log")
    lines.append("difficulty: extreme")
    lines.append('location: "Adversary Log (宿敵の写記)"')
    lines.append("")

    # EX variant info (RAG-critical fields!)
    lines.append("# ===========================================================================")
    lines.append("# EX VARIANT INFO")
    lines.append("# ===========================================================================")
    lines.append(f"base_boss_id: {base_boss_id}")
    lines.append(f"ex_rank: {ex_rank}")
    lines.append(f"actions_per_turn: {actions_per_turn}")
    lines.append("provoke_immunity: true  # Most EX bosses are provoke immune")
    lines.append("")

    # Stats (actual values for RAG indexing)
    lines.append("# ===========================================================================")
    lines.append(f"# {ex_display} STATS")
    lines.append("# ===========================================================================")
    lines.append(f"level: {main_enemy.level}")
    lines.append(f"shield_count: {main_enemy.shields}")
    lines.append(f"hp: {main_enemy.hp}  # ~{hp_multiplier:.1f}x base")
    lines.append(f"speed: {main_enemy.speed}")
    lines.append(f"p_atk: {main_enemy.p_atk}")
    lines.append(f"p_def: {main_enemy.p_def}")
    lines.append(f"e_atk: {main_enemy.e_atk}")
    lines.append(f"e_def: {main_enemy.e_def}")
    lines.append("")

    # Weaknesses
    lines.extend(format_weaknesses_yaml(main_enemy.weaknesses))

    # Multi-enemy for EX
    if fight.is_multi_enemy and len(variant.enemies) > 1:
        lines.append("")
        lines.append(
            "# ==========================================================================="
        )
        lines.append(f"# MULTI-ENEMY ENCOUNTER ({ex_display})")
        lines.append(
            "# ==========================================================================="
        )
        lines.append("enemies:")
        for idx, enemy in enumerate(variant.enemies):
            lines.append(f'  - name: "{enemy.name}"')
            if idx == 0:
                lines.append("    is_main_target: true")
            lines.append(f"    shield_count: {enemy.shields}")
            lines.append(f"    hp: {enemy.hp}")
            lines.append(f"    speed: {enemy.speed}")
            lines.extend(
                [f"  {line}" for line in format_weaknesses_yaml(enemy.weaknesses, indent=1)]
            )
            lines.append("")

    # Strategy (EX-specific)
    lines.append("")
    lines.append("# ===========================================================================")
    lines.append(f"# STRATEGY ({ex_display} SPECIFIC)")
    lines.append("# ===========================================================================")

    # Generate EX-specific strategy based on rank
    if ex_rank == "ex1":
        lines.append("general_strategy: |")
        lines.append(f"  {ex_display} variant with ~{hp_multiplier:.0f}x HP.")
        lines.append("  ")
        lines.append("  Key changes from base:")
        lines.append(f"  - Higher HP ({main_enemy.hp:,})")
        lines.append(f"  - Higher shield count ({main_enemy.shields})")
        lines.append(f"  - Higher speed ({main_enemy.speed})")
        lines.append(f"  - {actions_per_turn} actions per turn")
        lines.append("  ")
        lines.append("  Recommended HP per character: 3000+")
    elif ex_rank == "ex2":
        lines.append("general_strategy: |")
        lines.append(f"  {ex_display} variant with ~{hp_multiplier:.0f}x HP.")
        lines.append("  ")
        lines.append("  Key changes from base:")
        lines.append(f"  - Much higher HP ({main_enemy.hp:,})")
        lines.append(f"  - Higher shield count ({main_enemy.shields})")
        lines.append(f"  - Much higher speed ({main_enemy.speed})")
        lines.append(f"  - {actions_per_turn} actions per turn")
        lines.append("  ")
        lines.append("  CRITICAL:")
        lines.append("  - Stack all 5 damage multiplier categories")
        lines.append("  - Speed tuning required for debuffers")
        lines.append("  - Consider dodge tank (H'aanit EX, Canary)")
        lines.append("  ")
        lines.append("  Recommended HP per character: 3500+")
    else:  # ex3
        lines.append("general_strategy: |")
        lines.append(f"  {ex_display} variant - MAXIMUM DIFFICULTY.")
        lines.append("  ")
        lines.append("  Key changes from base:")
        lines.append(f"  - Extreme HP ({main_enemy.hp:,})")
        lines.append(f"  - Maximum shield count ({main_enemy.shields})")
        lines.append(f"  - Very high speed ({main_enemy.speed})")
        lines.append(f"  - {actions_per_turn} actions per turn from early fight")
        lines.append("  ")
        lines.append("  CRITICAL:")
        lines.append("  - Either speedkill (Solon + Primrose EX) or full turtle")
        lines.append("  - Stack all buff/debuff categories to 30%")
        lines.append("  - Fiore EX Cover or dodge tank essential")
        lines.append("  - May take 50-100+ turns without optimal setup")
        lines.append("  ")
        lines.append("  Recommended HP per character: 4000+")

    # Add fight notes if available
    if fight.notes:
        lines.append("  ")
        lines.append("  Fight notes:")
        lines.extend(f"  {note}" for note in fight.notes)

    lines.append("")

    # Required roles
    lines.append("required_roles:")
    lines.append("  - role: debuffer")
    lines.append("    priority: required")
    lines.append('    reason: "Stack attack debuffs (30% cap)"')
    lines.append("  - role: healer")
    lines.append("    priority: required")
    lines.append('    reason: "Survive multi-action turns"')
    lines.append("  - role: dps")
    lines.append("    priority: required")
    lines.append('    reason: "Deal damage during break windows"')
    if ex_rank in ["ex2", "ex3"]:
        lines.append("  - role: tank")
        lines.append("    priority: strongly_recommended")
        lines.append('    reason: "Fiore EX Cover or dodge tank for survival"')

    # Recommended weakness coverage
    elements = [w for w in main_enemy.weaknesses if w in ELEMENTS]
    weapons = [w for w in main_enemy.weaknesses if w in WEAPONS]

    lines.append("")
    if weapons or elements:
        lines.append("recommended_weakness_coverage:")
        for w in weapons + elements:
            lines.append(f"  - {w}")
    else:
        lines.append("recommended_weakness_coverage: []  # No weaknesses parsed")

    lines.append("")

    # Metadata
    lines.append("# ===========================================================================")
    lines.append("# METADATA")
    lines.append("# ===========================================================================")
    lines.append("data_confidence: incomplete")
    lines.append(f'data_source: "{fight.source}"')
    lines.append(f"last_updated: {today}")

    return "\n".join(lines) + "\n"


# =============================================================================
# FILL-MISSING MERGE
# =============================================================================


@dataclass
class BossFile:
    """An existing boss YAML file held in memory during a fill-missing run."""

    path: Path
    text: str
    data: dict
    changed: bool = False


def load_boss_files(output_dir: Path) -> dict[str, BossFile]:
    """Load boss YAML files keyed by their `id` (falling back to the file stem)."""
    files = {}
    for path in sorted(output_dir.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text) or {}
        files[data.get("id", path.stem)] = BossFile(path, text, data)
    return files


def known_base_ids(files: dict[str, BossFile]) -> set[str]:
    """Base boss IDs: non-EX files plus every `base_boss_id` EX files point at."""
    ids = set()
    for boss_id, boss in files.items():
        if boss.data.get("ex_rank") in EX_RANKS:
            if base := boss.data.get("base_boss_id"):
                ids.add(base)
        else:
            ids.add(boss_id)
    return ids


def resolve_base_id(fight_name: str, base_ids: set[str]) -> str | None:
    """Match a sheet fight name to a known base ID (exact, arena-*, or unique prefix).

    Sheets disagree on how much of a multi-enemy fight name they spell out
    ("Siva" vs "Siva & Zash"), so a unique prefix match in either direction counts.
    """
    slug = generate_boss_id(fight_name)
    arena_slug = "arena-" + slug.removeprefix("adversary-")
    for candidate in (slug, arena_slug):
        if candidate in base_ids:
            return candidate
    for matches in (
        [b for b in base_ids if b.startswith(slug + "-")],
        [b for b in base_ids if slug.startswith(b + "-")],
    ):
        if len(matches) == 1:
            return matches[0]
    return None


def resolve_target(base_id: str, rank: str, files: dict[str, BossFile]) -> BossFile | None:
    """File holding `rank` of `base_id`: the base file for Rank 1, else the EX file."""
    if rank == "rank1":
        return files.get(base_id)
    if rank not in EX_RANKS:
        return None
    if target := files.get(f"{base_id}-{rank}"):
        return target
    matches = [
        boss
        for boss in files.values()
        if boss.data.get("base_boss_id") == base_id and boss.data.get("ex_rank") == rank
    ]
    return matches[0] if len(matches) == 1 else None


def _is_empty(value: object) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _has_weaknesses(data: dict) -> bool:
    def present(weaknesses: object) -> bool:
        return isinstance(weaknesses, dict) and any(
            weaknesses.get(k) for k in ("elements", "weapons")
        )

    return present(data.get("weaknesses")) or any(
        present((enemy or {}).get("weaknesses")) for enemy in data.get("enemies") or []
    )


def find_conflict(data: dict, enemy: EnemyStats) -> str | None:
    """Describe a curated HP/shield value that contradicts the source, if any."""
    for key in ("hp", "shield_count"):
        have, want = data.get(key), getattr(enemy, key)
        if isinstance(have, int) and want and have != want:
            return f"{key} {have} != source {want}"
    return None


def find_column_shifts(data: dict, enemy: EnemyStats) -> dict[str, tuple[int, int, list[str]]]:
    """Curated stats that equal a *different* column of the fight's own sheet row.

    Returns {field: (curated, sheet value, matching columns)}. Values that merely
    differ from the sheet are not reported; only a match on another column is
    evidence that the value was read from the wrong column.
    """
    columns = {key: getattr(enemy, key) for key in SHEET_COLUMNS}
    shifts = {}
    for key in (*FILL_FIELDS, "p_atk", "e_atk"):
        have, want = data.get(key), columns[key]
        if not isinstance(have, int) or not want or have == want:
            continue
        if matches := [col for col, value in columns.items() if col != key and value == have]:
            shifts[key] = (have, want, matches)
    return shifts


def compute_fill(data: dict, enemy: EnemyStats, notes: list[str] | None = None) -> dict:
    """Values the source can supply for fields that are missing or empty in `data`."""
    fill: dict = {}
    for key in FILL_FIELDS:
        value = getattr(enemy, key)
        if value and _is_empty(data.get(key)):
            fill[key] = value

    if enemy.weaknesses and not enemy.weaknesses_rotate and not _has_weaknesses(data):
        weaknesses = {
            "elements": [w for w in enemy.weaknesses if w in ELEMENTS],
            "weapons": [w for w in enemy.weaknesses if w in WEAPONS],
        }
        fill["weaknesses"] = {k: v for k, v in weaknesses.items() if v}
        if _is_empty(data.get("recommended_weakness_coverage")):
            fill["recommended_weakness_coverage"] = weaknesses["weapons"] + weaknesses["elements"]

    strategy = data.get("general_strategy")
    if notes and (_is_empty(strategy) or str(strategy).strip() == TODO_STRATEGY):
        fill["general_strategy"] = "\n".join(notes) + "\n"

    return fill


def _block_span(lines: list[str], key: str) -> tuple[int, int] | None:
    """[start, end) of a top-level key and its indented continuation lines."""
    pattern = re.compile(rf"^{re.escape(key)}:(\s|$)")
    for start, line in enumerate(lines):
        if not pattern.match(line):
            continue
        end = start + 1
        while end < len(lines) and (
            not lines[end].strip() or lines[end][0] in " \t" or lines[end].startswith("- ")
        ):
            end += 1
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1
        return start, end
    return None


def _render(key: str, value: object) -> list[str]:
    if key == "weaknesses":
        lines = ["weaknesses:"]
        for group, items in value.items():
            lines.append(f"  {group}:")
            lines.extend(f"    - {item}" for item in items)
        return lines
    if key == "recommended_weakness_coverage":
        return [f"{key}:", *(f"  - {item}" for item in value)]
    if key == "general_strategy":
        return [f"{key}: |", *(f"  {line}" for line in value.splitlines())]
    if key == "data_source":
        return [f"{key}: {json.dumps(value, ensure_ascii=False)}"]
    return [f"{key}: {value}"]


def _insertion_point(lines: list[str], anchors: tuple[str, ...], after: bool) -> int:
    for anchor in anchors:
        if span := _block_span(lines, anchor):
            return span[1] if after else span[0]
    return len(lines)


def apply_fill(text: str, fill: dict, sources: list[str]) -> str:
    """Write `fill` into YAML text, touching only the filled top-level keys."""
    lines = text.splitlines()

    pending: list[str] = []
    for key in (*FILL_FIELDS, "weaknesses"):
        if key not in fill:
            continue
        if span := _block_span(lines, key):
            lines[span[0] : span[1]] = _render(key, fill[key])
        else:
            pending.extend(_render(key, fill[key]))
    if pending:
        at = _insertion_point(lines, STAT_ANCHORS, after=True)
        lines[at:at] = pending

    for key, anchors in (
        ("general_strategy", STRATEGY_ANCHORS),
        ("recommended_weakness_coverage", COVERAGE_ANCHORS),
    ):
        if key not in fill:
            continue
        if span := _block_span(lines, key):
            lines[span[0] : span[1]] = _render(key, fill[key])
        else:
            at = _insertion_point(lines, anchors, after=False)
            lines[at:at] = _render(key, fill[key])

    data_source = (yaml.safe_load(text) or {}).get("data_source") or ""
    missing_sources = [s for s in sources if s not in data_source]
    if missing_sources:
        combined = "; ".join([data_source, *missing_sources] if data_source else missing_sources)
        if span := _block_span(lines, "data_source"):
            lines[span[0] : span[1]] = _render("data_source", combined)
        else:
            lines.extend(_render("data_source", combined))

    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def fill_boss_file(boss: BossFile, fill: dict, sources: list[str]) -> None:
    """Apply `fill` in memory and verify no pre-existing value changed."""
    new_text = apply_fill(boss.text, fill, sources)
    new_data = yaml.safe_load(new_text)
    for key, value in boss.data.items():
        if key not in fill and key != "data_source" and new_data.get(key) != value:
            raise RuntimeError(f"{boss.path.name}: fill changed existing key '{key}'")
    for key, value in fill.items():
        if new_data.get(key) != value:
            raise RuntimeError(f"{boss.path.name}: '{key}' did not round-trip")
    boss.text, boss.data, boss.changed = new_text, new_data, True


def run_fill_missing(fights: list[AdversaryFight], output_dir: Path, dry_run: bool) -> None:
    """Fill empty fields of existing boss files from parsed fights."""
    files = load_boss_files(output_dir)
    base_ids = known_base_ids(files)
    filled: dict[str, list[str]] = {}
    conflicts: list[str] = []
    column_shifts: set[str] = set()
    unmatched: list[str] = []
    created: list[str] = []

    for fight in fights:
        label = normalize_name(fight.fight_name)
        base_id = resolve_base_id(fight.fight_name, base_ids)
        if base_id is None:
            unmatched.append(f"{label} [{fight.source}]")
            continue

        if (
            base_id not in files
            and "rank1" in fight.variants
            and base_id == generate_boss_id(fight.fight_name)
        ):
            content = generate_base_yaml(fight)
            path = output_dir / f"{base_id}.yaml"
            files[base_id] = BossFile(path, content, yaml.safe_load(content), changed=True)
            created.append(base_id)

        for rank, variant in fight.variants.items():
            target = resolve_target(base_id, rank, files)
            if target is None or not variant.enemies:
                continue
            enemy = variant.enemies[0]
            if conflict := find_conflict(target.data, enemy):
                conflicts.append(f"{target.path.stem} ({fight.source}, {label} {rank}): {conflict}")
                continue
            if target.data.get("hp") == enemy.hp:
                for key, (have, want, cols) in find_column_shifts(target.data, enemy).items():
                    column_shifts.add(
                        f"{target.path.stem}: {key} {have} equals sheet {'/'.join(cols)}; "
                        f"sheet {key} is {want}"
                    )
            notes = fight.notes if rank == "rank1" else None
            fill = compute_fill(target.data, enemy, notes)
            if not fill:
                continue
            sources = [fight.source] if set(fill) - {"general_strategy"} else []
            if "general_strategy" in fill:
                sources.append(NOTES_SOURCE)
            fill_boss_file(target, fill, sources)
            filled.setdefault(target.path.stem, []).extend(fill)

    for boss_id in created:
        print(f"  {'Would create' if dry_run else 'Created'} BASE: {boss_id}")
    for stem, keys in sorted(filled.items()):
        print(f"  {'Would fill' if dry_run else 'Filled'} {stem}: {', '.join(dict.fromkeys(keys))}")
    for conflict in conflicts:
        print(f"  Conflict (skipped): {conflict}")
    for shift in sorted(column_shifts):
        print(f"  Column shift (not changed): {shift}")
    for name in unmatched:
        print(f"  Unmatched fight: {name}")

    if not dry_run:
        for boss in files.values():
            if boss.changed:
                boss.path.write_text(boss.text, encoding="utf-8")

    print("\nFill-missing summary:")
    print(f"  Base files created: {len(created)}")
    print(f"  Files filled: {len(filled)}")
    print(f"  Conflicts skipped: {len(conflicts)}")
    print(f"  Column shifts reported: {len(column_shifts)}")
    print(f"  Unmatched fights: {len(unmatched)}")


def load_fights(project_root: Path, include_new_export: bool) -> list[AdversaryFight]:
    """Parse every stats sheet and attach Fight Notes to legacy fights."""
    legacy_dir = project_root / "resources" / LEGACY_DIR
    new_dir = project_root / "resources" / NEW_EXPORT_DIR

    all_notes: dict[str, list[str]] = {}
    for stem in LEGACY_NOTES_FILES:
        all_notes.update(parse_notes_file(legacy_dir / f"{LEGACY_PREFIX}{stem}.csv"))

    fights: list[AdversaryFight] = []
    for stem, level_tier in LEGACY_STATS_FILES:
        csv_path = legacy_dir / f"{LEGACY_PREFIX}{stem}.csv"
        if not csv_path.exists():
            print(f"Warning: CSV file not found: {csv_path}")
            continue
        parsed = parse_csv_file(csv_path, level_tier, f"{LEGACY_SOURCE} - {stem}")
        for fight in parsed:
            fight.notes = all_notes.get(normalize_name(fight.fight_name), [])
        print(f"Parsing: {csv_path.name}\n  Found {len(parsed)} fights")
        fights.extend(parsed)

    if include_new_export:
        for stem, level_tier in NEW_EXPORT_FILES:
            csv_path = new_dir / f"{NEW_EXPORT_PREFIX}{stem}.csv"
            if not csv_path.exists():
                print(f"Warning: CSV file not found: {csv_path}")
                continue
            parsed = parse_new_export_file(csv_path, level_tier, f"{NEW_EXPORT_SOURCE} ({stem})")
            print(f"Parsing: {csv_path.name}\n  Found {len(parsed)} fights")
            fights.extend(parsed)

    return fights


def main():
    parser = argparse.ArgumentParser(description="Import Adversary Log bosses from CSV")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be created")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--overwrite", action="store_true", help="Overwrite existing files")
    mode.add_argument(
        "--fill-missing",
        action="store_true",
        help="Fill empty fields of existing files without overwriting curated values",
    )
    args = parser.parse_args()

    # Paths
    project_root = Path(__file__).parent.parent
    output_dir = project_root / "data" / "bosses"

    if not (project_root / "resources" / LEGACY_DIR).exists():
        print(f"Error: Resources directory not found: {project_root / 'resources' / LEGACY_DIR}")
        return

    all_fights = load_fights(project_root, include_new_export=args.fill_missing)
    print(f"\nTotal fights found: {len(all_fights)}")

    if args.fill_missing:
        run_fill_missing(all_fights, output_dir, args.dry_run)
        if args.dry_run:
            print("\n(Dry run - no files written)")
        return

    # Arena bosses that already exist (skip these)
    existing_arena_bosses = {
        "tikilen",
        "glossom",
        "varkyn",
        "ritu",
        "ri'tu",
        "gertrude",
        "yan long",
        "yan-long",
        "yunnie",
        "largo",
        "aoi",
        "kagemune",
        "mirgardi",
    }

    # Generate YAML files
    base_created = 0
    ex_created = 0
    skipped = 0
    skipped_arena = 0
    skipped_invalid = 0
    existing_base_ids = known_base_ids(load_boss_files(output_dir))

    for fight in all_fights:
        if not fight.variants:
            continue

        base_boss_id = generate_boss_id(fight.fight_name)

        # Skip empty IDs
        if base_boss_id == "adversary-" or not base_boss_id or base_boss_id == "adversary":
            print(f"  Skip (invalid ID): '{fight.fight_name}'")
            skipped_invalid += 1
            continue

        # Skip existing arena bosses
        fight_name_lower = fight.fight_name.lower()
        if any(arena_boss in fight_name_lower for arena_boss in existing_arena_bosses):
            print(f"  Skip (arena exists): {base_boss_id}")
            skipped_arena += 1
            continue

        # Skip fights already stored under a differently spelled ID
        existing_id = resolve_base_id(fight.fight_name, existing_base_ids)
        if existing_id and existing_id != base_boss_id and not args.overwrite:
            print(f"  Skip (exists as {existing_id}): {base_boss_id}")
            skipped += 1
            continue

        # 1. Generate BASE file (Rank 1-3)
        base_path = output_dir / f"{base_boss_id}.yaml"

        if "rank1" in fight.variants:
            if base_path.exists() and not args.overwrite:
                print(f"  Skip (file exists): {base_boss_id}")
                skipped += 1
            else:
                yaml_content = generate_base_yaml(fight)
                if yaml_content:
                    if args.dry_run:
                        print(f"  Would create BASE: {base_boss_id}")
                        ranks = [k for k in fight.variants.keys() if k.startswith("rank")]
                        print(f"    Ranks: {ranks}")
                    else:
                        with open(base_path, "w", encoding="utf-8") as f:
                            f.write(yaml_content)
                        print(f"  Created BASE: {base_boss_id}")
                    base_created += 1

        # 2. Generate EX variant files (separate files!)
        for ex_rank in EX_RANKS:
            if ex_rank in fight.variants:
                ex_boss_id = f"{base_boss_id}-{ex_rank}"
                ex_path = output_dir / f"{ex_boss_id}.yaml"

                if ex_path.exists() and not args.overwrite:
                    print(f"  Skip (file exists): {ex_boss_id}")
                    skipped += 1
                else:
                    yaml_content = generate_ex_yaml(fight, ex_rank)
                    if yaml_content:
                        if args.dry_run:
                            main_enemy = fight.variants[ex_rank].enemies[0]
                            print(f"  Would create {ex_rank.upper()}: {ex_boss_id}")
                            print(f"    HP: {main_enemy.hp:,}, Shields: {main_enemy.shields}")
                        else:
                            with open(ex_path, "w", encoding="utf-8") as f:
                                f.write(yaml_content)
                            print(f"  Created {ex_rank.upper()}: {ex_boss_id}")
                        ex_created += 1

    print("\nSummary:")
    print(f"  Base files created: {base_created}")
    print(f"  EX files created: {ex_created}")
    print(f"  Total files: {base_created + ex_created}")
    print(f"  Skipped (file exists): {skipped}")
    print(f"  Skipped (arena exists): {skipped_arena}")
    print(f"  Skipped (invalid): {skipped_invalid}")

    if args.dry_run:
        print("\n(Dry run - no files written)")


if __name__ == "__main__":
    main()
