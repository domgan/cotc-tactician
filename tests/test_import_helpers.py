"""Tests for character import helpers."""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from _character_ids import create_character_id, resolve_character_id  # noqa: E402
from import_skills_from_markdown import (  # noqa: E402
    parse_markdown_file,
    split_sentences,
    update_yaml_file,
)

# Trimmed from the Rocbouquet Notion export: tier-only headers, nested glossary
# asides, a nested TP Lv.2 upgrade, a named nested passive and a "Lv.NN |" line.
ROCBOUQUET_MD = """# Rocbouquet

## Passive Skills

<aside>
<img src="a.png" /> **([✦](https://app.notion.com/p/x?pvs=21))**
When a broken enemy is present, lower Elem. Res. of All Foes by 10%.

<aside>
<img src="b.png" /> **([✦](https://app.notion.com/p/x?pvs=21)) Lv.2**
When a broken enemy is present, lower Elem. Res. of All Foes by **20%**.

</aside>

<aside>
<img src="c.png" /> **Damage Limit Up ([✦](https://app.notion.com/p/x?pvs=21)) Lv.2**
Raise Damage Limit of Elem. Lightning, Wind and Dark attacks of All Allies by 15,000.

</aside>

</aside>

<aside>
<img src="c.png" /> **Damage Limit Up (6★)**
Raise Self's Damage Limit by 30,000.

</aside>

## Battle Skills

<aside>
<img src="d.png" /> **(Initial)**
Deal Elem. Wind damage to Single Foe 3 time(s) (potency: 3x55). [33 SP]

</aside>

<aside>
<img src="e.png" /> **(3★)**
Deal Elem. Wind damage to All Foes 3 time(s) (potency: 3x65). When there's an enemy marked with Rancor, also lower their Phys. Atk., Phys. Def., Elem. Atk. and Elem. Def. by 10% (turns: 2). [88 SP]

<aside>
<img src="Enchant.png" /> Enchant: Have a certain chance of being unable to act.

</aside>

**Lv.88 |** SP Saver: 88→70

</aside>

## Ultimate Technique

<aside>
<img src="f.png" /> **“Passion Perfume” (Lv. 1→10→20)**
Act faster during turn, raise Damage Limit of All Allies by **10,000→50,000→100,000** (turns: 3).

---

Uses:
1→2

</aside>
"""


def _write_md(tmp_path: Path) -> Path:
    path = tmp_path / "Rocbouquet 7152a618231983488409816cd3f3d7f2.md"
    path.write_text(ROCBOUQUET_MD, encoding="utf-8")
    return path


def test_split_sentences_keeps_stat_abbreviations():
    text = "Lower their Phys. Def. and Elem. Def. by 15%. Raise Spd. by 10% (Boost Lv.)."
    assert split_sentences(text) == [
        "Lower their Phys. Def. and Elem. Def. by 15%.",
        "Raise Spd. by 10% (Boost Lv.).",
    ]


def test_nested_glossary_and_level_lines_do_not_become_skills(tmp_path):
    parsed = parse_markdown_file(_write_md(tmp_path))
    skills = parsed["skills"]

    assert [s["skill_category"] for s in skills] == ["active", "active", "special"]
    aoe = skills[1]
    assert "name" not in aoe
    assert aoe["unlock_tier"] == "3★"
    assert aoe["sp_cost"] == 88
    assert aoe["upgrades"] == ["Lv.88: SP Saver: 88→70"]
    assert aoe["effects"][-1] == (
        "When there's an enemy marked with Rancor, also lower their Phys. Atk., "
        "Phys. Def., Elem. Atk. and Elem. Def. by 10% (turns: 2)."
    )
    assert parsed["unique_mechanics"] == [
        {"name": "Enchant", "description": "Have a certain chance of being unable to act."}
    ]


