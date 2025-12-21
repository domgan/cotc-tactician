"""
Prompt templates for the LLM reasoning pipeline.

The system prompt enforces data-only reasoning.
The LLM is treated as ignorant of COTC game knowledge.
"""

SYSTEM_PROMPT = """# COTC Team Composition Analyst

You are a reasoning engine for team composition. You have NO knowledge of the game "Octopath Traveler: Champions of the Continent" beyond what is provided in each query.

## ABSOLUTE RULES

### 1. You Know Nothing
- You do NOT know any character names, skills, or stats
- You do NOT know any boss names, mechanics, or strategies
- You do NOT know the current meta or tier lists
- You do NOT know which characters are "good" or "bad"
- ALL game knowledge must come from the provided context

### 2. Data-Only Reasoning
- You may ONLY reference characters that appear in the [AVAILABLE CHARACTERS] section
- You may ONLY reference skills that are listed for those characters
- You may ONLY reference boss mechanics that are listed in the [BOSS DATA] section
- If information is missing, you MUST say "This information was not provided"

### 3. No Hallucination
- NEVER invent a character name
- NEVER invent a skill name or effect
- NEVER invent a number (damage, duration, percentage)
- NEVER assume a synergy that is not explicitly stated
- If you are uncertain, say "Based on the provided data, I cannot determine..."

### 4. Uncertainty Markers
When reasoning from limited data, use these markers:
- "The provided data suggests..." (when inferring from explicit information)
- "This is uncertain because..." (when data is incomplete)
- "If [assumption] is correct, then..." (when making necessary assumptions)
- "The data does not specify..." (when information is missing)

### 5. Reference Your Sources
When making claims, cite the data:
- "According to [character_id]'s skill [skill_name]..."
- "The boss data indicates [mechanic_name] occurs at [trigger]..."
- "The proven team [team_id] uses this approach because..."

### 6. Structured Output
Always respond in the requested JSON format. Do not add fields or omit required fields.

## WHAT YOU CAN DO

1. Analyze boss mechanics FROM the provided boss data
2. Match character capabilities TO boss requirements
3. Identify synergies that are EXPLICITLY stated in character data
4. Propose team compositions using ONLY provided characters
5. Explain reasoning by CITING provided data
6. Flag missing information or low-confidence data

## WHAT YOU CANNOT DO

1. Recommend characters not in the provided list
2. Describe skills not documented for a character
3. Assume a character is "good" without supporting data
4. Fill in missing data with assumptions
5. Use general JRPG knowledge to supplement missing COTC data
"""

USER_PROMPT_TEMPLATE = """## BOSS DATA
{boss_data}

## SIMILAR BOSSES (for pattern reference)
{similar_bosses}

## PROVEN TEAMS (verified compositions for this boss)
{proven_teams}

## AVAILABLE CHARACTERS
{candidate_characters}

---

## YOUR TASK

Analyze the boss encounter and propose team compositions.

### If PROVEN TEAMS are provided:
1. Explain why each proven team works (cite specific mechanics and character skills)
2. Identify which characters from AVAILABLE CHARACTERS can substitute
3. Note any risks or variations

### If NO PROVEN TEAMS are provided:
1. Analyze boss mechanics and identify required capabilities
2. Match AVAILABLE CHARACTERS to those requirements
3. Propose 2-3 team compositions with explicit reasoning
4. Mark confidence level based on data completeness

### For ALL responses:
- Use ONLY character IDs from AVAILABLE CHARACTERS
- Cite specific skills and mechanics by name
- Flag any data gaps that affect your recommendations
- Do not recommend characters not in the provided list

Respond in the following JSON format:

```json
{output_schema}
```
"""

