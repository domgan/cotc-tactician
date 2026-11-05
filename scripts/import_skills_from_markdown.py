#!/usr/bin/env python3
"""
Import skills and passives from Notion markdown exports.

This script parses markdown files from 'resources/Character List/' and updates
the corresponding YAML files in 'data/characters/' with skill/passive data.

Only the region from the `# Skills - parsed from markdown` marker to the metadata
block is rewritten; roles, notes and other curated fields above it are preserved.
Files whose kit was edited by hand must drop the marker so they are skipped.

Usage:
    python scripts/import_skills_from_markdown.py
    python scripts/import_skills_from_markdown.py --dry-run
    python scripts/import_skills_from_markdown.py --character richard
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from _character_ids import (  # noqa: E402
    extract_character_name_from_md,
    resolve_character_id,
)

SKILLS_MARKER = "# Skills - parsed from markdown"

# Headerless nested blocks starting with these labels describe the parent skill
# (cooldowns, use counts, ultimate gauge modes) rather than a status glossary term.
SKILL_META_LABELS = (
    "Preparation Turns",
    "Reuse Turns",
    "Uses",
    "Usage Condition",
    "Initial Gauge",
    "Gauge Increase",
    "Overcharge",
    "Backsurge",
)

# Pre-release Notion exports use these instead of real names; never store them as names.
PLACEHOLDER_NAMES = {"Name", "???", "TBD"}

ABBREVIATION = re.compile(r"\b(Phys|Elem|Atk|Def|Res|Lv|Spd|Crit|vs)\.")
TIER_TAG = re.compile(r"\((\d★|Initial|EX)\)")


# =============================================================================
# Text helpers
# =============================================================================


def clean_html_tags(text: str) -> str:
    """Remove HTML tags, markdown emphasis, and Notion artifacts from text."""
    text = re.sub(r"</?aside[^>]*>", "", text)
    text = re.sub(r"<img[^>]*>", "", text)
    text = re.sub(r"\(\[✦\]\([^)]+\)\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = text.replace("**", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def split_sentences(text: str) -> list[str]:
    """Split into sentences without breaking on 'Phys.', 'Elem.', 'Def.', 'Lv.' etc."""
    protected = ABBREVIATION.sub(r"\1<DOT>", text)
    parts = re.split(r"(?<=[.!?])\s+", protected)
    return [p.replace("<DOT>", ".").strip() for p in parts if p.strip()]


def parse_skill_tier(text: str) -> tuple[str, bool]:
    """
    Parse skill tier from text like '(1★)', '(3★)', '([✦]...)', '(6★)'.
    Returns (category, is_limit_break_upgrade).
    """
    if "6★" in text:
        return "active", True
    if "✦" in text:
        return "tp", False
    return "active", False


def parse_sp_cost(text: str) -> int | None:
    """Extract SP cost from text like '[38 SP]'."""
    match = re.search(r"\[(\d+)\s*SP\]", text)
    return int(match.group(1)) if match else None


def parse_potency(text: str) -> str | None:
    """Extract potency from text like '(potency: 3x65)' or '(potency: 230)'."""
    match = re.search(r"\(potency:\s*([^)]+)\)", text)
    return match.group(1).strip() if match else None


def parse_hit_count(text: str) -> str | None:
    """Extract hit count from text like '3 time(s)'."""
    match = re.search(r"(\d+)\s*time\(s\)", text)
    return f"{match.group(1)}x" if match else None


def parse_damage_type(text: str) -> list[str]:
    """Extract damage types from skill description."""
    types = []
    patterns = [
        (r"Phys\.\s*Sword\s*damage", "sword"),
        (r"Phys\.\s*Polearm\s*damage", "polearm"),
        (r"Phys\.\s*Dagger\s*damage", "dagger"),
        (r"Phys\.\s*Axe\s*damage", "axe"),
        (r"Phys\.\s*Bow\s*damage", "bow"),
        (r"Phys\.\s*Staff\s*damage", "staff"),
        (r"Phys\.\s*Fan\s*damage", "fan"),
        (r"Elem\.\s*Fire\s*damage", "fire"),
        (r"Elem\.\s*Ice\s*damage", "ice"),
        (r"Elem\.\s*Lightning\s*damage", "lightning"),
        (r"Elem\.\s*Wind\s*damage", "wind"),
        (r"Elem\.\s*Light\s*damage", "light"),
        (r"Elem\.\s*Dark\s*damage", "dark"),
    ]
    for pattern, dtype in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            types.append(dtype)

    exploit_match = re.search(r"Exploits?\s+(\w+)\s+weakness", text, re.IGNORECASE)
    if exploit_match:
        weakness = exploit_match.group(1).lower()
        if weakness not in types:
            types.append(weakness)

    return types


def parse_target(text: str) -> str:
    """Extract target type from skill description."""
    text_lower = text.lower()
    if "front row" in text_lower:
        return "front_row"
    if "back row" in text_lower:
        return "back_row"
    if "all foes" in text_lower:
        return "aoe"
    if "random foe" in text_lower:
        return "random"
    if "single foe" in text_lower:
        return "single_enemy"
    if "paired all" in text_lower:
        return "paired_ally"
    if "all allies" in text_lower:
        return "all_allies"
    if "single ally" in text_lower:
        return "single_ally"
    if " self" in text_lower:
        return "self"
    return "single_enemy"


def determine_skill_type(text: str) -> str:
    """Determine skill type from description."""
    text_lower = text.lower()

    has_damage = re.search(r"\bdeal\b[^.]*damage", text_lower) is not None
    has_buff = (
        any(kw in text_lower for kw in ["raise", "up %", "up", "grant", "impart"])
        and "foe" not in text_lower
    )
    has_debuff = any(kw in text_lower for kw in ["lower", "down", "impart"]) and "foe" in text_lower
    has_heal = "restore hp" in text_lower or "restore sp" in text_lower or "cure" in text_lower

    if has_damage and (has_buff or has_debuff or has_heal):
        return "mixed"
    if has_damage:
        return "attack"
    if has_heal:
        return "heal"
    if has_buff:
        return "buff"
    if has_debuff:
        return "debuff"
    return "utility"


# =============================================================================
# <aside> tree
# =============================================================================


@dataclass
class AsideNode:
    """One Notion <aside> block: its own text plus nested blocks."""

    text: str = ""
    children: list["AsideNode"] = field(default_factory=list)


def parse_asides(section: str) -> list[AsideNode]:
    """Parse a markdown section into top-level <aside> nodes, honoring nesting."""
    root = AsideNode()
    stack: list[tuple[AsideNode, list[str]]] = [(root, [])]

    for token in re.split(r"(<aside>|</aside>)", section):
        if token == "<aside>":
            stack.append((AsideNode(), []))
        elif token == "</aside>":
            if len(stack) == 1:
                continue
            node, parts = stack.pop()
            node.text = "".join(parts)
            stack[-1][0].children.append(node)
        else:
            stack[-1][1].append(token)

    while len(stack) > 1:
        node, parts = stack.pop()
        node.text = "".join(parts)
        stack[-1][0].children.append(node)

    return root.children


@dataclass
class Entry:
    """A skill or passive parsed from a headed <aside> block."""

    name: str | None
    unlock_tier: str | None
    is_tp: bool
    tp_level: int | None
    is_6star: bool
    body: str
    sp_cost: int | None = None
    upgrades: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    limit_break_upgrade: str | None = None


def parse_header(header: str) -> tuple[str | None, str | None, bool, int | None, bool]:
    """Split a bold header into (name, unlock_tier, is_tp, tp_level, is_6star)."""
    header = re.sub(r"\(?\[✦\]\([^)]*\)\)?", "✦", header)
    header = re.sub(r"\s*\(Lv\.[^)]*\)", "", header)
    tier_match = TIER_TAG.search(header)
    level_match = re.search(r"Lv\.\s*(\d+)", header)
    name = re.sub(r"\((\d★|Initial|EX)\)|✦|Lv\.\s*\d+", "", header).strip(' |“”"')
    unlock_tier = tier_match.group(1) if tier_match else None
    return (
        None if name in PLACEHOLDER_NAMES or "???" in name else name or None,
        unlock_tier,
        "✦" in header,
        int(level_match.group(1)) if level_match else None,
        unlock_tier == "6★",
    )


def entry_from_node(node: AsideNode) -> Entry | None:
    """Build an Entry from a node whose first line carries a bold header."""
    stripped = node.text.strip()
    first_line, _, rest = stripped.partition("\n")
    first_line = re.sub(r"^\s*(<img[^>]*>\s*)*", "", first_line)
    header_match = re.match(r"\*\*(.+?)\*\*", first_line)
    if not header_match or header_match.group(1).startswith("Lv."):
        return None

    name, unlock_tier, is_tp, tp_level, is_6star = parse_header(header_match.group(1).strip())
    body_raw = first_line[header_match.end() :] + "\n" + rest
    body_raw, _, meta_raw = body_raw.partition("\n---")

    upgrades = [
        f"Lv.{level}: {clean_html_tags(text)}"
        for level, text in re.findall(r"\*\*Lv\.(\d+)\s*\|\*\*\s*([^\n]+)", body_raw)
    ]
    body_raw = re.sub(r"\*\*Lv\.\d+\s*\|\*\*[^\n]*", "", body_raw)
    sp_cost = parse_sp_cost(body_raw)
    body = clean_html_tags(re.sub(r"\[(\d+|X+)\s*SP\]", "", body_raw))

    entry = Entry(
        name=name,
        unlock_tier=unlock_tier,
        is_tp=is_tp,
        tp_level=tp_level,
        is_6star=is_6star,
        body=body,
        sp_cost=sp_cost,
        upgrades=upgrades,
    )
    meta = clean_html_tags(meta_raw)
    if meta:
        entry.notes.append(meta)
    return entry


def collect_headerless(node: AsideNode, glossary: dict[str, str], notes: list[str] | None) -> None:
    """Route headerless blocks to skill notes (meta) or the character glossary."""
    text = clean_html_tags(node.text)
    if text:
        glossary_match = re.match(r"^[“\"]?([^:“”\"]{2,40}?)[”\"]?:\s+(.+)$", text)
        if text.startswith(SKILL_META_LABELS) or not glossary_match:
            if notes is not None:
                notes.append(text)
        else:
            glossary.setdefault(glossary_match.group(1).strip(), glossary_match.group(2).strip())
    for child in node.children:
        collect_headerless(child, glossary, notes)


def build_entries(node: AsideNode, glossary: dict[str, str]) -> list[Entry]:
    """Return the node's entry followed by any distinctly named nested entries."""
    entry = entry_from_node(node)
    if entry is None:
        collect_headerless(node, glossary, None)
        return []

    extra: list[Entry] = []
    for child in node.children:
        if entry_from_node(child) is None:
            collect_headerless(child, glossary, entry.notes)
            continue
        child_entry, *child_extra = build_entries(child, glossary)
        if child_entry.is_6star:
            entry.limit_break_upgrade = child_entry.body
            entry.notes.extend(child_entry.notes)
        elif child_entry.name in (None, entry.name):
            label = f"Lv.{child_entry.tp_level}" if child_entry.tp_level else "Upgraded"
            entry.upgrades.append(f"{label}: {child_entry.body}")
            entry.upgrades.extend(f"{label}: {note}" for note in child_entry.notes)
        else:
            extra.append(child_entry)
        extra.extend(child_extra)
    return [entry, *extra]


