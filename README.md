# COTC Tactician

AI-powered team composition assistant for **Octopath Traveler: Champions of the Continent**.

A local-first prototype combining human-editable game knowledge, vector-based semantic retrieval, and LLM-powered reasoning for team composition.

## Core Design Principle

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  THE LLM KNOWS NOTHING ABOUT COTC                                           │
│                                                                             │
│  All character names, skills, passives, numbers, boss mechanics,            │
│  and meta knowledge MUST come from human-curated data files.                │
│                                                                             │
│  The LLM's role: REASON over provided data, never GENERATE game facts.      │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Features

- **Human-Editable Data**: All game knowledge stored in YAML files (260+ characters imported)
- **Semantic Search**: Vector database for finding relevant characters/bosses/teams
- **MCP Server**: Use Claude in Cursor as your reasoning engine (no API costs!)
- **LLM Reasoning**: Alternatively use Ollama or OpenAI for team composition
- **Data-Grounded**: LLM cannot hallucinate game facts—only reasons from provided data
- **Local-First**: Runs entirely on your machine

## Quick Start

### 1. Install Dependencies

```bash
# Clone the repository
git clone https://github.com/example/cotc-tactician.git
cd cotc-tactician

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install with pip
pip install -e ".[all]"
```

### 2. Add Game Data

The system requires human-curated game data. Start by copying the templates:

```bash
# Copy character template
cp data/characters/_template.yaml data/characters/my-character.yaml

# Copy boss template
cp data/bosses/_template.yaml data/bosses/my-boss.yaml

# Copy team template
cp data/teams/_template.yaml data/teams/my-boss-team.yaml
```

Edit the YAML files with actual game data. See `data/*/_example-*.yaml` for format examples.

### 3. Index the Data

```bash
# Index game data into vector database
cotc-tactician index
```

### 4. Compose Teams

```bash
# With a known boss
cotc-tactician compose --boss example-boss

# With a description of an unknown boss
cotc-tactician compose --desc "Boss with party-wide nuke every 5 turns, weak to fire"

# With specific available characters
cotc-tactician compose --boss example-boss --chars "char1,char2,char3"
```

## Usage Options

### Option 1: MCP Server with Cursor (Recommended)

Use Claude in Cursor as your reasoning engine—no API costs!

```bash
# Start the MCP server
cotc-tactician mcp-serve
```

Configure Cursor by adding to `~/.cursor/mcp.json`:

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

Restart Cursor, then ask Claude things like:
- "Search for fire damage dealers in COTC"
- "Get details on the character primrose-ex"  
- "Find characters that hit sword and fire weaknesses"
- "Suggest a team for a boss weak to ice and dagger"

### Option 2: Local LLM (Ollama)

