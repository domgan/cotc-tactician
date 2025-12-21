#!/usr/bin/env python3
"""
Import skills and passives from Notion markdown exports.

This script parses markdown files from 'resources/Character List/' and updates
the corresponding YAML files in 'data/characters/' with skill/passive data.

Usage:
    python scripts/import_skills_from_markdown.py
    python scripts/import_skills_from_markdown.py --dry-run
    python scripts/import_skills_from_markdown.py --character richard
"""

import re
import argparse
from pathlib import Path
from datetime import date


def extract_character_name(filename: str) -> str:
    """Extract character name from filename like 'Richard 2d02a61823198175b9bad46cb9f01d6d.md'"""
    # Remove .md extension and hash
    name = re.sub(r'\s+[a-f0-9]{32}\.md$', '', filename)
    return name


def create_character_id(name: str) -> str:
    """Create a safe ID from character name."""
    id_str = name.lower()
    id_str = re.sub(r"[''`]", "", id_str)
    id_str = re.sub(r"[^a-z0-9]+", "-", id_str)
    id_str = re.sub(r"-+", "-", id_str)
    id_str = id_str.strip("-")
    return id_str


def clean_html_tags(text: str) -> str:
    """Remove HTML tags and Notion artifacts from text."""
    # Remove <aside> and </aside> tags
    text = re.sub(r'</?aside[^>]*>', '', text)
    # Remove <img> tags
    text = re.sub(r'<img[^>]*>', '', text)
    # Remove Notion links like ([✦](https://...))
    text = re.sub(r'\(\[✦\]\([^)]+\)\)', '', text)
    # Clean up extra whitespace and newlines
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def parse_skill_tier(text: str) -> tuple[str, bool]:
    """
    Parse skill tier from text like '(1★)', '(3★)', '([✦]...)', '(6★)'
    Returns (category, is_limit_break_upgrade)
    """
    if '6★' in text:
        return 'active', True  # This is a limit break upgrade
    if '[✦]' in text or '✦' in text:
        return 'tp', False
    # Regular star ratings are just board positions - all are 'active'
    if re.search(r'\d★', text):
        return 'active', False
    return 'active', False


def parse_sp_cost(text: str) -> int | None:
    """Extract SP cost from text like '[38 SP]'"""
    match = re.search(r'\[(\d+)\s*SP\]', text)
    if match:
        return int(match.group(1))
    return None


def parse_potency(text: str) -> str | None:
    """Extract potency from text like '(potency: 3x65)' or '(potency: 230)'"""
    match = re.search(r'\(potency:\s*([^)]+)\)', text)
    if match:
        return match.group(1).strip()
    return None


def parse_hit_count(text: str) -> str | None:
    """Extract hit count from text like '3 time(s)'"""
    match = re.search(r'(\d+)\s*time\(s\)', text)
    if match:
        return f"{match.group(1)}x"
    return None


def parse_damage_type(text: str) -> list[str]:
    """Extract damage types from skill description."""
    types = []
    
    # Physical weapon damage
    weapon_patterns = [
        (r'Phys\.\s*Sword\s*damage', 'sword'),
        (r'Phys\.\s*Polearm\s*damage', 'polearm'),
        (r'Phys\.\s*Dagger\s*damage', 'dagger'),
        (r'Phys\.\s*Axe\s*damage', 'axe'),
        (r'Phys\.\s*Bow\s*damage', 'bow'),
        (r'Phys\.\s*Staff\s*damage', 'staff'),
        (r'Phys\.\s*Fan\s*damage', 'fan'),
    ]
    
    # Elemental damage
    element_patterns = [
        (r'Elem\.\s*Fire\s*damage', 'fire'),
        (r'Elem\.\s*Ice\s*damage', 'ice'),
        (r'Elem\.\s*Lightning\s*damage', 'lightning'),
        (r'Elem\.\s*Wind\s*damage', 'wind'),
        (r'Elem\.\s*Light\s*damage', 'light'),
        (r'Elem\.\s*Dark\s*damage', 'dark'),
    ]
    
    for pattern, dtype in weapon_patterns + element_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            types.append(dtype)
    
    # Check for "Exploits X weakness"
    exploit_match = re.search(r'Exploits?\s+(\w+)\s+weakness', text, re.IGNORECASE)
    if exploit_match:
        weakness = exploit_match.group(1).lower()
        if weakness not in types:
            types.append(weakness)
    
    return types