def parse_section_entries(section: str, glossary: dict[str, str]) -> list[Entry]:
    """Parse all entries of a section, attaching top-level 6★ blocks to their base."""
    entries: list[Entry] = []
    for node in parse_asides(section):
        for entry in build_entries(node, glossary):
            if entry.is_6star and entries:
                base = next((e for e in reversed(entries) if e.name == entry.name), entries[-1])
                base.limit_break_upgrade = entry.body
            else:
                entries.append(entry)
    return entries


def _section(content: str, heading: str, stop: str) -> str | None:
    match = re.search(rf"## (?:{heading})\s*(.*?)(?=## (?:{stop})|$)", content, re.DOTALL)
    return match.group(1) if match else None


# =============================================================================
# Entry -> YAML dicts
# =============================================================================


def _compact(data: dict) -> dict:
    return {k: v for k, v in data.items() if v not in (None, "", [], False)}


def entry_to_skill(entry: Entry, category: str) -> dict:
    text = entry.body
    return _compact(
        {
            "skill_category": category,
            "name": entry.name,
            "unlock_tier": entry.unlock_tier,
            "sp_cost": entry.sp_cost,
            "skill_type": determine_skill_type(text),
            "damage_types": parse_damage_type(text),
            "target": parse_target(text),
            "hit_count": parse_hit_count(text),
            "power": parse_potency(text),
            "priority": "act faster" in text.lower(),
            "effects": split_sentences(text),
            "upgrades": entry.upgrades,
            "limit_break_upgrade": entry.limit_break_upgrade,
            "notes": "; ".join(entry.notes) or None,
        }
    )