def test_nested_tp_upgrade_named_child_and_6star(tmp_path):
    passives = parse_markdown_file(_write_md(tmp_path))["passives"]

    assert len(passives) == 2
    elem_res, dmg_limit = passives
    assert elem_res["passive_category"] == "tp"
    assert "name" not in elem_res
    assert elem_res["upgrades"] == [
        "Lv.2: When a broken enemy is present, lower Elem. Res. of All Foes by 20%."
    ]
    assert dmg_limit["name"] == "Damage Limit Up"
    assert dmg_limit["limit_break_upgrade"] == "Raise Self's Damage Limit by 30,000."


def test_inline_bold_in_headerless_child_is_not_a_skill(tmp_path):
    md = tmp_path / "Final Emperor 0000a618231983488409816cd3f3d7f2.md"
    md.write_text(
        "## Battle Skills\n\n<aside>\n<img src=\"a.png\" /> **([✦](https://x))**\n"
        "Deal Phys. Axe damage to Random Foe 3 time(s) (potency: **3x85**). [60 SP]\n\n"
        "<aside>\n<img src=\"a.png\" /> **([✦](https://x)) Lv.2**\n"
        "Deal Phys. Axe damage to Random Foe 3 time(s) (potency: **3x95**). [60 SP]\n\n"
        "<aside>\n<img src=\"Glimmer.png\" /> Deal Phys. Axe damage to Random Foe 3 time(s) "
        "(potency: **3x95**). Damage Limit of this skill is increased by 500,000.\n</aside>\n\n"
        "</aside>\n\n</aside>\n",
        encoding="utf-8",
    )
    skills = parse_markdown_file(md)["skills"]

    assert len(skills) == 1
    assert skills[0]["power"] == "3x85"
    assert any("Lv.2:" in u and "500,000" in u for u in skills[0]["upgrades"])


def test_ultimate_name_and_meta(tmp_path):
    ultimate = parse_markdown_file(_write_md(tmp_path))["skills"][-1]
    assert ultimate["name"] == "Passion Perfume"
    assert ultimate["skill_type"] == "buff"
    assert ultimate["priority"] is True
    assert ultimate["notes"] == "Uses: 1→2"


def _character_yaml(confidence: str, marker: bool) -> str:
    skills_header = "# Skills - parsed from markdown\n" if marker else ""
    return (
        "id: rocbouquet\nroles: [buffer]\n\n"
        f"{skills_header}skills:\n  - skill_category: active\n    name: Hand Written\n"
        "    skill_type: attack\n    target: aoe\n\n"
        f"# Metadata\ndata_confidence: {confidence}\n"
    )


def test_update_regenerates_marked_kit_and_keeps_curated_fields(tmp_path):
    parsed = parse_markdown_file(_write_md(tmp_path))
    owned = tmp_path / "owned.yaml"
    owned.write_text(_character_yaml("verified", marker=True), encoding="utf-8")

    assert update_yaml_file(owned, parsed) is True
    data = yaml.safe_load(owned.read_text(encoding="utf-8"))
    assert data["roles"] == ["buffer"]
    assert data["data_confidence"] == "verified"
    assert len(data["skills"]) == 3
    assert data["unique_mechanics"][0]["name"] == "Enchant"


def test_update_skips_hand_edited_kit(tmp_path):
    parsed = parse_markdown_file(_write_md(tmp_path))
    path = tmp_path / "hand-edited.yaml"
    original = _character_yaml("incomplete", marker=False)
    path.write_text(original, encoding="utf-8")

    assert update_yaml_file(path, parsed) is False
    assert path.read_text(encoding="utf-8") == original


def test_create_character_id_strips_accents():
    assert create_character_id("Agnès") == "agnes"
    assert create_character_id("José") == "jose"
    assert create_character_id("Throné") == "throne"


def test_resolve_character_id_legacy_aliases():
    assert resolve_character_id("Agnès") == "agn-s"
    assert resolve_character_id("José") == "jos"
    assert resolve_character_id("Throné") == "thron"


def test_support_skills_parser_finds_passives():
    md_path = (
        Path(__file__).resolve().parent.parent
        / "resources"
        / "Character List"
        / "Aviete 6272a618231982b8b29f011235837ce8.md"
    )
    if not md_path.exists():
        return

    parsed = parse_markdown_file(md_path)
    assert len(parsed["skills"]) > 0
    assert len(parsed["passives"]) > 0
