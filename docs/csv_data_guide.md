# Community CSV Data Guide

This document explains how to use the community spreadsheet CSV exports for data entry.

## CSV Sources

The CSV files in `resources/` come from the community spreadsheet:
- **Characters Index**: Overview of all characters by job
- **Warriors ⭐5**: Detailed data for 5★ Warrior characters
- (Similar files exist for other jobs)

## Can These CSVs Be Used Programmatically?

**Short answer: With difficulty.**

The spreadsheets are designed for **human reading**, not programmatic parsing:

### Challenges

1. **Non-tabular layout**: Data is arranged visually, not in rows/columns
2. **Merged cells**: Multi-line skill descriptions span rows
3. **Implicit structure**: Skill awakening levels are positional (1*, 2*, 3*, etc.)
4. **Variable row counts**: Each character takes a different number of rows
5. **Empty rows**: Used for visual spacing
6. **Nested data**: Skills, passives, and effects are mixed in complex ways

### What IS Parseable

With significant effort, you could extract:
- Character names and their job/class
- Basic stat values (HP, Atk, etc.) at known positions
- Skill text (though parsing effects would be complex)
- Release dates, rarity, voice actors

### Recommendation

**Use CSVs as a reference for manual data entry, not for automated import.**

The best workflow:
1. Open the CSV (or the original Google Sheet)
2. Manually create YAML entries using our schema
3. Copy-paste skill descriptions verbatim
4. Use consistent patterns for effects

## Data Entry Patterns

### Skill Text Format (from spreadsheets)

The community uses consistent patterns:

```
"2x single-target Sword (2x 90~180 Power)"
│  │              │     │   └─ Power range
│  │              │     └─ Hits × Power per hit
│  │              └─ Damage type (weapon/element)
│  └─ Targeting (single-target, AoE, random-target)
└─ Hit count
```

More examples:
```
"4x random-target Wind (4x 55~105 Power)"
"1x AoE Sword, inflict 15% Def Down for 2 turns (1x 150~260 Power)"
"3x single-target Light, also hits Sword weakness (3x 85~140 Power)"
"[Priority] 1x single-target Sword (1x 440 Power)"
```

### Effect Patterns

```
"Self 20% Atk Up for 3-6 turns, based on Boost Lv."
"Frontrow 15% Sword Dmg/Spear Dmg Up for 2-5 turns"
"inflict 15% Def Down for 2 turns"
"AoE Taunt for 2 turns"
"Self Guaranteed Crit for 3 turns"
"HP Regen (110 Regen Strength)"
"HP Barrier (40% of Max HP)"
```

### Conditional Patterns

```
"If Boost MAX, guaranteed Crit"
"Power x1.5 if target is Broken"
"Power x1.2 if target has Wind Res Down"
"If self HP is more than 50%, take 50% max HP damage for power x1.1"
```

## Character Data Structure (from CSV)

Each character entry in the CSV contains:

### Identity Block
- Character name (first column, at character start)
- Influence type (Wealth, Power, Glory, Dominance, Opulence, Prestige)
- Stats at Lv100 and Lv120

### Skills Block
Organized by awakening level:
- Base skills (no marker)
- 1* skill
- 2* skills (two)
- 3* skill  
- 4* skill
- 5* skills (two)
- TP skill (active from TP passive)
- EX skill (with trigger condition)
- Special/Ultimate (Lv1, Lv10, Lv20)

### Passives Block
- 1* passive
- 3* passive
- TP passive
- (6* upgrades shown in separate column)

### Accessories Block
- A4 accessory name and effects
- Sometimes exclusive accessories

### Resistances Block
- Element resistances (20%, 10%)

### Metadata Block
- Release date
- Rarity
- Gacha banner
- Voice actor

## Example: CSV to YAML Conversion

### CSV Data (Tikilen)

```
Tikilen
Wealth
Lv100: 3062
Stats: 301/339/323/372/241/290/290
Skills:
  30 SP: 1x AoE Sword (1x 150~260 Power)
  20 SP: 1x single-target Wind (1x 170~350 Power)
  1*: 30 SP: 2x AoE Wind (2x 70~120 Power)
  2*: 25 SP: 3x random-target Sword (3x 55~100 Power)
  2*: 24 SP: Self 20% Speed Up for 3-6 turns
  3*: 34 SP: 1x single-target Wind (1x 230~400 Power)
  ...
Passives:
  1*: At the start of battle, Self 20% Mag Up for 3 turns
  3*: Self 20% Wind Damage Up
  TP: While at 50% HP or lower, 50% chance to dodge certain attacks
A4: Windslicer Bracers (Self 10% Wind Damage Up, When breaking inflict 20% Wind Res Down)
```

### YAML Output

```yaml
id: tikilen
display_name: Tikilen
rarity: 5
job: warrior
influence: wealth

elements_covered: [wind]
weapons_covered: [sword]

roles: [dps, breaker]
role_notes: |
  Hybrid Sword/Wind attacker. Strong multi-hit skills for breaking.
  Free character from Arena, good starter DPS.

skills:
  - awakening: base
    sp_cost: 30
    skill_type: attack
    damage_types: [sword]
    target: aoe
    hit_count: "1x"
    power: "150~260"

  - awakening: base
    sp_cost: 20
    skill_type: attack
    damage_types: [wind]
    target: single_enemy
    hit_count: "1x"
    power: "170~350"

  - awakening: a1
    sp_cost: 30
    skill_type: attack
    damage_types: [wind]
    target: aoe
    hit_count: "2x"
    power: "70~120"

  # ... more skills

  - awakening: tp
    sp_cost: 73
    skill_type: attack
    damage_types: [wind, sword]
    target: aoe
    hit_count: "3x"
    power: "65"
    effects:
      - "inflicts 15% Wind Res Down for 2 turns"
    notes: "Also hits Sword weakness - rare hybrid"

  - awakening: special
    skill_type: attack
    damage_types: [wind]
    target: single_enemy
    hit_count: "4-6x (random)"
    power: "85/100/125"
    notes: "Lv1/Lv10/Lv20 power values"

passives:
  - awakening: a1
    effect: "At the start of battle, Self 20% Mag Up for 3 turns"
    trigger: battle_start
    a6_upgrade: "Effect is now permanent, also grants Magic Critical Hit"

  - awakening: a3
    effect: "Self 20% Wind Damage Up"
    trigger: always

  - awakening: tp
    effect: "While at 50% HP or lower, 50% chance to dodge certain attacks"
    trigger: hp_condition

a4_accessory:
  name: "Windslicer Bracers"
  passive_effect: |
    Self 10% Wind Damage Up
    When breaking an enemy, inflict 20% Wind Res Down for 3 turns

assumed_awakening: 4
has_tp_passive: false
has_a6: false

data_confidence: verified
data_source: "Community spreadsheet (YetAnotherIndecisive)"
last_updated: 2024-12-21
```

## Notes for Data Entry

1. **Preserve exact wording**: Copy skill effects verbatim - the LLM will parse them
2. **Focus on team-relevant skills**: Buffer/debuffer effects are more important than raw damage
3. **Note weakness coverage**: "also hits X weakness" expands breaking options
4. **Document unique mechanics**: Stances, stacks, and special states need explanation
5. **Mark confidence levels**: Use `verified`, `tested`, `theoretical`, or `incomplete`

## Resources

- [Original Google Sheet](https://docs.google.com/spreadsheets/d/...) (link from Discord)
- [MeowDB Guide](https://meowdb.com/db/octopath-traveler-cotc/)
- Discord communities: discord.gg/octopath