def passive_trigger(description: str) -> str:
    desc_lower = description.lower()
    if "start of battle" in desc_lower or "at the start" in desc_lower:
        return "battle_start"
    if "at full hp" in desc_lower or "at max hp" in desc_lower:
        return "hp_condition"
    if "when breaking" in desc_lower:
        return "on_break"
    return "always"


def entry_to_passive(entry: Entry) -> dict:
    return _compact(
        {
            "passive_category": "tp" if entry.is_tp else "innate",
            "name": entry.name,
            "unlock_tier": entry.unlock_tier,
            "effect": entry.body,
            "trigger": passive_trigger(entry.body),
            "upgrades": entry.upgrades,
            "limit_break_upgrade": entry.limit_break_upgrade,
            "notes": "; ".join(entry.notes) or None,
        }
    )


def parse_passives_section(content: str, glossary: dict[str, str]) -> list[dict]:
    """Parse Passive Skills or Support Skills section."""
    section = _section(content, "Passive Skills|Support Skills", "Battle Skills|Ultimate|EX")
    if section is None:
        return []
    return [entry_to_passive(e) for e in parse_section_entries(section, glossary) if e.body]


def parse_skills_section(content: str, glossary: dict[str, str]) -> list[dict]:
    """Parse the Battle Skills section."""
    section = _section(content, "Battle Skills", "Ultimate|EX")
    if section is None:
        return []
    return [
        entry_to_skill(e, "tp" if e.is_tp else "active")
        for e in parse_section_entries(section, glossary)
        if e.body
    ]


