# AGENTS.md — Architecture Guide for AI Agents

This document describes the COTC Tactician architecture for AI coding assistants and agents working on this codebase.

## Critical Design Principle

**THE LLM KNOWS NOTHING ABOUT COTC**

Most game knowledge must come from human-curated data files. The LLM:
- ❌ CANNOT invent character names, skills, or stats
- ❌ CANNOT invent boss mechanics or strategies
- ❌ CANNOT assume meta or balance knowledge
- ✅ CAN reason over provided data
- ✅ CAN identify patterns and synergies from explicit data
- ✅ CAN propose team compositions using only provided characters

When modifying this codebase:
- Never add game-specific knowledge to code
- All game facts must be stored in `data/*.yaml` files
- Treat most `[HUMAN-REQUIRED]` fields as opaque—don't generate values

## Project Structure

```
cotc-tactician/
├── src/
│   ├── __init__.py         # Package init
│   ├── models.py           # Pydantic models for all entities
│   ├── data_loader.py      # YAML loading and validation
│   ├── vector_store.py     # ChromaDB wrapper
│   ├── retrieval.py        # Retrieval service (combines loader + vectors)
│   ├── prompts.py          # System prompt and templates
│   ├── pipeline.py         # Main reasoning pipeline
│   ├── mcp_server.py       # MCP server for Cursor/Claude integration
│   └── main.py             # CLI entry point
├── scripts/
│   └── import_characters_from_csv.py  # CSV to YAML converter
├── data/
│   ├── characters/         # Character YAML files (260+ from CSV import)
│   ├── bosses/             # Boss YAML files
│   ├── teams/              # Team composition YAML files
│   └── reference/          # Reference data (elements, weapons, etc.)
├── resources/              # Source data files
│   └── Character List all.csv  # Community spreadsheet export
├── requirements.txt
├── pyproject.toml
├── README.md
└── AGENTS.md               # This file
```

## Key Components

### 1. Models (`src/models.py`)

Pydantic models for all game entities:

- `Character`: Player characters with skills, roles, synergies
- `Boss`: Enemy encounters with mechanics, weaknesses, phases
- `Team`: Proven team compositions for specific bosses

Each model has:
- `get_embedding_text()`: Returns text for vector embedding
- `get_metadata()`: Returns metadata for vector store filtering

### 2. Data Loader (`src/data_loader.py`)

Loads YAML files from disk:

```python
loader = DataLoader("./data")
characters, bosses, teams = loader.load_all()
```

Skips files starting with `_` (schemas, templates, examples).

### 2b. CSV Import Script (`scripts/import_characters_from_csv.py`)

Converts community spreadsheet data to YAML:

```bash
# Dry run to see what would be created
python scripts/import_characters_from_csv.py --dry-run

# Import all characters
python scripts/import_characters_from_csv.py

# Overwrite existing files
python scripts/import_characters_from_csv.py --overwrite
```

**Note**: CSV import only provides base data (stats, weakness coverage, tier ratings).
Skills, passives, and roles are added by `import_skills_from_markdown.py`.

### 2c. Skill Import Script (`scripts/import_skills_from_markdown.py`)

Parses Notion markdown exports to extract skills and passives:

```bash
# Import skills for all characters
python scripts/import_skills_from_markdown.py

# Dry run
python scripts/import_skills_from_markdown.py --dry-run

# Import specific character
python scripts/import_skills_from_markdown.py --character "Richard"
```

**Note**: The markdown files must be in `resources/Character List/` as Notion exports.
Roles still need manual assignment based on skill analysis.

### 2d. Adversary Log Import Script (`scripts/import_adversary_log_from_csv.py`)

Imports boss data from community spreadsheet CSV exports:

```bash
# Dry run to see what would be created
python scripts/import_adversary_log_from_csv.py --dry-run

# Import all bosses
python scripts/import_adversary_log_from_csv.py

# Overwrite existing files
python scripts/import_adversary_log_from_csv.py --overwrite
```

**Source files** (in `resources/Adversary Log/`):
- `EN OT_ COTC _ Adversary Log Enemy Index - Lv. 1~.csv`
- `EN OT_ COTC _ Adversary Log Enemy Index - Lv. 25~.csv`
- `EN OT_ COTC _ Adversary Log Enemy Index - Lv. 50~.csv`
- `EN OT_ COTC _ Adversary Log Enemy Index - Lv. 75~.csv`
- Corresponding `Fight Notes.csv` files with strategy tips