Requires [Ollama](https://ollama.ai/) installed:

```bash
ollama pull llama3.1
cotc-tactician compose --boss example-boss --llm ollama
```

### Option 3: Cloud LLM (OpenAI)

```bash
export OPENAI_API_KEY="your-api-key"
cotc-tactician compose --boss example-boss --llm openai
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `index` | Index game data into vector database |
| `compose` | Compose a team for a boss encounter |
| `mcp-serve` | Start MCP server for Cursor/Claude integration |
| `list-bosses` | List all indexed bosses |
| `list-characters` | List all indexed characters |
| `info <type> <id>` | Get info about a boss/character |
| `search <query>` | Semantic search across game data |

### MCP Tools (when using `mcp-serve`)

| Tool | Description |
|------|-------------|
| `search_characters` | Semantic search for characters by description |
| `get_character` | Get full character details (skills, passives, stats) |
| `find_by_weakness` | Find characters covering specific weaknesses |
| `list_by_tier` | Get characters by tier rating (S+, S, A, etc.) |
| `get_team_suggestions` | Suggest characters for a boss fight |
| `list_all_character_ids` | List all available character IDs |
| `get_database_stats` | Get indexed entity counts |

## Data Directory Structure

```
data/
├── characters/
│   ├── _schema.yaml          # Schema reference
│   ├── _template.yaml        # Template for new entries
│   ├── _example-character.yaml  # Example format
│   └── [your-characters].yaml
├── bosses/
│   ├── _schema.yaml
│   ├── _template.yaml
│   ├── _example-boss.yaml
│   └── [your-bosses].yaml
├── teams/
│   ├── _schema.yaml
│   ├── _template.yaml
│   ├── _example-team.yaml
│   └── [your-teams].yaml
└── reference/
    ├── elements.yaml         # Game elements (fire, ice, etc.)
    ├── weapons.yaml          # Weapon types
    ├── roles.yaml            # Role definitions
    └── buff_categories.yaml  # Buff/debuff stacking rules
```

## Data Entry Guidelines

### All data is [HUMAN-REQUIRED]

The LLM cannot and will not generate game data. You must provide:

- Character names, skills, and stats
- Boss mechanics and patterns
- Proven team compositions

### Data Confidence Levels

Mark your data confidence in each entry:

| Level | Meaning |
|-------|---------|
| `verified` | Confirmed from game, wiki, or trusted sources |
| `tested` | Personally tested but not cross-referenced |
| `theoretical` | Based on skill descriptions, not tested |
| `incomplete` | Missing significant information |

### Focus on Team-Relevant Data

You don't need to document everything. Focus on:

- Skills that affect team composition
- Synergies between characters
- Boss mechanics that require counters
- Proven team strategies

## Architecture

```mermaid
flowchart TB
    subgraph data ["📁 Data Layer"]
        yaml[(YAML Files<br/>260+ characters<br/>bosses, teams)]
        chromadb[(ChromaDB<br/>Vector Store)]
    end

    subgraph core ["⚙️ Core Services"]
        loader[Data Loader]
        models[Pydantic Models]
        retrieval[Retrieval Service]
        vectors[Vector Store]
    end

    subgraph interfaces ["🔌 Interfaces"]
        cli[CLI Commands<br/>compose, search, index]
        mcp[MCP Server<br/>7 tools for Claude]
    end

    subgraph llm ["🤖 LLM Options"]
        cursor[Cursor/Claude<br/>via MCP]
        ollama[Ollama<br/>Local LLM]
        openai[OpenAI<br/>Cloud API]
    end

    yaml --> loader
    loader --> models
    models --> vectors
    vectors --> chromadb
    models --> retrieval
    vectors --> retrieval
    
    retrieval --> cli
    retrieval --> mcp
    
    cli --> ollama
    cli --> openai
    mcp <--> cursor
```

### Data Flow

```mermaid
sequenceDiagram
    participant User
    participant Interface as CLI / MCP
    participant Retrieval
    participant VectorDB as ChromaDB
    participant LLM

    User->>Interface: Query (boss description)
    Interface->>Retrieval: Find relevant context
    Retrieval->>VectorDB: Semantic search
    VectorDB-->>Retrieval: Characters, Bosses, Teams
    Retrieval-->>Interface: Structured context
    
    alt MCP Mode
        Interface-->>User: Claude reasons directly
    else CLI Mode
        Interface->>LLM: Context + System Prompt
        LLM-->>Interface: Team composition
        Interface-->>User: Formatted results
    end
```

### Component Responsibilities

| Component | Purpose |
|-----------|---------|
| **Data Loader** | Load YAML files, validate against Pydantic models |
| **Vector Store** | Index entities, semantic search via ChromaDB |
| **Retrieval Service** | Combine exact lookups + semantic search |
| **Pipeline** | Assemble prompts, call LLM, parse results |
| **MCP Server** | Expose tools for Claude in Cursor |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `COTC_DATA_DIR` | `./data` | Path to data directory |
| `COTC_VECTOR_DIR` | `./.vectordb` | Path to vector database |
| `OPENAI_API_KEY` | — | OpenAI API key (for cloud LLM) |

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
ruff format src/
```

## Future Roadmap

- [x] MCP Server for Cursor/Claude integration
- [x] Import 260+ characters from community spreadsheet
- [x] Skill/passive data from Notion exports
- [ ] Manual role assignments for key characters
- [ ] Boss data population
- [ ] Proven team compositions
- [ ] Agent-based multi-step reasoning (LangGraph)
- [ ] User feedback loops for team ratings

## License

MIT License. See LICENSE file for details.

## Acknowledgments

Game data is sourced from the COTC community. This is a fan project and is not affiliated with Square Enix.