def parse_ex_skill(content: str, glossary: dict[str, str]) -> dict | None:
    """Parse the EX skill section."""
    section = _section(content, "EX skill", "Awakening|Misc")
    entries = parse_section_entries(section, glossary) if section else []
    if not entries:
        return None
    skill = entry_to_skill(entries[0], "ex")
    trigger = re.search(r"Usage Condition:\s*([^;]+)", skill.get("notes", ""))
    if trigger:
        skill["ex_trigger"] = trigger.group(1).strip()
    return skill


def parse_ultimate(content: str, glossary: dict[str, str]) -> dict | None:
    """Parse the Ultimate Technique section."""
    section = _section(content, "Ultimate Technique", "EX|Awakening")
    entries = parse_section_entries(section, glossary) if section else []
    if not entries:
        return None
    return entry_to_skill(entries[0], "special")


def parse_a4_accessory(content: str) -> dict | None:
    """Parse the Awakening IV Accessory section."""
    section = _section(content, "Awakening IV Accessory", "Exclusive|Misc")
    if section is None:
        return None
    name_match = re.search(r"\*\*([^*]+)\*\*", section)
    if not name_match or name_match.group(1).strip(' “”"') in PLACEHOLDER_NAMES:
        return None
    effects = re.findall(r"·([^\n]+)", section)
    return {
        "name": name_match.group(1).strip(' “”"'),
        "passive_effect": "; ".join(e.strip() for e in effects),
    }


def parse_markdown_file(filepath: Path) -> dict:
    """Parse a character markdown file."""
    content = filepath.read_text(encoding="utf-8")
    glossary: dict[str, str] = {}

    result = {
        "name": extract_character_name_from_md(filepath.name),
        "passives": parse_passives_section(content, glossary),
        "skills": parse_skills_section(content, glossary),
    }
    for extra in (parse_ex_skill(content, glossary), parse_ultimate(content, glossary)):
        if extra:
            result["skills"].append(extra)

    a4 = parse_a4_accessory(content)
    if a4:
        result["a4_accessory"] = a4

    result["unique_mechanics"] = [
        {"name": name, "description": description} for name, description in glossary.items()
    ]
    return result


# =============================================================================
# YAML update
# =============================================================================


def is_importer_owned(content: str) -> bool:
    """True when the skills region is generated; hand-edited kits drop the marker."""
    return SKILLS_MARKER in content


def _dump(key: str, value) -> list[str]:
    text = yaml.safe_dump(
        {key: value}, sort_keys=False, allow_unicode=True, width=10_000, default_flow_style=False
    )
    return text.rstrip("\n").split("\n")