**CRITICAL: EX Variant File Structure**

Each boss with EX variants requires **SEPARATE YAML FILES** for RAG indexing:
```
adversary-francesca-the-actress.yaml      # Base (Rank 1-3)
adversary-francesca-the-actress-ex1.yaml  # EX1 variant
adversary-francesca-the-actress-ex2.yaml  # EX2 variant
adversary-francesca-the-actress-ex3.yaml  # EX3 variant
```

**DO NOT put EX stats in comments** - they won't be indexed by RAG!

Each EX file must have:
- `base_boss_id`: References the base boss file
- `ex_rank`: `ex1`, `ex2`, or `ex3`
- `shield_count`: The actual shield count for that EX rank
- `hp`: The actual HP for that EX rank (from CSV)
- `speed`: The actual speed for that EX rank (from CSV)
- `actions_per_turn`: Usually 2 for EX1/EX2, 3 for EX3
- `general_strategy`: EX-specific strategy notes

See `data/bosses/arena-gertrude-ex1.yaml` for the canonical example.

### 2e. Rank Comment Conversion Script (`scripts/convert_rank_comments_to_yaml.py`)

Converts rank/EX comments in boss files to structured `rank_variants` YAML:

```bash
# Dry run
python scripts/convert_rank_comments_to_yaml.py --dry-run

# Convert all files
python scripts/convert_rank_comments_to_yaml.py
```

This script:
- Parses rank comments like `# Rank 1: Shield 10, HP 7,532, Speed 120`
- Converts them to a proper `rank_variants` YAML structure
- Removes old EX comments (EX data should be in separate files)

### 3. Vector Store (`src/vector_store.py`)

ChromaDB wrapper with three collections:
- `characters`: Semantic search for characters
- `bosses`: Semantic search for bosses
- `teams`: Semantic search for team compositions

Key methods:
```python
store.index_all(characters, bosses, teams)
store.search_characters(query, n_results=10)
store.search_bosses(query, n_results=5)
store.get_teams_for_boss(boss_id)
```

### 4. Retrieval Service (`src/retrieval.py`)

High-level retrieval combining exact matches and semantic search:

```python
service = RetrievalService(data_dir, vector_store)
service.initialize()

# Get context for team composition
context = service.retrieve_context_for_boss(
    boss_id="example-boss",
    available_character_ids=["char1", "char2"]
)
```

### 5. Prompts (`src/prompts.py`)

Contains:
- `SYSTEM_PROMPT`: Enforces data-only reasoning
- `USER_PROMPT_TEMPLATE`: Structures context for LLM
- `OUTPUT_SCHEMA`: Expected JSON output format
- Formatting functions for each entity type

### 6. Pipeline (`src/pipeline.py`)

Main reasoning flow:

```python
pipeline = ReasoningPipeline(data_dir, llm_client)
pipeline.initialize()

result = pipeline.compose_team(
    boss_id="example-boss",
    available_character_ids=["char1", "char2"]
)
```

Supports two LLM backends:
- `OpenAIClient`: Uses OpenAI API
- `OllamaClient`: Uses local Ollama

### 7. MCP Server (`src/mcp_server.py`)

Alternative interface using Model Context Protocol (MCP) for Cursor/Claude integration.
Instead of using paid LLM APIs, you can use Claude in Cursor as the reasoning engine.

**Start the MCP server:**
```bash
cotc-tactician mcp-serve
```

**Configure Cursor** by adding to `~/.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "cotc-tactician": {
      "command": "cotc-tactician",
      "args": ["mcp-serve"]
    }
  }
}
```

**Available MCP Tools:**

| Tool | Description |
|------|-------------|
| `get_team_building_guide` | **CALL FIRST** - Get party structure, role definitions, EX scaling |
| `search_characters` | Semantic search for characters by query |
| `get_character` | Get full character details (skills, passives, stats) |
| `find_by_weakness` | Find characters covering specific weaknesses |
| `list_by_tier` | Get characters by tier rating (S+, S, A, etc.) |
| `get_team_suggestions` | Suggest characters for a boss fight |
| `list_all_character_ids` | List all available character IDs |
| `get_database_stats` | Get indexed entity counts |
| `search_bosses` | Search for bosses by description |
| `get_boss` | Get full boss details (mechanics, weaknesses, strategy) |
| `list_all_boss_ids` | List all available boss IDs |
| `plan_team_for_boss` | Get strategic team planning (8 chars: 4 front + 4 back) |