def parse_target(text: str) -> str:
    """Extract target type from skill description."""
    text_lower = text.lower()
    
    if 'entire front row' in text_lower or 'front row' in text_lower:
        return 'front_row'
    if 'entire back row' in text_lower or 'back row' in text_lower:
        return 'back_row'
    if 'all foes' in text_lower:
        return 'aoe'
    if 'random foe' in text_lower:
        return 'random'
    if 'single foe' in text_lower:
        return 'single_enemy'
    if 'paired all' in text_lower:
        return 'paired_ally'
    if 'all allies' in text_lower:
        return 'all_allies'
    if 'single ally' in text_lower:
        return 'single_ally'
    if ' self' in text_lower:
        return 'self'
    
    return 'single_enemy'


def determine_skill_type(text: str) -> str:
    """Determine skill type from description."""
    text_lower = text.lower()
    
    # Check for damage dealing
    has_damage = 'damage' in text_lower and ('potency' in text_lower or 'phys.' in text_lower or 'elem.' in text_lower)
    
    # Check for buffs
    has_buff = any(kw in text_lower for kw in ['raise', 'up %', 'up', 'grant', 'impart']) and 'foe' not in text_lower
    
    # Check for debuffs
    has_debuff = any(kw in text_lower for kw in ['lower', 'down', 'impart']) and 'foe' in text_lower
    
    # Check for healing
    has_heal = 'restore hp' in text_lower or 'restore sp' in text_lower or 'cure' in text_lower
    
    if has_damage and (has_buff or has_debuff or has_heal):
        return 'mixed'
    if has_damage:
        return 'attack'
    if has_heal:
        return 'heal'
    if has_buff:
        return 'buff'
    if has_debuff:
        return 'debuff'
    
    return 'utility'


def extract_effects(text: str) -> list[str]:
    """Extract buff/debuff effects from skill description."""
    effects = []
    
    # Clean text first
    text = clean_html_tags(text)
    
    # Look for key effect phrases and extract the full clause
    # Split by common delimiters while preserving content
    effect_keywords = [
        'raise', 'lower', 'grant', 'impart', 'restore', 
        'guaranteed critical', 'act faster', 'dead aim'
    ]
    
    # Find clauses containing effect keywords
    clauses = re.split(r'(?:,\s*(?=and\s)|(?<!\d),\s+|\.\s+)', text)
    
    for clause in clauses:
        clause_lower = clause.lower()
        for keyword in effect_keywords:
            if keyword in clause_lower:
                # Clean and add the clause
                effect = clause.strip().rstrip('.,')
                if effect and len(effect) > 10 and effect not in effects:
                    effects.append(effect)
                break
    
    return effects


def parse_level_upgrades(text: str) -> dict:
    """Parse level upgrades like 'Lv.88 | Potency Up: 80→95'"""
    upgrades = {}
    
    # Find all level upgrade lines
    pattern = r'\*\*Lv\.(\d+)\s*\|\*\*\s*(.+?)(?=\n|$)'
    matches = re.findall(pattern, text)
    
    for level, effect in matches:
        upgrades[int(level)] = effect.strip()
    
    return upgrades