OUTPUT_SCHEMA = """{
  "data_completeness": {
    "boss_data": "complete | partial | minimal",
    "character_data": "complete | partial | minimal",
    "proven_teams_available": true | false,
    "missing_critical_info": ["list of missing information that would improve recommendations"]
  },

  "boss_analysis": {
    "summary": "Brief summary DERIVED FROM provided boss data",
    "key_mechanics": [
      {
        "mechanic_name": "FROM boss_data.mechanics[].name",
        "threat_level": "FROM boss_data.mechanics[].threat_level",
        "counter_needed": "FROM boss_data.mechanics[].counter_strategy"
      }
    ],
    "required_capabilities": [
      {
        "capability": "e.g., 'party-wide healing'",
        "reason": "Because [mechanic_name] requires this",
        "source": "boss_data.mechanics[X] or boss_data.required_roles[Y]"
      }
    ]
  },

  "proposed_teams": [
    {
      "name": "Descriptive name for this composition",
      "confidence": "high | medium | low",
      "confidence_reason": "Why this confidence level",
      "strategy_type": "burst | sustain | safe",
      
      "composition": [
        {
          "position": 1,
          "character_id": "FROM available_characters",
          "role": "tank | healer | buffer | debuffer | breaker | dps",
          "key_skills": ["skill names FROM that character's data"],
          "why_selected": "Reasoning citing specific character data",
          "substitutes": ["other character_ids that could fill this role"],
          "substitute_tradeoffs": "What changes with substitution"
        }
      ],

      "speed_order": ["character_ids in intended turn order"],
      "speed_tuning_notes": "How to achieve this order (if known from data)",

      "turn_plan_summary": {
        "setup_phase": "What to do turns 1-N before first break",
        "break_phase": "What to do during break window",
        "sustain_phase": "How to handle extended fight (if applicable)"
      },

      "synergies_used": [
        {
          "characters": ["char_id_1", "char_id_2"],
          "synergy": "FROM character_data.synergies or explicitly reasoned",
          "source": "character_data or inferred"
        }
      ],

      "risks": ["Potential failure points"],
      "data_gaps": ["What additional data would improve this recommendation"]
    }
  ],

  "characters_not_recommended": [
    {
      "character_id": "FROM available_characters",
      "reason": "Why not suitable for this boss (citing data)"
    }
  ],

  "additional_notes": [
    "Any other observations based on provided data"
  ]
}"""


def format_boss_data(boss) -> str:
    """Format boss data for the prompt."""
    if boss is None:
        return "No boss data provided. Using free-text description."
    
    # Handle optional weaknesses
    if boss.weaknesses:
        weak_elements = [e.value for e in boss.weaknesses.elements] if boss.weaknesses.elements else []
        weak_weapons = [w.value for w in boss.weaknesses.weapons] if boss.weaknesses.weapons else []
    else:
        weak_elements = []
        weak_weapons = []
    
    lines = [
        f"ID: {boss.id}",
        f"Name: {boss.display_name}",
        f"Difficulty: {boss.difficulty.value}",
        f"Content Type: {boss.content_type.value}",
        "",
        "Weaknesses:",
        f"  Elements: {weak_elements}",
        f"  Weapons: {weak_weapons}",
        "",
        f"Shield Count: {boss.shield_count}",
        "",
        "Mechanics:",
    ]
    
    for mech in boss.mechanics:
        lines.append(f"  - {mech.name}")
        lines.append(f"    Type: {mech.mechanic_type.value}")
        if mech.trigger:
            lines.append(f"    Trigger: {mech.trigger}")
        lines.append(f"    Target: {mech.target.value}")
        lines.append(f"    Threat Level: {mech.threat_level.value}")
        lines.append(f"    Counter Strategy: {mech.counter_strategy}")
        lines.append("")
    
    if boss.phases:
        lines.append("Phases:")
        for phase in boss.phases:
            lines.append(f"  Phase {phase.phase_number}: {phase.trigger}")
            lines.append(f"    Changes: {phase.behavior_changes}")
            if phase.priority_actions:
                lines.append(f"    Priority: {phase.priority_actions}")
        lines.append("")
    
    lines.append("Required Roles:")
    for rr in boss.required_roles:
        lines.append(f"  - {rr.role.value} ({rr.priority.value}): {rr.reason}")
    
    lines.append("")
    lines.append(f"General Strategy: {boss.general_strategy}")
    
    if boss.common_mistakes:
        lines.append("")
        lines.append("Common Mistakes:")
        for mistake in boss.common_mistakes:
            lines.append(f"  - {mistake}")
    
    lines.append("")
    lines.append(f"Data Confidence: {boss.data_confidence.value}")
    
    return "\n".join(lines)


def format_similar_bosses(bosses: list) -> str:
    """Format similar bosses for the prompt."""
    if not bosses:
        return "No similar bosses found in the database."
    
    lines = []
    for boss in bosses:
        lines.append(f"### {boss.display_name} ({boss.id})")
        lines.append(f"Difficulty: {boss.difficulty.value}")
        
        # Handle optional weaknesses
        if boss.weaknesses:
            weak_elements = [e.value for e in boss.weaknesses.elements] if boss.weaknesses.elements else []
            weak_weapons = [w.value for w in boss.weaknesses.weapons] if boss.weaknesses.weapons else []
        else:
            weak_elements = []
            weak_weapons = []
        lines.append(f"Weaknesses: {weak_elements}, {weak_weapons}")
        
        strategy = boss.general_strategy[:200] if boss.general_strategy else "No strategy documented"
        lines.append(f"Strategy: {strategy}...")
        lines.append("")
    
    return "\n".join(lines)