**How it works:**
1. Claude in Cursor calls these tools to retrieve game data
2. Tools return structured JSON from the human-curated data files
3. Claude reasons about team composition using its native intelligence
4. No custom prompts needed - Claude handles the reasoning

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DATA FLOW                                      │
└─────────────────────────────────────────────────────────────────────────────┘

1. USER INPUT
   boss_id="tikilen" OR description="Boss with party-wide nuke..."

2. RETRIEVAL
   ┌─────────────┐     ┌─────────────┐
   │ DataLoader  │────►│ YAML Files  │
   └──────┬──────┘     └─────────────┘
          │
          ▼
   ┌─────────────┐     ┌─────────────┐
   │ VectorStore │────►│ ChromaDB    │
   └──────┬──────┘     └─────────────┘
          │
          ▼
   ┌─────────────────────────────────────┐
   │ Context:                            │
   │   - boss: Boss | None               │
   │   - similar_bosses: list[Boss]      │
   │   - proven_teams: list[Team]        │
   │   - candidate_characters: list[Char]│
   └─────────────────┬───────────────────┘
                     │
3. PROMPT ASSEMBLY   │
                     ▼
   ┌─────────────────────────────────────┐
   │ System Prompt: "You know nothing..."│
   │ User Prompt: formatted context      │
   │ Output Schema: JSON structure       │
   └─────────────────┬───────────────────┘
                     │
4. LLM REASONING     │
                     ▼
   ┌─────────────────────────────────────┐
   │ LLM (Ollama or OpenAI)              │
   │   - Analyzes mechanics              │
   │   - Matches characters to roles     │
   │   - Proposes teams                  │
   │   - Explains reasoning              │
   └─────────────────┬───────────────────┘
                     │
5. OUTPUT            │
                     ▼
   ┌─────────────────────────────────────┐
   │ Structured JSON:                    │
   │   - boss_analysis                   │
   │   - proposed_teams                  │
   │   - data_gaps                       │
   │   - additional_notes                │
   └─────────────────────────────────────┘
```

## Adding New Features

### Adding a New Entity Type

1. Add Pydantic model in `src/models.py` with:
   - All fields with proper types
   - `get_embedding_text()` method
   - `get_metadata()` method

2. Add YAML schema in `data/[entity_type]/_schema.yaml`

3. Add template in `data/[entity_type]/_template.yaml`

4. Add loading method in `src/data_loader.py`

5. Add collection in `src/vector_store.py`

6. Add retrieval methods in `src/retrieval.py`

### Adding a New LLM Provider

1. Create client class implementing the `LLMClient` protocol:

```python
class MyLLMClient:
    def chat(self, system_prompt: str, user_prompt: str) -> str:
        # Your implementation
        pass
```

2. Add to `src/pipeline.py`

3. Add CLI option in `src/main.py`

### Modifying the Prompt

Edit `src/prompts.py`:
- `SYSTEM_PROMPT`: Core instructions (be careful—this enforces data-only reasoning)
- `USER_PROMPT_TEMPLATE`: How context is formatted
- `OUTPUT_SCHEMA`: Expected JSON structure
- Formatting functions: How entities are serialized

## Testing Considerations

- Use the `_example-*.yaml` files for testing
- Vector store can use in-memory mode (no persist_directory)
- Mock LLM clients for unit tests

## Future Agent Evolution

The current linear pipeline can evolve to agents:

### Current: Linear Pipeline
```
Parse → Retrieve → Assemble → LLM → Output
```

### Future: Agent with Tools
```python
@tool
def search_bosses(query: str) -> list[Boss]:
    """Find bosses matching description."""
    pass

@tool
def search_characters(requirements: dict) -> list[Character]:
    """Find characters matching role/element/weapon requirements."""
    pass

@tool
def get_proven_teams(boss_id: str) -> list[Team]:
    """Get verified team compositions for a boss."""
    pass
```

### LangGraph Integration

The pipeline maps directly to LangGraph nodes:

```python
graph = StateGraph(CompositionState)