def parse_aside_block(text: str) -> dict | None:
    """Parse a single <aside> block containing a skill or passive."""
    result = {}
    
    # Extract skill/passive name - pattern: **Name** or **Name (X★)**
    name_match = re.search(r'\*\*([^*]+(?:\([^)]+\))?)\*\*', text)
    if not name_match:
        return None
    
    full_name = name_match.group(1).strip()
    
    # Clean Notion link artifacts from name
    full_name = re.sub(r'\s*\(\[✦\]\([^)]+\)\)', '', full_name).strip()
    
    # Parse tier from name
    tier_match = re.search(r'\((\d★|6★|\[✦\][^)]*)\)$', full_name)
    if tier_match:
        tier_str = tier_match.group(1)
        category, is_6star = parse_skill_tier(tier_str)
        name = re.sub(r'\s*\([^)]+\)$', '', full_name).strip()
    else:
        category = 'active'
        is_6star = False
        name = full_name
    
    # Check if this is a TP skill (has ✦ marker)
    if '[✦]' in text and category != 'tp':
        category = 'tp'
    
    result['name'] = name
    result['is_6star_upgrade'] = is_6star
    result['category'] = category
    
    # Get description (everything after the name until SP cost or end)
    desc_start = text.find('**', text.find('**') + 2)
    if desc_start != -1:
        desc_end = text.find('[', desc_start)  # SP cost marker
        if desc_end == -1:
            desc_end = len(text)
        description = text[desc_start + 2:desc_end].strip()
        # Clean HTML artifacts
        description = clean_html_tags(description)
        result['description'] = description
    
    # SP cost
    sp_cost = parse_sp_cost(text)
    if sp_cost:
        result['sp_cost'] = sp_cost
    
    # Potency
    potency = parse_potency(text)
    if potency:
        result['power'] = potency
    
    # Hit count
    hit_count = parse_hit_count(text)
    if hit_count:
        result['hit_count'] = hit_count
    
    # Damage types
    damage_types = parse_damage_type(text)
    if damage_types:
        result['damage_types'] = damage_types
    
    # Target
    result['target'] = parse_target(text)
    
    # Skill type
    result['skill_type'] = determine_skill_type(text)
    
    # Effects
    effects = extract_effects(text)
    if effects:
        result['effects'] = effects
    
    # Level upgrades
    upgrades = parse_level_upgrades(text)
    if upgrades:
        result['level_upgrades'] = upgrades
    
    return result


def parse_passives_section(content: str) -> list[dict]:
    """Parse the Passive Skills section."""
    passives = []
    
    # Find passive skills section
    match = re.search(r'## Passive Skills\s*(.*?)(?=##|$)', content, re.DOTALL)
    if not match:
        return passives
    
    section = match.group(1)
    
    # Split by <aside> blocks
    aside_blocks = re.split(r'<aside>', section)
    
    current_passive = None
    
    for block in aside_blocks:
        if not block.strip():
            continue
        
        parsed = parse_aside_block(block)
        if not parsed:
            continue
        
        # Clean description
        description = clean_html_tags(parsed.get('description', parsed.get('name', '')))
        
        # Check if this is a 6★ upgrade of previous passive
        if parsed.get('is_6star_upgrade') and current_passive:
            current_passive['limit_break_upgrade'] = description
            continue
        
        passive = {
            'passive_category': 'tp' if parsed.get('category') == 'tp' else 'innate',
            'effect': description,
        }
        
        # Determine trigger
        desc_lower = description.lower()
        if 'start of battle' in desc_lower or 'at the start' in desc_lower:
            passive['trigger'] = 'battle_start'
        elif 'at full hp' in desc_lower or 'at max hp' in desc_lower:
            passive['trigger'] = 'hp_condition'
        elif 'when breaking' in desc_lower:
            passive['trigger'] = 'on_break'
        else:
            passive['trigger'] = 'always'
        
        passives.append(passive)
        current_passive = passive
    
    return passives


