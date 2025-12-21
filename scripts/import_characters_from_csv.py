#!/usr/bin/env python3
"""
Import characters from community CSV export to YAML files.

This script reads the exported "Character List all.csv" and generates
YAML files for each character in data/characters/.

Usage:
    python scripts/import_characters_from_csv.py

The script will:
1. Read the CSV file from resources/Character List all.csv
2. Generate YAML files in data/characters/
3. Skip characters that already have YAML files (unless --overwrite is passed)

Note: This only imports the BASE data from CSV. Skills, passives, and detailed
role information must still be added manually from other sources.
"""

import csv
import re
import argparse
from pathlib import Path
from datetime import date


def parse_rarity(class_field: str) -> int:
    """Parse rarity from star emoji field."""
    star_count = class_field.count('⭐️')
    if star_count == 0:
        # Fallback: count any star-like characters
        star_count = len(class_field) // 2 if class_field else 5
    return max(3, min(5, star_count))


def parse_weakness_coverage(weakness_str: str) -> list[str]:
    """Parse 'Weakness to hit' field into normalized list."""
    if not weakness_str:
        return []
    
    # Normalize weapon/element names
    name_map = {
        'polearm': 'polearm',
        'spear': 'polearm',  # Alias
        'lightning': 'lightning',
        'thunder': 'lightning',  # Alias
    }
    
    items = [w.strip().lower() for w in weakness_str.split(',')]
    normalized = []
    for item in items:
        normalized.append(name_map.get(item, item))
    
    return normalized


def parse_influence(influence_str: str) -> str:
    """Parse influence field."""
    if not influence_str:
        return ""
    return influence_str.strip().lower()


def parse_job(job_str: str) -> str:
    """Parse job field."""
    if not job_str:
        return ""
    return job_str.strip().lower()


def create_character_id(name: str) -> str:
    """Create a safe ID from character name."""
    # Replace spaces and special chars with hyphens
    id_str = name.lower()
    id_str = re.sub(r"[''`]", "", id_str)  # Remove apostrophes
    id_str = re.sub(r"[^a-z0-9]+", "-", id_str)  # Replace non-alphanumeric
    id_str = re.sub(r"-+", "-", id_str)  # Collapse multiple hyphens
    id_str = id_str.strip("-")
    return id_str


def parse_int_or_none(value: str) -> int | None:
    """Parse integer, returning None for empty/invalid."""
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def bool_from_availability(value: str) -> bool:
    """Check if a feature is available in GL from status string."""
    if not value:
        return False
    return 'available in gl' in value.lower()