graph.add_node("parse_input", parse_input)
graph.add_node("retrieve_context", retrieve_context)
graph.add_node("analyze", analyze_with_llm)
graph.add_node("propose_teams", propose_teams)
graph.add_node("validate", validate_composition)
graph.add_node("refine", handle_feedback)

# Add edges including loops for refinement
```

## Key Data Fields

### Character Model

Key fields for team composition:
- `weakness_coverage`: List of weaknesses this character can hit (weapons + elements)
- `roles`: Functional roles (tank, healer, buffer, debuffer, breaker, dps)
- `job`: Character class (determines primary weapon)
- `influence`: Character influence type (wealth, power, fame, domination, opulence, approval)
- `origin`: Where character comes from (Orsterra, Solistia, crossover worlds)
- `gl_tier` / `jp_tier`: Community tier ratings

### Progression Systems

See `data/reference/progression_systems.yaml` for details:
- **Awakening Stages (0-4)**: Stat bonuses, Stage II unlocks 4th skill slot, Stage IV gives A4 accessory
- **Limit Break (6★)**: Allows Lv120, may upgrade skills/passives
- **Blessing of the Lantern**: Unlocks TP passive and TP skill

### Weapon/Element Naming

Use these exact values (from community spreadsheet):
- Weapons: `sword`, `polearm`, `dagger`, `axe`, `bow`, `staff`, `tome`, `fan`
- Elements: `fire`, `ice`, `lightning`, `wind`, `light`, `dark`

Note: "Polearm" not "Spear", "Lightning" not "Thunder"

## Reference Files (Game Mechanics)

The `data/reference/` directory contains verified game mechanics knowledge:

| File | Purpose |
|------|---------|
| `damage_mechanics.yaml` | Damage formulas, multipliers, crit rules |
| `break_mechanics.yaml` | Break state, timing, shield shaving, turn order |
| `buff_categories.yaml` | 6 buff/6 debuff brackets, 30% caps, stacking rules |
| `turn_timing.yaml` | Buff activation timing, speed tuning, priority skills |
| `healing_mechanics.yaml` | Healing vs Regen scaling, top healers |
| `status_ailments.yaml` | Bleed, Poison, Burning effects |
| `meta_strategies.yaml` | Speedclear vs Turtle meta, team building principles |
| `roles.yaml` | PDPS, EDPS, Tank, Healer, Buffer, Debuffer, Breaker |
| `elements.yaml` | Element types and weakness order |
| `weapons.yaml` | Weapon types and primary jobs |
| `jobs.yaml` | Job classes and their primary weapons |
| `progression_systems.yaml` | Awakening, Limit Break, Blessing of Lantern |
| `ex_mechanics.yaml` | EX fight mechanics (Adversary Log), HP scaling, auras |
| `survival_strategies.yaml` | Tank archetypes (provoke, dodge, cover, HP barrier) |
| `damage_stacking.yaml` | 5 multiplicative damage categories for speedkill |
| `llm_guidelines.yaml` | **CRITICAL** - Party structure (8 chars), skill slots, EX scaling, common mistakes |

### Key Mechanics Summary

**Damage Multipliers:**
- Weakness: 2.5x
- Break: 2x
- Weakness + Break: **5x** (THE damage window)
- Crit: +25% (physical only)

**Buff/Debuff Rules:**
- 6 brackets each, 30% cap per bracket
- **Delayed activation**: Takes effect at START of next unit's turn
- Max duration: 9 turns

**Break Window:**
- Lasts 2 turns (break turn + next turn)
- Enemy cannot act, takes 2x damage
- After break: enemy acts FIRST

### EX Fight (Adversary Log) Schema

EX fights are enhanced rematches of bosses with increased difficulty.

**CRITICAL: Each EX variant requires its OWN YAML file for RAG indexing!**

```
data/bosses/
  adversary-sazantos.yaml      # Base (Rank 1-3)
  adversary-sazantos-ex1.yaml  # EX1 variant  
  adversary-sazantos-ex2.yaml  # EX2 variant
  adversary-sazantos-ex3.yaml  # EX3 variant