def parse_skills_section(content: str) -> list[dict]:
    """Parse the Battle Skills section."""
    skills = []
    
    # Find battle skills section
    match = re.search(r'## Battle Skills\s*(.*?)(?=## Ultimate|## EX|$)', content, re.DOTALL)
    if not match:
        return skills
    
    section = match.group(1)
    
    # Split by <aside> blocks
    aside_blocks = re.split(r'<aside>', section)
    
    current_skill = None
    
    for block in aside_blocks:
        if not block.strip():
            continue
        
        parsed = parse_aside_block(block)
        if not parsed:
            continue
        
        # Check if this is a 6★ upgrade of previous skill
        if parsed.get('is_6star_upgrade') and current_skill:
            upgrade_desc = parsed.get('description', '')
            # Try to extract the key difference
            if upgrade_desc:
                current_skill['limit_break_upgrade'] = upgrade_desc
            continue
        
        skill = {
            'skill_category': parsed.get('category', 'active'),
            'name': parsed.get('name', ''),
            'skill_type': parsed.get('skill_type', 'attack'),
            'target': parsed.get('target', 'single_enemy'),
        }
        
        if parsed.get('sp_cost'):
            skill['sp_cost'] = parsed['sp_cost']
        
        if parsed.get('hit_count'):
            skill['hit_count'] = parsed['hit_count']
        
        if parsed.get('power'):
            skill['power'] = parsed['power']
        
        if parsed.get('damage_types'):
            skill['damage_types'] = parsed['damage_types']
        
        if parsed.get('effects'):
            skill['effects'] = parsed['effects']
        
        skills.append(skill)
        current_skill = skill
    
    return skills


def parse_ex_skill(content: str) -> dict | None:
    """Parse the EX skill section."""
    match = re.search(r'## EX skill\s*(.*?)(?=## Awakening|## Misc|$)', content, re.DOTALL)
    if not match:
        return None
    
    section = match.group(1)
    
    # Find the main aside block
    aside_match = re.search(r'<aside>(.*?)</aside>', section, re.DOTALL)
    if not aside_match:
        return None
    
    block = aside_match.group(1)
    parsed = parse_aside_block(block)
    if not parsed:
        return None
    
    skill = {
        'skill_category': 'ex',
        'name': parsed.get('name', ''),
        'skill_type': parsed.get('skill_type', 'attack'),
        'target': parsed.get('target', 'single_enemy'),
    }
    
    if parsed.get('hit_count'):
        skill['hit_count'] = parsed['hit_count']
    
    if parsed.get('power'):
        skill['power'] = parsed['power']
    
    if parsed.get('damage_types'):
        skill['damage_types'] = parsed['damage_types']
    
    if parsed.get('effects'):
        skill['effects'] = parsed['effects']
    
    # Extract usage condition
    condition_match = re.search(r'Usage Condition:\s*(.+?)(?=</aside>|$)', section)
    if condition_match:
        skill['ex_trigger'] = condition_match.group(1).strip()
    
    # Extract uses count
    uses_match = re.search(r'Uses\s*:\s*(\d+)', section)
    if uses_match:
        skill['notes'] = f"Uses: {uses_match.group(1)}"
    
    return skill


def parse_ultimate(content: str) -> dict | None:
    """Parse the Ultimate Technique section."""
    match = re.search(r'## Ultimate Technique\s*(.*?)(?=## EX|## Awakening|$)', content, re.DOTALL)
    if not match:
        return None
    
    section = match.group(1)
    
    # Find the main aside block with skill name
    name_match = re.search(r'\*\*([^*]+)\*\*', section)
    if not name_match:
        return None
    
    name = name_match.group(1).strip()
    # Remove (Lv. X→Y) from name
    name = re.sub(r'\s*\(Lv\.[^)]+\)', '', name).strip()
    
    # Get description
    desc_match = re.search(r'\*\*[^*]+\*\*\s*(.+?)(?=<aside>|---|\n\n)', section, re.DOTALL)
    description = desc_match.group(1).strip() if desc_match else ''
    
    skill = {
        'skill_category': 'special',
        'name': name,
        'skill_type': determine_skill_type(description),
        'target': parse_target(description),
    }
    
    # Potency - often shows scaling like "500→600→750"
    potency_match = re.search(r'\*\*(\d+(?:→\d+)+)\*\*', section)
    if potency_match:
        skill['power'] = potency_match.group(1)
    
    hit_count = parse_hit_count(description)
    if hit_count:
        skill['hit_count'] = hit_count
    
    damage_types = parse_damage_type(description)
    if damage_types:
        skill['damage_types'] = damage_types
    
    effects = extract_effects(description)
    if effects:
        skill['effects'] = effects
    
    return skill