def render_generated_block(parsed: dict, include_unique_mechanics: bool) -> list[str]:
    lines = [SKILLS_MARKER, *_dump("skills", parsed.get("skills") or [])]
    lines += [
        "",
        "# Passives - parsed from markdown",
        *_dump("passives", parsed.get("passives") or []),
    ]
    if parsed.get("a4_accessory"):
        lines += ["", "# A4 Accessory - parsed from markdown"]
        lines += _dump("a4_accessory", parsed["a4_accessory"])
    if include_unique_mechanics and parsed.get("unique_mechanics"):
        lines += ["", "# Glossary terms - parsed from markdown"]
        lines += _dump("unique_mechanics", parsed["unique_mechanics"])
    return lines


def apply_skill_overrides(skills: list[dict], overrides: list[dict], label: str) -> None:
    """Set curated names/SP (e.g. read from the game) on the skill whose effects contain `match`."""
    for override in overrides:
        hits = [s for s in skills if override["match"] in " ".join(s.get("effects", []))]
        if len(hits) != 1:
            print(f"  WARN: {label} override {override['match']!r} matched {len(hits)} skills")
            continue
        skill = hits[0]
        named = {"skill_category": skill["skill_category"], "name": override["name"]}
        skill_rest = {k: v for k, v in skill.items() if k not in named}
        skill.clear()
        skill.update({**named, **skill_rest})
        observed = override.get("sp_cost")
        if observed and not skill.get("sp_cost"):
            skill["sp_cost"] = observed
        elif observed and observed != skill["sp_cost"]:
            # Source gives base SP; the game screen shows the levelled cost (SP Saver upgrades).
            note = f"In-game SP at owner's level: {observed}"
            skill["notes"] = f"{skill['notes']}; {note}" if skill.get("notes") else note


def update_yaml_file(yaml_path: Path, parsed_data: dict, dry_run: bool = False) -> bool:
    """Replace the generated skills..metadata region of an importer-owned YAML file."""
    if not yaml_path.exists():
        print(f"  SKIP: No YAML file found at {yaml_path}")
        return False

    content = yaml_path.read_text(encoding="utf-8")
    if not is_importer_owned(content):
        print(f"  SKIP: {yaml_path.name} is hand-curated")
        return False
    overrides = (yaml.safe_load(content) or {}).get("skill_overrides") or []
    apply_skill_overrides(parsed_data.get("skills") or [], overrides, yaml_path.name)

    lines = content.split("\n")
    skills_idx = next((i for i, line in enumerate(lines) if line.startswith("skills:")), None)
    if skills_idx is None:
        print(f"  SKIP: No skills section found in {yaml_path}")
        return False
    start = skills_idx
    while start > 0 and lines[start - 1].startswith("# Skills"):
        start -= 1
    end = next(
        (
            i
            for i in range(skills_idx + 1, len(lines))
            if "# Metadata" in lines[i] or lines[i].startswith("data_confidence:")
        ),
        len(lines),
    )

    head, tail = lines[:start], lines[end:]
    has_mechanics = any(line.startswith("unique_mechanics:") for line in head + tail)
    new_lines = head + render_generated_block(parsed_data, not has_mechanics) + [""] + tail
    new_content = "\n".join(new_lines)

    if new_content == content:
        return False
    if dry_run:
        print(f"  WOULD UPDATE: {yaml_path.name}")
        return True

    yaml_path.write_text(new_content, encoding="utf-8")
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

    md_files = sorted(md_dir.glob("*.md"))
    md_files = [f for f in md_files if not f.name.startswith(("3 Stars", "4 Stars", "5 Stars"))]
    print(f"Found {len(md_files)} character markdown files")

    if args.character:
        md_files = [f for f in md_files if args.character.lower() in f.name.lower()]
        print(f"Filtered to {len(md_files)} files matching '{args.character}'")

    if args.limit:
        md_files = md_files[: args.limit]
        print(f"Limited to first {args.limit} files")

    updated = skipped = errors = 0
    for md_file in md_files:
        char_name = extract_character_name_from_md(md_file.name)
        yaml_path = yaml_dir / f"{resolve_character_id(char_name)}.yaml"
        try:
            parsed = parse_markdown_file(md_file)
            if not parsed.get("skills") and not parsed.get("passives"):
                print(f"  SKIP: {char_name} - no skills/passives found")
                skipped += 1
                continue
            if update_yaml_file(yaml_path, parsed, dry_run=args.dry_run):
                updated += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  ERROR: {char_name} - {e}")
            errors += 1

    print("\nSummary:")
    print(f"  Updated: {updated}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors: {errors}")
    return 0


if __name__ == "__main__":
    exit(main())