def generate_yaml(row: dict) -> str:
    """Generate YAML content for a character row."""
    
    char_id = create_character_id(row['Name'])
    display_name = row['Name']
    rarity = parse_rarity(row.get('Class', ''))
    job = parse_job(row.get('Job', ''))
    influence = parse_influence(row.get('Influence', ''))
    origin = row.get('Continent', '')
    weakness_coverage = parse_weakness_coverage(row.get('Weakness to hit', ''))
    
    # Stats
    hp = parse_int_or_none(row.get('HP', ''))
    hp_120 = parse_int_or_none(row.get('HP (Lv. 120)', ''))
    p_atk = parse_int_or_none(row.get('P.Atk', ''))
    p_atk_120 = parse_int_or_none(row.get('P.Atk (Lv. 120)', ''))
    p_def = parse_int_or_none(row.get('P.Def', ''))
    p_def_120 = parse_int_or_none(row.get('P.Def (Lv. 120)', ''))
    e_atk = parse_int_or_none(row.get('E.Atk', ''))
    e_atk_120 = parse_int_or_none(row.get('E.Atk (Lv. 120)', ''))
    e_def = parse_int_or_none(row.get('E.Def', ''))
    e_def_120 = parse_int_or_none(row.get('E.Def (Lv. 120)', ''))
    spd = parse_int_or_none(row.get('Spd', ''))
    spd_120 = parse_int_or_none(row.get('Spd (Lv. 120)', ''))
    crit = parse_int_or_none(row.get('Crit', ''))
    crit_120 = parse_int_or_none(row.get('Crit (Lv. 120)', ''))
    sp = parse_int_or_none(row.get('SP', ''))
    sp_120 = parse_int_or_none(row.get('SP (Lv. 120)', ''))
    
    # Tier ratings
    gl_tier = row.get('GL Tier', '').strip() or None
    jp_tier = row.get('JP Tier', '').strip() or None
    
    # Progression availability
    has_blessing = bool_from_availability(row.get('Blessing of the Lantern', ''))
    has_limit_break = bool_from_availability(row.get('Class Breakthrough', ''))
    has_overcharge = bool_from_availability(row.get('Overcharge', ''))
    
    # Ultimate priority notes
    ult_priority = row.get('Ultimate Priority', '').strip() or None
    
    # Build YAML
    lines = [
        f"# Character: {display_name}",
        f"# Auto-generated from CSV on {date.today().isoformat()}",
        f"# Skills and passives must be added manually",
        f"",
        f"id: {char_id}",
        f"display_name: \"{display_name}\"",
        f"rarity: {rarity}",
        f"",
        f"# Core attributes",
        f"job: {job}",
    ]
    
    if influence:
        lines.append(f"influence: {influence}")
    
    if origin:
        lines.append(f"origin: \"{origin}\"")
    
    lines.append(f"")
    lines.append(f"# Weakness coverage (what enemy weaknesses this character can hit)")
    if weakness_coverage:
        lines.append(f"weakness_coverage: [{', '.join(weakness_coverage)}]")
    else:
        lines.append(f"weakness_coverage: []")
    
    lines.append(f"")
    lines.append(f"# Roles - [HUMAN-REQUIRED] Must be assigned manually based on skills")
    lines.append(f"roles: []  # TODO: Add roles (tank, healer, buffer, debuffer, breaker, dps)")
    lines.append(f"role_notes: |")
    lines.append(f"  TODO: Describe role capabilities based on skill analysis")
    
    lines.append(f"")
    lines.append(f"# Stats (base level)")
    if hp:
        lines.append(f"hp: {hp}")
    if p_atk:
        lines.append(f"p_atk: {p_atk}")
    if p_def:
        lines.append(f"p_def: {p_def}")
    if e_atk:
        lines.append(f"e_atk: {e_atk}")
    if e_def:
        lines.append(f"e_def: {e_def}")
    if spd:
        lines.append(f"speed: {spd}")
    if crit:
        lines.append(f"crit: {crit}")
    if sp:
        lines.append(f"sp: {sp}")
    
    lines.append(f"")
    lines.append(f"# Stats (Lv 120 after Limit Break)")
    if hp_120:
        lines.append(f"hp_120: {hp_120}")
    if p_atk_120:
        lines.append(f"p_atk_120: {p_atk_120}")
    if p_def_120:
        lines.append(f"p_def_120: {p_def_120}")
    if e_atk_120:
        lines.append(f"e_atk_120: {e_atk_120}")
    if e_def_120:
        lines.append(f"e_def_120: {e_def_120}")
    if spd_120:
        lines.append(f"speed_120: {spd_120}")
    if crit_120:
        lines.append(f"crit_120: {crit_120}")
    if sp_120:
        lines.append(f"sp_120: {sp_120}")
    
    lines.append(f"")
    lines.append(f"# Progression availability (in GL)")
    lines.append(f"has_blessing_of_lantern: {str(has_blessing).lower()}")
    lines.append(f"has_limit_break: {str(has_limit_break).lower()}")
    lines.append(f"awakening_stage: 4  # Assume max for team comp purposes")
    
    lines.append(f"")
    lines.append(f"# Tier ratings (from community)")
    if gl_tier:
        lines.append(f"gl_tier: \"{gl_tier}\"")
    if jp_tier:
        lines.append(f"jp_tier: \"{jp_tier}\"")
    
    lines.append(f"")
    lines.append(f"# Skills - [HUMAN-REQUIRED] Must be added from skill spreadsheet")
    lines.append(f"skills: []")
    
    lines.append(f"")
    lines.append(f"# Passives - [HUMAN-REQUIRED] Must be added from skill spreadsheet")
    lines.append(f"passives: []")
    
    if ult_priority:
        lines.append(f"")
        lines.append(f"# Ultimate priority notes")
        lines.append(f"ultimate_notes: \"{ult_priority}\"")
    
    lines.append(f"")
    lines.append(f"# Metadata")
    lines.append(f"data_confidence: incomplete")
    lines.append(f"data_source: \"Community spreadsheet CSV export\"")
    lines.append(f"last_updated: {date.today().isoformat()}")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Import characters from CSV to YAML")
    parser.add_argument("--overwrite", action="store_true", 
                        help="Overwrite existing YAML files")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be done without writing files")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit number of characters to process")
    args = parser.parse_args()
    
    # Paths
    project_root = Path(__file__).parent.parent
    csv_path = project_root / "resources" / "Character List all.csv"
    output_dir = project_root / "data" / "characters"
    
    if not csv_path.exists():
        print(f"ERROR: CSV file not found: {csv_path}")
        return 1
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Read CSV
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    print(f"Found {len(rows)} characters in CSV")
    
    if args.limit:
        rows = rows[:args.limit]
        print(f"Processing first {args.limit} characters")
    
    created = 0
    skipped = 0
    errors = 0
    
    for row in rows:
        name = row.get('Name', '').strip()
        if not name:
            continue
        
        char_id = create_character_id(name)
        output_path = output_dir / f"{char_id}.yaml"
        
        if output_path.exists() and not args.overwrite:
            print(f"  SKIP: {char_id} (already exists)")
            skipped += 1
            continue
        
        try:
            yaml_content = generate_yaml(row)
            
            if args.dry_run:
                print(f"  WOULD CREATE: {char_id}")
            else:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(yaml_content)
                print(f"  CREATED: {char_id}")
            
            created += 1
        except Exception as e:
            print(f"  ERROR: {char_id} - {e}")
            errors += 1
    
    print(f"\nSummary:")
    print(f"  Created: {created}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors: {errors}")
    
    return 0


if __name__ == "__main__":
    exit(main())