def parse_a4_accessory(content: str) -> dict | None:
    """Parse the Awakening IV Accessory section."""
    match = re.search(r'## Awakening IV Accessory\s*(.*?)(?=## Exclusive|## Misc|$)', content, re.DOTALL)
    if not match:
        return None
    
    section = match.group(1)
    
    # Extract name
    name_match = re.search(r'\*\*([^*]+)\*\*', section)
    if not name_match:
        return None
    
    name = name_match.group(1).strip()
    
    # Extract effects (lines starting with ·)
    effects = re.findall(r'·([^\n]+)', section)
    effect_str = '; '.join(e.strip() for e in effects)
    
    return {
        'name': name,
        'passive_effect': effect_str,
    }


def parse_markdown_file(filepath: Path) -> dict:
    """Parse a character markdown file."""
    content = filepath.read_text(encoding='utf-8')
    
    result = {
        'name': extract_character_name(filepath.name),
        'passives': parse_passives_section(content),
        'skills': parse_skills_section(content),
    }
    
    ex_skill = parse_ex_skill(content)
    if ex_skill:
        result['skills'].append(ex_skill)
    
    ultimate = parse_ultimate(content)
    if ultimate:
        result['skills'].append(ultimate)
    
    a4 = parse_a4_accessory(content)
    if a4:
        result['a4_accessory'] = a4
    
    return result


