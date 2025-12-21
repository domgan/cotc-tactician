# Character Role Assignment Guide

This guide helps assign roles to characters based on their skills and passives.

## Role Definitions (from meowdb)

| Role | What to Look For |
|------|------------------|
| **PDPS** | High physical attack, weapon damage skills, crit passives, self-buffs |
| **EDPS** | High elemental attack, element damage skills, multi-element coverage |
| **Tank** | Provoke/Taunt skills, high HP/DEF, damage reduction, self-heals |
| **Healer** | Party HP healing, regen skills, revive, status cure |
| **Buffer** | Party ATK/damage buffs, BP regen, damage cap up, potency up |
| **Debuffer** | Enemy DEF down, resistance down, weakness implant, critical scope |
| **Breaker** | High hit-count skills, [Priority], +shield damage, multi-weapon |

## Role Assignment Process

### Step 1: Identify Primary Role
Look at the character's highest-impact skills. What do they do best?

**DPS indicators:**
- High power skills (260+ power)
- Self damage buffs
- Guaranteed crit
- Potency up
- Damage cap up

**Support indicators:**
- Party-wide buffs
- Party-wide debuffs
- Multi-turn duration
- Regen/healing

### Step 2: Identify Secondary Roles
Most characters do more than one thing. Check for:

**Role compression examples:**
- Richard: Buffer (sword/polearm damage up) + PDPS
- Primrose EX: Buffer + Healer + Regen
- Viola: Debuffer + Breaker (multi-hit)
- Rinyuu: Healer + Buffer (Crusader's Prayer)

### Step 3: Check Tier Lists for Context
The [meowdb tier list](https://meowdb.com/db/octopath-traveler-cotc/tier-list-by-roles/) 
rates each character across all roles:
- S+/S in a role = Excellent at that role
- A/B = Good at that role
- n/a = Cannot perform that role

## Quick Role Assignment by Job

### Warriors (Sword primary)
- Usually: PDPS, Breaker
- Look for: Tank skills (provoke), Buffer skills

### Hunters (Bow primary)
- Usually: PDPS, Breaker
- Look for: Multi-hit skills, debuffs

### Thieves (Dagger primary)
- Usually: PDPS, Breaker, Debuffer
- Look for: Multi-hit, speed manipulation

### Apothecaries (Axe primary)
- Usually: Healer, Support
- Look for: Healing, regen, status cure

### Merchants (Polearm primary)
- Usually: PDPS, Buffer
- Look for: BP manipulation, buffs

### Scholars (Tome primary)
- Usually: EDPS
- Look for: Multi-element coverage, AoE

### Clerics (Staff primary)
- Usually: Healer, Buffer
- Look for: Party healing, regen, buffs

### Dancers (Fan primary)
- Usually: Buffer, Debuffer, EDPS
- Look for: Party buffs, debuffs, element damage

## Key Characters to Prioritize

These are commonly mentioned in meta discussions and should have accurate roles:

### S+ Tier (prioritize these)
- **Elrica** - Sword DPS
- **Richard** - Sword/Polearm Buffer + DPS
- **Primrose EX** - Buffer + Healer
- **Rinyuu** - Healer (Crusader's Prayer)
- **Viola/Viola EX** - Debuffer
- **Lynette** - Buffer
- **Bargello** - Dagger/Wind Buffer + DPS
- **W'ludai** - Polearm DPS

### Common Support
- **Gilderoy** - Tank
- **Canary** - Debuffer
- **Sarisa** - Dagger Debuffer
- **Roland** - Polearm Debuffer

## Updating Character YAML Files

Add roles to the `roles` field:

```yaml
roles:
  - buffer
  - dps

role_notes: |
  Primary buffer for sword/polearm teams.
  Also deals solid physical damage.
  Key skills: [Skill name] for buff, [Skill name] for damage.
```

## Automated Detection (Future)

A script could potentially assign roles based on skill keywords:
- "Frontrow X Up" → Buffer
- "Enemy X Down" → Debuffer
- "Heal" or "Regen" → Healer
- "Provoke" or "Taunt" → Tank
- High hit count (4+) → Breaker
- High power (300+) → DPS

However, nuance is required - manual review recommended.