```

**DO NOT put EX stats in comments** - they won't be indexed by RAG!

**Boss EX File Fields:**
- `id`: Must include EX suffix (e.g., `adversary-sazantos-ex3`)
- `display_name`: Include EX rank (e.g., `"Sazantos EX3"`)
- `base_boss_id`: Links EX variant to base boss (e.g., `adversary-sazantos`)
- `ex_rank`: `ex1`, `ex2`, or `ex3`
- `shield_count`: Actual shield count for this EX rank (from CSV)
- `hp`: Actual HP for this EX rank (from CSV)
- `speed`: Actual speed for this EX rank (from CSV)
- `actions_per_turn`: 2 for EX1/EX2, 3 for EX3
- `provoke_immunity`: `true` for most EX bosses
- `general_strategy`: EX-specific strategy notes

**EX Rank Scaling (typical):**
- EX1: ~2x HP, +50 speed, 2 actions/turn
- EX2: ~3x HP, +100 speed, 2-3 actions/turn  
- EX3: ~5x HP, +150 speed, 3 actions/turn, extreme difficulty

**Example EX3 file structure:**
```yaml
id: adversary-sazantos-ex3
display_name: "Sazantos EX3"
content_type: adversary_log
difficulty: extreme

# EX VARIANT INFO - Critical for get_ex_variants tool!
base_boss_id: adversary-sazantos
ex_rank: ex3
actions_per_turn: 3
provoke_immunity: true

# Actual stats (indexed by RAG)
shield_count: 22
hp: 2242594
speed: 312

# EX3-specific strategy
general_strategy: |
  EX3 variant - MAXIMUM DIFFICULTY.
  - Speedkill (Solon + Primrose EX) or full turtle
  - Stack all buff/debuff categories to 30%
  - Fiore EX Cover or dodge tank essential
  Recommended HP per character: 4000+
```

**Aura Mechanics:**
```yaml
auras:
  - name: "Counter Stance"
    trigger: "Break recovery"
    active_indicator: "Purple flame"
    weakness_changes:
      locked: [sword, polearm]
      unlocked: [light]
    counter_trigger: "Hitting locked weakness"
    counter_effect: "+1 action next turn"
    removal_condition: "Break"
```

### Tank Types

Character schema now includes `tank_type` enum:

- `provoke`: Draw single-target attacks (Gilderoy, Serenoa)
- `dodge`: Evade via Sidestep (H'aanit EX, Canary, Tressa)
- `cover`: Intercept attacks for allies (Fiore EX only)
- `hp_barrier`: Create HP shields (Sazantos, Temenos)
- `none`: Not a tank

### Buff/Debuff Categories for Damage Stacking

Character and Team schemas now track which damage stacking categories are covered:

**5 Multiplicative Categories:**
1. Active Skills (cap 30%)
2. Passives/Equipment (cap 30%)
3. Ultimate (varies, Solon = 100% potency)
4. Pets (varies)
5. Divine Beast (varies)

**Character Schema:**
```yaml
buff_categories:
  active:
    - type: phys_atk_up
      value: 30
      source_skill: "Master's Cheer"
  passive:
    - type: sword_damage_up
      value: 15
      source_passive: "Sword Affinity"
  ultimate:
    - type: potency_up
      value: 100
      source_skill: "Ultimate"
```

**Team Schema:**
```yaml
survival_strategy: dodge_tank  # or provoke_tank, cover_tank, turtle, speedrun
target_ex_rank: ex3
minimum_hp_recommended: 4000
buff_category_coverage:
  active_atk_up: 30
  active_def_down: 30
  ultimate_potency: 100
```

## Common Pitfalls

1. **Don't hardcode game data**: All game facts go in YAML files
2. **Don't trust LLM game knowledge**: It knows nothing about COTC
3. **Keep embedding text focused**: Include only searchable content
4. **Validate data confidence**: Flag low-confidence recommendations
5. **Test with empty data**: System should gracefully handle missing data
6. **CSV-imported characters are incomplete**: They need skills, passives, and roles added manually

## Environment Setup

```bash
# Required
pip install -e ".[all]"

# Index the data first
cotc-tactician index

# Option 1: Use MCP with Cursor (recommended - no API costs)
cotc-tactician mcp-serve
# Then configure ~/.cursor/mcp.json as described above

# Option 2: Use local LLM (Ollama)
ollama pull llama3.1
cotc-tactician compose --desc "boss weak to fire"

# Option 3: Use cloud LLM (OpenAI)
export OPENAI_API_KEY="..."
cotc-tactician compose --llm openai --desc "boss weak to fire"

# Data directory (optional)
export COTC_DATA_DIR="./data"
export COTC_VECTOR_DIR="./.vectordb"
```
