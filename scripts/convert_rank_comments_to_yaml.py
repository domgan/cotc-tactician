#!/usr/bin/env python3
"""
Convert rank/EX comments in boss YAML files to structured rank_variants field.

This script:
1. Parses rank comments like "# Rank 1: Shield 10, HP 7,532, Speed 120"
2. Converts them to a proper rank_variants YAML structure
3. Removes old EX comments (EX data should be in separate files)

Usage:
    python scripts/convert_rank_comments_to_yaml.py --dry-run
    python scripts/convert_rank_comments_to_yaml.py
"""

import argparse
import re
from pathlib import Path


def parse_rank_comment(line: str) -> dict | None:
    """Parse a rank comment line into structured data."""
    # Pattern: # Rank 1: Shield 10, HP 7,532, Speed 120
    # Or: # EX1: Shield 19, HP 2,554,424, Speed 487

    rank_match = re.match(
        r"#\s*(Rank\s*(\d+)|EX(\d+)):\s*Shield\s*(\d+),?\s*HP\s*([\d,]+),?\s*Speed\s*(\d+)",
        line,
        re.IGNORECASE,
    )
    if rank_match:
        if rank_match.group(2):  # Rank N
            rank_num = int(rank_match.group(2))
            rank_key = f"rank{rank_num}"
        else:  # EX N
            rank_key = f"ex{rank_match.group(3)}"

        return {
            "rank": rank_key,
            "shield_count": int(rank_match.group(4)),
            "hp": int(rank_match.group(5).replace(",", "")),
            "speed": int(rank_match.group(6)),
        }
    return None


def process_file(filepath: Path, dry_run: bool = False) -> bool:
    """Process a single boss file."""
    with open(filepath, encoding="utf-8") as f:
        content = f.read()
        lines = content.split("\n")

    # Find rank/EX comment section
    rank_data = {}
    ex_data = {}
    comment_section_start = -1
    comment_section_end = -1

    for i, line in enumerate(lines):
        parsed = parse_rank_comment(line)
        if parsed:
            if comment_section_start == -1:
                comment_section_start = i
            comment_section_end = i

            if parsed["rank"].startswith("rank"):
                rank_data[parsed["rank"]] = parsed
            else:
                ex_data[parsed["rank"]] = parsed

    if not rank_data:
        return False  # No rank data found

    # Check if file already has rank_variants
    if "rank_variants:" in content:
        print(f"  Skip (already has rank_variants): {filepath.name}")
        return False

    # Build the rank_variants YAML block
    yaml_lines = []
    yaml_lines.append("")
    yaml_lines.append(
        "# ==========================================================================="
    )
    yaml_lines.append("# RANK VARIANTS (for progression)")
    yaml_lines.append("# See separate -ex1, -ex2, -ex3 files for EX variants.")
    yaml_lines.append(
        "# ==========================================================================="
    )
    yaml_lines.append("rank_variants:")

    # Get level from file if available
    level_match = re.search(r"^level:\s*(\d+)", content, re.MULTILINE)
    level = int(level_match.group(1)) if level_match else 100

    for rank_key in ["rank1", "rank2", "rank3"]:
        if rank_key in rank_data:
            data = rank_data[rank_key]
            yaml_lines.append(f"  {rank_key}:")
            yaml_lines.append(f"    shield_count: {data['shield_count']}")
            yaml_lines.append(f"    hp: {data['hp']}")
            yaml_lines.append(f"    speed: {data['speed']}")
            yaml_lines.append(f"    level: {level}")

    # Find where to insert (after weaknesses section ideally, or after shield_count)
    insert_pos = -1
    for i, line in enumerate(lines):
        if line.strip().startswith("weaknesses:"):
            # Find end of weaknesses block
            for j in range(i + 1, len(lines)):
                if (
                    lines[j].strip()
                    and not lines[j].startswith(" ")
                    and not lines[j].startswith("#")
                ):
                    insert_pos = j
                    break
            break
        elif line.strip().startswith("shield_count:"):
            insert_pos = i + 1

    if insert_pos == -1:
        # Insert after difficulty line
        for i, line in enumerate(lines):
            if line.strip().startswith("difficulty:"):
                insert_pos = i + 1
                break

    if insert_pos == -1:
        print(f"  Skip (couldn't find insert position): {filepath.name}")
        return False

    # Remove old comment section
    new_lines = []
    skip_until_blank = False
    for i, line in enumerate(lines):
        # Skip the old rank/EX comment section
        if i >= comment_section_start and i <= comment_section_end:
            continue
        # Also skip the header for RANK/EX VARIANTS section if present
        if "# RANK/EX VARIANTS" in line or "# Data for all difficulty tiers" in line:
            skip_until_blank = True
            continue
        if skip_until_blank:
            if line.strip() == "" or (not line.startswith("#") and line.strip()):
                skip_until_blank = False
            else:
                continue
        new_lines.append(line)

    # Insert rank_variants at the right position
    # Recalculate insert position after removal
    insert_pos = -1
    for i, line in enumerate(new_lines):
        if line.strip().startswith("weaknesses:"):
            for j in range(i + 1, len(new_lines)):
                if (
                    new_lines[j].strip()
                    and not new_lines[j].startswith(" ")
                    and not new_lines[j].startswith("#")
                ):
                    insert_pos = j
                    break
            break
        elif line.strip().startswith("shield_count:"):
            insert_pos = i + 1

    if insert_pos == -1:
        for i, line in enumerate(new_lines):
            if line.strip().startswith("difficulty:"):
                insert_pos = i + 1
                break

    if insert_pos == -1:
        insert_pos = len(new_lines)

    # Insert the new YAML
    final_lines = new_lines[:insert_pos] + yaml_lines + new_lines[insert_pos:]

    # Clean up multiple blank lines
    cleaned_lines = []
    prev_blank = False
    for line in final_lines:
        is_blank = line.strip() == ""
        if is_blank and prev_blank:
            continue
        cleaned_lines.append(line)
        prev_blank = is_blank

    new_content = "\n".join(cleaned_lines)

    if dry_run:
        print(f"  Would update: {filepath.name}")
        print(f"    Ranks: {list(rank_data.keys())}")
        if ex_data:
            print(f"    EX (removed from comments): {list(ex_data.keys())}")
    else:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"  Updated: {filepath.name}")

    return True


def main():
    parser = argparse.ArgumentParser(description="Convert rank comments to YAML structure")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be changed")
    args = parser.parse_args()

    bosses_dir = Path(__file__).parent.parent / "data" / "bosses"

    # Files that have rank/EX comments to convert
    files_to_process = list(bosses_dir.glob("adversary-*.yaml"))

    # Exclude EX variant files (they don't need rank_variants)
    files_to_process = [f for f in files_to_process if not re.search(r"-ex\d\.yaml$", f.name)]

    print(f"Found {len(files_to_process)} base adversary files to check")

    updated = 0
    for filepath in sorted(files_to_process):
        if process_file(filepath, args.dry_run):
            updated += 1

    print(f"\nSummary: {updated} files {'would be ' if args.dry_run else ''}updated")

    if args.dry_run:
        print("\n(Dry run - no files modified)")


if __name__ == "__main__":
    main()