def format_proven_teams(teams: list) -> str:
    """Format proven teams for the prompt."""
    if not teams:
        return "No proven teams available for this boss."
    
    lines = []
    for team in teams:
        lines.append(f"### {team.name} ({team.id})")
        lines.append(f"Strategy: {team.strategy_type.value}")
        lines.append(f"Investment: {team.investment_level.value}")
        lines.append(f"Verified: {team.verified}")
        lines.append("")
        lines.append("Composition:")
        
        for slot in team.front_line:
            lines.append(f"  Position {slot.position}: {slot.character_id}")
            lines.append(f"    Role: {slot.role_in_team.value}")
            lines.append(f"    Required: {slot.is_required}")
            lines.append(f"    Key Skills: {slot.key_skills_used}")
            if slot.substitutes:
                lines.append(f"    Substitutes: {slot.substitutes}")
        
        lines.append("")
        lines.append(f"Why It Works: {team.why_it_works}")
        lines.append(f"Key Synergies: {team.key_synergies}")
        
        if team.risks_and_recovery:
            lines.append(f"Risks: {team.risks_and_recovery}")
        
        lines.append(f"Data Confidence: {team.data_confidence.value}")
        lines.append("")
    
    return "\n".join(lines)


def format_characters(characters: list) -> str:
    """Format available characters for the prompt."""
    if not characters:
        return "No characters provided."
    
    lines = []
    for char in characters:
        lines.append(f"### {char.display_name} ({char.id})")
        lines.append(f"Job: {char.job.value}")
        
        if char.weakness_coverage:
            lines.append(f"Weakness Coverage: {char.weakness_coverage}")
        
        if char.roles:
            lines.append(f"Roles: {[r.value for r in char.roles]}")
        
        if char.role_notes:
            lines.append(f"Role Notes: {char.role_notes}")
        
        # Stats summary
        if char.p_atk or char.e_atk:
            lines.append(f"Stats: P.Atk={char.p_atk}, E.Atk={char.e_atk}, Speed={char.speed}")
        
        if char.gl_tier or char.jp_tier:
            lines.append(f"Tier: GL={char.gl_tier}, JP={char.jp_tier}")
        
        lines.append("")
        lines.append("Skills:")
        for skill in char.skills:
            skill_name = skill.name or "(unnamed)"
            lines.append(f"  - {skill_name} [{skill.skill_category.value}]")
            lines.append(f"    Type: {skill.skill_type.value}")
            lines.append(f"    Target: {skill.target.value}")
            if skill.damage_types:
                lines.append(f"    Damage Types: {skill.damage_types}")
            if skill.hit_count:
                lines.append(f"    Hits: {skill.hit_count}")
            if skill.power:
                lines.append(f"    Power: {skill.power}")
            if skill.sp_cost:
                lines.append(f"    SP Cost: {skill.sp_cost}")
            if skill.effects:
                lines.append(f"    Effects: {skill.effects[:3]}")  # Limit effects shown
            if skill.ex_trigger:
                lines.append(f"    EX Trigger: {skill.ex_trigger}")
            if skill.notes:
                lines.append(f"    Notes: {skill.notes}")
        
        if char.passives:
            lines.append("")
            lines.append("Key Passives:")
            for passive in char.passives[:5]:  # Limit to 5 most important
                lines.append(f"  - {passive.effect[:100]}...")
        
        if char.synergies:
            lines.append("")
            lines.append("Synergies:")
            for syn in char.synergies:
                lines.append(f"  - With {syn.character_id}: {syn.description}")
        
        if char.weaknesses:
            lines.append("")
            lines.append(f"Limitations: {char.weaknesses}")
        
        if char.best_use_cases:
            lines.append(f"Best For: {char.best_use_cases}")
        
        lines.append(f"Data Confidence: {char.data_confidence.value}")
        lines.append("")
    
    return "\n".join(lines)


def build_prompt(context: dict) -> str:
    """
    Build the complete user prompt from retrieved context.
    
    Args:
        context: Dictionary with boss, similar_bosses, proven_teams,
                 candidate_characters keys.
                 
    Returns:
        Formatted user prompt string.
    """
    return USER_PROMPT_TEMPLATE.format(
        boss_data=format_boss_data(context.get("boss")),
        similar_bosses=format_similar_bosses(context.get("similar_bosses", [])),
        proven_teams=format_proven_teams(context.get("proven_teams", [])),
        candidate_characters=format_characters(context.get("candidate_characters", [])),
        output_schema=OUTPUT_SCHEMA,
    )

