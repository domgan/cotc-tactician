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

CSV files are expected in resources/Adversary Log/ with format:
- EN OT_ COTC _ Adversary Log Enemy Index - Lv. X~.csv (stats)
- EN OT_ COTC _ Adversary Log Enemy Index - Lv. X~ Fight Notes.csv (tips)

Usage:
    python scripts/import_adversary_log_from_csv.py
    python scripts/import_adversary_log_from_csv.py --dry-run
    python scripts/import_adversary_log_from_csv.py --overwrite
"""

import argparse
import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from datetime import date


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


def parse_weakness_string(weakness_str: str) -> list[str]:
    """Parse weakness string into list of weakness types."""
    if not weakness_str or weakness_str.lower() == 'none':
        return []
    
    # Normalize names
    weakness_map = {
        'sword': 'sword',
        'spear': 'polearm',
        'polearm': 'polearm',
        'dagger': 'dagger',
        'axe': 'axe',
        'bow': 'bow',
        'staff': 'staff',
        'tome': 'tome',
        'fan': 'fan',
        'fire': 'fire',
        'ice': 'ice',
        'lightning': 'lightning',
        'wind': 'wind',
        'light': 'light',
        'dark': 'dark',
    }
    
    # Handle multi-line weakness strings (weakness cycling)
    # Just take the first set for now
    first_line = weakness_str.split('\n')[0].strip()
    
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
        val = val.replace(',', '').strip()
        return int(float(val))
    except (ValueError, TypeError):
        return 0


def parse_shields(val: str) -> int:
    """Parse shield count, handling special cases like '9 -> 12'."""
    if not val:
        return 0
    # Take first number if there's a range
    match = re.search(r'(\d+)', val)
    if match:
        return int(match.group(1))
    return 0


def normalize_rank(rank_str: str) -> str:
    """Normalize rank string to standard format."""
    rank_str = rank_str.strip().lower()
    if 'rank 1' in rank_str or rank_str == 'rank1':
        return 'rank1'
    if 'rank 2' in rank_str or rank_str == 'rank2':
        return 'rank2'
    if 'rank 3' in rank_str or rank_str == 'rank3':
        return 'rank3'
    if 'ex1' in rank_str or 'ex 1' in rank_str:
        return 'ex1'
    if 'ex2' in rank_str or 'ex 2' in rank_str:
        return 'ex2'
    if 'ex3' in rank_str or 'ex 3' in rank_str:
        return 'ex3'
    return rank_str


def generate_boss_id(fight_name: str) -> str:
    """Generate a boss ID from the fight name."""
    # Remove special characters and normalize
    name = fight_name.lower()
    name = re.sub(r'[&\n]', ' ', name)
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'\s+', '-', name.strip())
    name = re.sub(r'-+', '-', name)
    name = name.strip('-')
    
    # Add prefix based on content
    return f"adversary-{name}"


def parse_csv_file(csv_path: Path, level_tier: str) -> list[AdversaryFight]:
    """Parse a single CSV file and extract fight data."""
    fights = []
    current_fight = None
    current_variant = None
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        rows = list(reader)
    
    # Skip header rows
    data_rows = rows[4:] if len(rows) > 4 else rows[1:]
    
    i = 0
    while i < len(data_rows):
        row = data_rows[i]
        
        # Pad row to expected length
        while len(row) < 20:
            row.append('')
        
        fight_name = row[0].strip()
        rank_col = row[2].strip()  # For multi-enemy: "Rank 1", "EX1", etc.
        name_col = row[3].strip()  # Enemy name for multi-enemy fights
        level = row[4].strip()
        shields = row[5].strip()
        weaknesses = row[6].strip()
        hp = row[7].strip()
        sp = row[8].strip()
        # tp = row[9]  # Usually -1
        p_atk = row[10].strip()
        p_def = row[11].strip()
        e_atk = row[12].strip()
        e_def = row[13].strip()
        speed = row[14].strip()
        crit = row[15].strip()
        crit_def = row[16].strip()
        equip_atk = row[17].strip()
        
        # New fight detected (fight_name in column 0)
        if fight_name:
            if current_fight and current_fight.variants:
                fights.append(current_fight)
            
            current_fight = AdversaryFight(
                fight_name=fight_name,
                level_tier=level_tier,
                is_multi_enemy='&' in fight_name or 'x2' in fight_name.lower() or 'x3' in fight_name.lower()
            )
            current_variant = None
        
        # Skip if no current fight
        if not current_fight:
            i += 1
            continue
        
        # CASE 1: Multi-enemy fight - rank in col 2, enemy name in col 3
        if rank_col and current_fight.is_multi_enemy:
            normalized_rank = normalize_rank(rank_col)
            if normalized_rank in ['rank1', 'rank2', 'rank3', 'ex1', 'ex2', 'ex3']:
                current_variant = FightVariant(rank=normalized_rank)
                current_fight.variants[normalized_rank] = current_variant
        
        # Parse enemy data for multi-enemy fight
        if current_fight.is_multi_enemy and name_col and level and hp and current_variant is not None:
            enemy = EnemyStats(
                name=name_col.strip(),
                level=parse_int_safe(level),
                shields=parse_shields(shields),
                weaknesses=parse_weakness_string(weaknesses),
                hp=parse_int_safe(hp),
                sp=parse_int_safe(sp),
                p_atk=parse_int_safe(p_atk),
                p_def=parse_int_safe(p_def),
                e_atk=parse_int_safe(e_atk),
                e_def=parse_int_safe(e_def),
                speed=parse_int_safe(speed),
                crit=parse_int_safe(crit),
                crit_def=parse_int_safe(crit_def),
                equip_atk=parse_int_safe(equip_atk),
            )
            current_variant.enemies.append(enemy)
        
        # CASE 2: Single enemy fight - rank embedded in col 2 with name
        elif not current_fight.is_multi_enemy and rank_col and level and hp:
            # Check for rank pattern in rank_col (e.g., "Francesca Rank 1" or "Francesca EX1")
            rank_match = re.search(r'(Rank\s*\d+|EX\d+)', rank_col, re.IGNORECASE)
            if rank_match:
                rank_str = rank_match.group(1)
                if 'Rank 1' in rank_str or 'Rank1' in rank_str:
                    normalized_rank = 'rank1'
                elif 'Rank 2' in rank_str or 'Rank2' in rank_str:
                    normalized_rank = 'rank2'
                elif 'Rank 3' in rank_str or 'Rank3' in rank_str:
                    normalized_rank = 'rank3'
                elif 'EX1' in rank_str.upper():
                    normalized_rank = 'ex1'
                elif 'EX2' in rank_str.upper():
                    normalized_rank = 'ex2'
                elif 'EX3' in rank_str.upper():
                    normalized_rank = 'ex3'
                else:
                    i += 1
                    continue
                
                if normalized_rank not in current_fight.variants:
                    current_variant = FightVariant(rank=normalized_rank)
                    current_fight.variants[normalized_rank] = current_variant
                else:
                    current_variant = current_fight.variants[normalized_rank]
                
                # Extract base name (remove rank suffix)
                base_name = re.sub(r'\s*(Rank\s*\d+|EX\d+)\s*$', '', rank_col, flags=re.IGNORECASE).strip()
                if not base_name:
                    base_name = current_fight.fight_name.split('\n')[0].strip()
                
                enemy = EnemyStats(
                    name=base_name,
                    level=parse_int_safe(level),
                    shields=parse_shields(shields),
                    weaknesses=parse_weakness_string(weaknesses),
                    hp=parse_int_safe(hp),
                    sp=parse_int_safe(sp),
                    p_atk=parse_int_safe(p_atk),
                    p_def=parse_int_safe(p_def),
                    e_atk=parse_int_safe(e_atk),
                    e_def=parse_int_safe(e_def),
                    speed=parse_int_safe(speed),
                    crit=parse_int_safe(crit),
                    crit_def=parse_int_safe(crit_def),
                    equip_atk=parse_int_safe(equip_atk),
                )
                current_variant.enemies.append(enemy)
        
        i += 1
    
    # Don't forget the last fight
    if current_fight and current_fight.variants:
        fights.append(current_fight)
    
    return fights


def parse_notes_file(notes_path: Path) -> dict[str, list[str]]:
    """Parse fight notes CSV and return notes by fight name."""
    notes = {}
    
    if not notes_path.exists():
        return notes
    
    with open(notes_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        rows = list(reader)
    
    current_fight = None
    
    for row in rows[3:]:  # Skip headers
        while len(row) < 5:
            row.append('')
        
        fight_name = row[0].strip()
        note_col = row[2].strip()
        
        if fight_name:
            current_fight = fight_name
            if current_fight not in notes:
                notes[current_fight] = []
        
        if note_col and current_fight:
            notes[current_fight].append(note_col)
    
    return notes


def format_weaknesses_yaml(weaknesses: list[str], indent: int = 0) -> list[str]:
    """Format weaknesses as YAML lines."""
    lines = []
    prefix = "  " * indent
    
    elements = [w for w in weaknesses if w in ['fire', 'ice', 'lightning', 'wind', 'light', 'dark']]
    weapons = [w for w in weaknesses if w in ['sword', 'polearm', 'dagger', 'axe', 'bow', 'staff', 'tome', 'fan']]
    
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
    rank1 = fight.variants.get('rank1')
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
    lines.append(f"# SOURCE: Community Spreadsheet (Wigglytuff)")
    lines.append(f"#")
    lines.append(f"# Base version with Rank 1-3 variants.")
    lines.append(f"# See separate -ex1, -ex2, -ex3 files for EX variants.")
    lines.append(f"")
    lines.append(f"id: {boss_id}")
    lines.append(f'display_name: "{main_enemy.name}"')
    lines.append(f"content_type: adversary_log")
    lines.append(f"difficulty: {difficulty}")
    lines.append(f"location: \"Adversary Log (宿敵の写記)\"")
    lines.append(f"")
    
    # Rank 1 base stats (what RAG will index)
    lines.append(f"# ===========================================================================")
    lines.append(f"# BASE STATS (Rank 1)")
    lines.append(f"# ===========================================================================")
    lines.append(f"level: {main_enemy.level}")
    lines.append(f"shield_count: {main_enemy.shields}")
    lines.append(f"hp: {main_enemy.hp}")
    lines.append(f"speed: {main_enemy.speed}")
    lines.append(f"p_atk: {main_enemy.p_atk}")
    lines.append(f"p_def: {main_enemy.p_def}")
    lines.append(f"e_atk: {main_enemy.e_atk}")
    lines.append(f"e_def: {main_enemy.e_def}")
    lines.append(f"")
    
    # Weaknesses
    lines.extend(format_weaknesses_yaml(main_enemy.weaknesses))
    
    # Rank 2 and 3 as structured data
    lines.append(f"")
    lines.append(f"# ===========================================================================")
    lines.append(f"# RANK VARIANTS (for progression)")
    lines.append(f"# ===========================================================================")
    lines.append(f"rank_variants:")
    
    for rank_key in ['rank1', 'rank2', 'rank3']:
        variant = fight.variants.get(rank_key)
        if variant and variant.enemies:
            main = variant.enemies[0]
            rank_num = rank_key.replace('rank', '')
            lines.append(f"  rank{rank_num}:")
            lines.append(f"    shield_count: {main.shields}")
            lines.append(f"    hp: {main.hp}")
            lines.append(f"    speed: {main.speed}")
            lines.append(f"    level: {main.level}")
    
    # Multi-enemy encounter
    if fight.is_multi_enemy and rank1 and len(rank1.enemies) > 1:
        lines.append(f"")
        lines.append(f"# ===========================================================================")
        lines.append(f"# MULTI-ENEMY ENCOUNTER")
        lines.append(f"# ===========================================================================")
        lines.append(f"enemies:")
        for idx, enemy in enumerate(rank1.enemies):
            lines.append(f"  - name: \"{enemy.name}\"")
            if idx == 0:
                lines.append(f"    is_main_target: true")
            lines.append(f"    shield_count: {enemy.shields}")
            lines.append(f"    hp: {enemy.hp}")
            lines.append(f"    speed: {enemy.speed}")
            lines.extend([f"  {line}" for line in format_weaknesses_yaml(enemy.weaknesses, indent=1)])
            lines.append(f"")
    
    # Notes as actual strategy field (RAG-indexable!)
    lines.append(f"")
    lines.append(f"# ===========================================================================")
    lines.append(f"# STRATEGY")
    lines.append(f"# ===========================================================================")
    if fight.notes:
        lines.append(f"general_strategy: |")
        for note in fight.notes:
            note_clean = note.replace('\n', ' ').strip()
            if note_clean:
                lines.append(f"  {note_clean}")
    else:
        lines.append(f"general_strategy: |")
        lines.append(f"  TODO: Add strategy notes for this fight.")
    
    lines.append(f"")
    
    # Team requirements
    lines.append(f"required_roles:")
    lines.append(f"  - role: breaker")
    lines.append(f"    priority: required")
    lines.append(f"    reason: \"Break to deal damage and control fight\"")
    lines.append(f"  - role: dps")
    lines.append(f"    priority: required")
    lines.append(f"    reason: \"Deal damage during break windows\"")
    
    # Recommended weakness coverage
    elements = [w for w in main_enemy.weaknesses if w in ['fire', 'ice', 'lightning', 'wind', 'light', 'dark']]
    weapons = [w for w in main_enemy.weaknesses if w in ['sword', 'polearm', 'dagger', 'axe', 'bow', 'staff', 'tome', 'fan']]
    
    lines.append(f"")
    if weapons or elements:
        lines.append(f"recommended_weakness_coverage:")
        for w in weapons + elements:
            lines.append(f"  - {w}")
    else:
        lines.append(f"recommended_weakness_coverage: []  # No weaknesses parsed")
    
    lines.append(f"")
    
    # Metadata
    lines.append(f"# ===========================================================================")
    lines.append(f"# METADATA")
    lines.append(f"# ===========================================================================")
    lines.append(f"data_confidence: incomplete")
    lines.append(f"data_source: \"Community Spreadsheet (Wigglytuff)\"")
    lines.append(f"last_updated: {today}")
    
    return '\n'.join(lines)


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
    rank1 = fight.variants.get('rank1')
    rank1_main = rank1.enemies[0] if rank1 and rank1.enemies else None
    
    # Calculate scaling from rank1
    hp_multiplier = 1.0
    if rank1_main and rank1_main.hp > 0:
        hp_multiplier = main_enemy.hp / rank1_main.hp
    
    # Determine actions per turn based on EX rank
    actions_per_turn = 2 if ex_rank in ['ex1', 'ex2'] else 3
    
    ex_display = ex_rank.upper()
    
    lines = []
    lines.append(f"# Adversary Log Boss: {fight.fight_name.replace(chr(10), ' ')} {ex_display}")
    lines.append(f"# SOURCE: Community Spreadsheet (Wigglytuff)")
    lines.append(f"#")
    lines.append(f"# {ex_display} variant with increased stats and difficulty.")
    lines.append(f"")
    lines.append(f"id: {boss_id}")
    lines.append(f'display_name: "{main_enemy.name} {ex_display}"')
    lines.append(f"content_type: adversary_log")
    lines.append(f"difficulty: extreme")
    lines.append(f"location: \"Adversary Log (宿敵の写記)\"")
    lines.append(f"")
    
    # EX variant info (RAG-critical fields!)
    lines.append(f"# ===========================================================================")
    lines.append(f"# EX VARIANT INFO")
    lines.append(f"# ===========================================================================")
    lines.append(f"base_boss_id: {base_boss_id}")
    lines.append(f"ex_rank: {ex_rank}")
    lines.append(f"actions_per_turn: {actions_per_turn}")
    lines.append(f"provoke_immunity: true  # Most EX bosses are provoke immune")
    lines.append(f"")
    
    # Stats (actual values for RAG indexing)
    lines.append(f"# ===========================================================================")
    lines.append(f"# {ex_display} STATS")
    lines.append(f"# ===========================================================================")
    lines.append(f"level: {main_enemy.level}")
    lines.append(f"shield_count: {main_enemy.shields}")
    lines.append(f"hp: {main_enemy.hp}  # ~{hp_multiplier:.1f}x base")
    lines.append(f"speed: {main_enemy.speed}")
    lines.append(f"p_atk: {main_enemy.p_atk}")
    lines.append(f"p_def: {main_enemy.p_def}")
    lines.append(f"e_atk: {main_enemy.e_atk}")
    lines.append(f"e_def: {main_enemy.e_def}")
    lines.append(f"")
    
    # Weaknesses
    lines.extend(format_weaknesses_yaml(main_enemy.weaknesses))
    
    # Multi-enemy for EX
    if fight.is_multi_enemy and len(variant.enemies) > 1:
        lines.append(f"")
        lines.append(f"# ===========================================================================")
        lines.append(f"# MULTI-ENEMY ENCOUNTER ({ex_display})")
        lines.append(f"# ===========================================================================")
        lines.append(f"enemies:")
        for idx, enemy in enumerate(variant.enemies):
            lines.append(f"  - name: \"{enemy.name}\"")
            if idx == 0:
                lines.append(f"    is_main_target: true")
            lines.append(f"    shield_count: {enemy.shields}")
            lines.append(f"    hp: {enemy.hp}")
            lines.append(f"    speed: {enemy.speed}")
            lines.extend([f"  {line}" for line in format_weaknesses_yaml(enemy.weaknesses, indent=1)])
            lines.append(f"")
    
    # Strategy (EX-specific)
    lines.append(f"")
    lines.append(f"# ===========================================================================")
    lines.append(f"# STRATEGY ({ex_display} SPECIFIC)")
    lines.append(f"# ===========================================================================")
    
    # Generate EX-specific strategy based on rank
    if ex_rank == 'ex1':
        lines.append(f"general_strategy: |")
        lines.append(f"  {ex_display} variant with ~{hp_multiplier:.0f}x HP.")
        lines.append(f"  ")
        lines.append(f"  Key changes from base:")
        lines.append(f"  - Higher HP ({main_enemy.hp:,})")
        lines.append(f"  - Higher shield count ({main_enemy.shields})")
        lines.append(f"  - Higher speed ({main_enemy.speed})")
        lines.append(f"  - {actions_per_turn} actions per turn")
        lines.append(f"  ")
        lines.append(f"  Recommended HP per character: 3000+")
    elif ex_rank == 'ex2':
        lines.append(f"general_strategy: |")
        lines.append(f"  {ex_display} variant with ~{hp_multiplier:.0f}x HP.")
        lines.append(f"  ")
        lines.append(f"  Key changes from base:")
        lines.append(f"  - Much higher HP ({main_enemy.hp:,})")
        lines.append(f"  - Higher shield count ({main_enemy.shields})")
        lines.append(f"  - Much higher speed ({main_enemy.speed})")
        lines.append(f"  - {actions_per_turn} actions per turn")
        lines.append(f"  ")
        lines.append(f"  CRITICAL:")
        lines.append(f"  - Stack all 5 damage multiplier categories")
        lines.append(f"  - Speed tuning required for debuffers")
        lines.append(f"  - Consider dodge tank (H'aanit EX, Canary)")
        lines.append(f"  ")
        lines.append(f"  Recommended HP per character: 3500+")
    else:  # ex3
        lines.append(f"general_strategy: |")
        lines.append(f"  {ex_display} variant - MAXIMUM DIFFICULTY.")
        lines.append(f"  ")
        lines.append(f"  Key changes from base:")
        lines.append(f"  - Extreme HP ({main_enemy.hp:,})")
        lines.append(f"  - Maximum shield count ({main_enemy.shields})")
        lines.append(f"  - Very high speed ({main_enemy.speed})")
        lines.append(f"  - {actions_per_turn} actions per turn from early fight")
        lines.append(f"  ")
        lines.append(f"  CRITICAL:")
        lines.append(f"  - Either speedkill (Solon + Primrose EX) or full turtle")
        lines.append(f"  - Stack all buff/debuff categories to 30%")
        lines.append(f"  - Fiore EX Cover or dodge tank essential")
        lines.append(f"  - May take 50-100+ turns without optimal setup")
        lines.append(f"  ")
        lines.append(f"  Recommended HP per character: 4000+")
    
    # Add fight notes if available
    if fight.notes:
        lines.append(f"  ")
        lines.append(f"  Fight notes:")
        for note in fight.notes:
            note_clean = note.replace('\n', ' ').strip()
            if note_clean:
                lines.append(f"  - {note_clean}")
    
    lines.append(f"")
    
    # Required roles
    lines.append(f"required_roles:")
    lines.append(f"  - role: debuffer")
    lines.append(f"    priority: required")
    lines.append(f"    reason: \"Stack attack debuffs (30% cap)\"")
    lines.append(f"  - role: healer")
    lines.append(f"    priority: required")
    lines.append(f"    reason: \"Survive multi-action turns\"")
    lines.append(f"  - role: dps")
    lines.append(f"    priority: required")
    lines.append(f"    reason: \"Deal damage during break windows\"")
    if ex_rank in ['ex2', 'ex3']:
        lines.append(f"  - role: tank")
        lines.append(f"    priority: strongly_recommended")
        lines.append(f"    reason: \"Fiore EX Cover or dodge tank for survival\"")
    
    # Recommended weakness coverage
    elements = [w for w in main_enemy.weaknesses if w in ['fire', 'ice', 'lightning', 'wind', 'light', 'dark']]
    weapons = [w for w in main_enemy.weaknesses if w in ['sword', 'polearm', 'dagger', 'axe', 'bow', 'staff', 'tome', 'fan']]
    
    lines.append(f"")
    if weapons or elements:
        lines.append(f"recommended_weakness_coverage:")
        for w in weapons + elements:
            lines.append(f"  - {w}")
    else:
        lines.append(f"recommended_weakness_coverage: []  # No weaknesses parsed")
    
    lines.append(f"")
    
    # Metadata
    lines.append(f"# ===========================================================================")
    lines.append(f"# METADATA")
    lines.append(f"# ===========================================================================")
    lines.append(f"data_confidence: incomplete")
    lines.append(f"data_source: \"Community Spreadsheet (Wigglytuff)\"")
    lines.append(f"last_updated: {today}")
    
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description="Import Adversary Log bosses from CSV")
    parser.add_argument('--dry-run', action='store_true', help="Print what would be created")
    parser.add_argument('--overwrite', action='store_true', help="Overwrite existing files")
    args = parser.parse_args()
    
    # Paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    resources_dir = project_root / "resources" / "Adversary Log"
    output_dir = project_root / "data" / "bosses"
    
    if not resources_dir.exists():
        print(f"Error: Resources directory not found: {resources_dir}")
        return
    
    # Arena bosses that already exist (skip these)
    existing_arena_bosses = {
        'tikilen', 'glossom', 'varkyn', 'ritu', 'ri\'tu', 'gertrude',
        'yan long', 'yan-long', 'yunnie', 'largo', 'aoi', 'kagemune', 'mirgardi'
    }
    
    # CSV files to parse
    csv_files = [
        ("EN OT_ COTC _ Adversary Log Enemy Index - Lv. 1~.csv", "1"),
        ("EN OT_ COTC _ Adversary Log Enemy Index - Lv. 25~.csv", "25"),
        ("EN OT_ COTC _ Adversary Log Enemy Index - Lv. 50~.csv", "50"),
        ("EN OT_ COTC _ Adversary Log Enemy Index - Lv. 75~.csv", "75"),
    ]
    
    notes_files = [
        "EN OT_ COTC _ Adversary Log Enemy Index - Lv. 1~ Fight Notes.csv",
        "EN OT_ COTC _ Adversary Log Enemy Index - Lv. 50~ Fight Notes.csv",
        "EN OT_ COTC _ Adversary Log Enemy Index - Lv. 75~ Fight Notes.csv",
    ]
    
    # Parse all notes first
    all_notes = {}
    for notes_file in notes_files:
        notes_path = resources_dir / notes_file
        if notes_path.exists():
            file_notes = parse_notes_file(notes_path)
            all_notes.update(file_notes)
    
    # Parse all CSV files
    all_fights = []
    for csv_file, level_tier in csv_files:
        csv_path = resources_dir / csv_file
        if not csv_path.exists():
            print(f"Warning: CSV file not found: {csv_path}")
            continue
        
        print(f"Parsing: {csv_file}")
        fights = parse_csv_file(csv_path, level_tier)
        
        # Attach notes
        for fight in fights:
            if fight.fight_name in all_notes:
                fight.notes = all_notes[fight.fight_name]
        
        all_fights.extend(fights)
        print(f"  Found {len(fights)} fights")
    
    print(f"\nTotal fights found: {len(all_fights)}")
    
    # Generate YAML files
    base_created = 0
    ex_created = 0
    skipped = 0
    skipped_arena = 0
    skipped_invalid = 0
    
    for fight in all_fights:
        if not fight.variants:
            continue
        
        base_boss_id = generate_boss_id(fight.fight_name)
        
        # Skip empty IDs
        if base_boss_id == 'adversary-' or not base_boss_id or base_boss_id == 'adversary':
            print(f"  Skip (invalid ID): '{fight.fight_name}'")
            skipped_invalid += 1
            continue
        
        # Skip existing arena bosses
        fight_name_lower = fight.fight_name.lower()
        if any(arena_boss in fight_name_lower for arena_boss in existing_arena_bosses):
            print(f"  Skip (arena exists): {base_boss_id}")
            skipped_arena += 1
            continue
        
        # 1. Generate BASE file (Rank 1-3)
        base_path = output_dir / f"{base_boss_id}.yaml"
        
        if 'rank1' in fight.variants:
            if base_path.exists() and not args.overwrite:
                print(f"  Skip (file exists): {base_boss_id}")
                skipped += 1
            else:
                yaml_content = generate_base_yaml(fight)
                if yaml_content:
                    if args.dry_run:
                        print(f"  Would create BASE: {base_boss_id}")
                        ranks = [k for k in fight.variants.keys() if k.startswith('rank')]
                        print(f"    Ranks: {ranks}")
                    else:
                        with open(base_path, 'w', encoding='utf-8') as f:
                            f.write(yaml_content)
                        print(f"  Created BASE: {base_boss_id}")
                    base_created += 1
        
        # 2. Generate EX variant files (separate files!)
        for ex_rank in ['ex1', 'ex2', 'ex3']:
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
                            with open(ex_path, 'w', encoding='utf-8') as f:
                                f.write(yaml_content)
                            print(f"  Created {ex_rank.upper()}: {ex_boss_id}")
                        ex_created += 1
    
    print(f"\nSummary:")
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