def update_yaml_file(yaml_path: Path, parsed_data: dict, dry_run: bool = False) -> bool:
    """Update a YAML file with parsed skill data."""
    if not yaml_path.exists():
        print(f"  SKIP: No YAML file found at {yaml_path}")
        return False
    
    # Read existing YAML
    content = yaml_path.read_text(encoding='utf-8')
    
    # Parse YAML while preserving comments
    lines = content.split('\n')
    
    # Find key sections
    skills_line_idx = None
    metadata_line_idx = None
    
    for i, line in enumerate(lines):
        # Look for the actual skills: YAML key (not just comments mentioning skills)
        if line.startswith('skills:'):
            skills_line_idx = i
        elif '# Metadata' in line or line.startswith('data_confidence:'):
            if metadata_line_idx is None:
                metadata_line_idx = i
    
    if skills_line_idx is None:
        print(f"  SKIP: No skills section found in {yaml_path}")
        return False
    
    # Build new content: everything up to skills section
    # But skip skills-related comment lines just before the skills: key
    new_lines = []
    for i, line in enumerate(lines):
        if i >= skills_line_idx:
            break
        # Skip skill comment lines that appear right before skills:
        if i >= skills_line_idx - 2 and '# Skills' in line:
            continue
        new_lines.append(line)
    
    # Add skills header and skills
    new_lines.append("# Skills - parsed from markdown")
    new_lines.append("skills:")
    if parsed_data.get('skills'):
        for skill in parsed_data['skills']:
            new_lines.append(f"  - skill_category: {skill.get('skill_category', 'active')}")
            if skill.get('name'):
                new_lines.append(f"    name: \"{skill['name']}\"")
            if skill.get('sp_cost'):
                new_lines.append(f"    sp_cost: {skill['sp_cost']}")
            new_lines.append(f"    skill_type: {skill.get('skill_type', 'attack')}")
            if skill.get('damage_types'):
                new_lines.append(f"    damage_types: [{', '.join(skill['damage_types'])}]")
            new_lines.append(f"    target: {skill.get('target', 'single_enemy')}")
            if skill.get('hit_count'):
                new_lines.append(f"    hit_count: \"{skill['hit_count']}\"")
            if skill.get('power'):
                new_lines.append(f"    power: \"{skill['power']}\"")
            if skill.get('effects'):
                new_lines.append("    effects:")
                for effect in skill['effects']:
                    effect_escaped = effect.replace('"', '\\"')
                    new_lines.append(f"      - \"{effect_escaped}\"")
            if skill.get('ex_trigger'):
                new_lines.append(f"    ex_trigger: \"{skill['ex_trigger']}\"")
            if skill.get('limit_break_upgrade'):
                new_lines.append(f"    limit_break_upgrade: \"{skill['limit_break_upgrade']}\"")
            if skill.get('notes'):
                new_lines.append(f"    notes: \"{skill['notes']}\"")
    else:
        new_lines.append("  []")
    
    # Add passives section
    new_lines.append("")
    new_lines.append("# Passives - parsed from markdown")
    new_lines.append("passives:")
    if parsed_data.get('passives'):
        for passive in parsed_data['passives']:
            new_lines.append(f"  - passive_category: {passive.get('passive_category', 'innate')}")
            effect = passive.get('effect', '').replace('"', '\\"')
            new_lines.append(f"    effect: \"{effect}\"")
            if passive.get('trigger'):
                new_lines.append(f"    trigger: {passive['trigger']}")
            if passive.get('limit_break_upgrade'):
                upgrade = passive['limit_break_upgrade'].replace('"', '\\"')
                new_lines.append(f"    limit_break_upgrade: \"{upgrade}\"")
    else:
        new_lines.append("  []")
    
    # Add A4 accessory if present
    if parsed_data.get('a4_accessory'):
        new_lines.append("")
        new_lines.append("# A4 Accessory - parsed from markdown")
        new_lines.append("a4_accessory:")
        new_lines.append(f"  name: \"{parsed_data['a4_accessory']['name']}\"")
        effect = parsed_data['a4_accessory']['passive_effect'].replace('"', '\\"')
        new_lines.append(f"  passive_effect: \"{effect}\"")
    
    # Add remaining content (metadata section)
    # Find where metadata starts
    for i, line in enumerate(lines):
        if '# Metadata' in line or 'data_confidence:' in line:
            new_lines.append("")
            new_lines.extend(lines[i:])
            break
    
    new_content = '\n'.join(new_lines)
    
    if dry_run:
        print(f"  WOULD UPDATE: {yaml_path.name}")
        return True
    
    yaml_path.write_text(new_content, encoding='utf-8')
    print(f"  UPDATED: {yaml_path.name}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Import skills from markdown to YAML")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done")
    parser.add_argument("--character", type=str, help="Process only this character")
    parser.add_argument("--limit", type=int, help="Limit number of characters to process")
    args = parser.parse_args()
    
    project_root = Path(__file__).parent.parent
    md_dir = project_root / "resources" / "Character List"
    yaml_dir = project_root / "data" / "characters"
    
    if not md_dir.exists():
        print(f"ERROR: Markdown directory not found: {md_dir}")
        return 1
    
    # Get all markdown files (excluding star rating files)
    md_files = sorted(md_dir.glob("*.md"))
    md_files = [f for f in md_files if not f.name.startswith(('3 Stars', '4 Stars', '5 Stars'))]
    
    print(f"Found {len(md_files)} character markdown files")
    
    if args.character:
        md_files = [f for f in md_files if args.character.lower() in f.name.lower()]
        print(f"Filtered to {len(md_files)} files matching '{args.character}'")
    
    if args.limit:
        md_files = md_files[:args.limit]
        print(f"Limited to first {args.limit} files")
    
    updated = 0
    skipped = 0
    errors = 0
    
    for md_file in md_files:
        char_name = extract_character_name(md_file.name)
        char_id = create_character_id(char_name)
        yaml_path = yaml_dir / f"{char_id}.yaml"
        
        try:
            parsed = parse_markdown_file(md_file)
            
            if not parsed.get('skills') and not parsed.get('passives'):
                print(f"  SKIP: {char_name} - no skills/passives found")
                skipped += 1
                continue
            
            success = update_yaml_file(yaml_path, parsed, dry_run=args.dry_run)
            if success:
                updated += 1
            else:
                skipped += 1
                
        except Exception as e:
            print(f"  ERROR: {char_name} - {e}")
            errors += 1
    
    print(f"\nSummary:")
    print(f"  Updated: {updated}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors: {errors}")
    
    return 0


if __name__ == "__main__":
    exit(main())
