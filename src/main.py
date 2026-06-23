"""
CLI Entry Point for COTC Tactician.

Provides commands for:
- Indexing game data
- Querying team compositions
- Exploring data
"""

import json
import logging
import os
from pathlib import Path

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table

from .pipeline import OllamaClient, OpenAIClient, ReasoningPipeline
from .retrieval import RetrievalService
from .roster import load_roster, owned_character_ids, roster_path
from .vector_store import VectorStore

# Setup rich console
console = Console()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(console=console, rich_tracebacks=True)],
)
logger = logging.getLogger(__name__)

# Create Typer app
app = typer.Typer(
    name="cotc-tactician",
    help="AI-powered team composition assistant for COTC",
    add_completion=False,
)


def get_data_dir() -> Path:
    """Get the data directory path."""
    # Check environment variable first
    if env_path := os.environ.get("COTC_DATA_DIR"):
        return Path(env_path)

    # Default to ./data relative to project root
    return Path(__file__).parent.parent / "data"


def get_vector_store_dir() -> Path:
    """Get the vector store directory path."""
    if env_path := os.environ.get("COTC_VECTOR_DIR"):
        return Path(env_path)

    return Path(__file__).parent.parent / ".vectordb"


def create_retrieval_service() -> RetrievalService:
    """Create retrieval service for read-only CLI commands (no LLM required)."""
    data_dir = get_data_dir()
    vector_dir = get_vector_store_dir()
    vector_store = VectorStore(persist_directory=vector_dir)
    service = RetrievalService(data_dir=data_dir, vector_store=vector_store)
    service.initialize()
    return service


def create_pipeline(
    llm_provider: str = "ollama",
    llm_model: str | None = None,
) -> ReasoningPipeline:
    """Create and configure the reasoning pipeline."""
    data_dir = get_data_dir()
    vector_dir = get_vector_store_dir()

    vector_store = VectorStore(persist_directory=vector_dir)
    pipeline = ReasoningPipeline(
        data_dir=data_dir,
        vector_store=vector_store,
    )

    # Configure LLM client
    if llm_provider == "openai":
        model = llm_model or "gpt-4-turbo-preview"
        client = OpenAIClient(model=model)
    else:
        model = llm_model or "llama3.1"
        client = OllamaClient(model=model)

    pipeline.set_llm_client(client)
    return pipeline


# =============================================================================
# COMMANDS
# =============================================================================


@app.command()
def index(
    force: bool = typer.Option(False, "--force", "-f", help="Force reindex"),
):
    """Index game data into the vector database."""
    console.print("[bold blue]COTC Tactician - Indexing Data[/]")
    console.print()

    data_dir = get_data_dir()
    vector_dir = get_vector_store_dir()

    console.print(f"Data directory: {data_dir}")
    console.print(f"Vector store: {vector_dir}")
    console.print()

    if not data_dir.exists():
        console.print(f"[red]Error: Data directory not found: {data_dir}[/]")
        raise typer.Exit(1)

    vector_store = VectorStore(persist_directory=vector_dir)
    pipeline = ReasoningPipeline(
        data_dir=data_dir,
        vector_store=vector_store,
    )

    with console.status("Indexing data..."):
        stats = pipeline.initialize(force_reindex=force)

    table = Table(title="Indexed Data")
    table.add_column("Entity Type", style="cyan")
    table.add_column("Count", style="green", justify="right")

    for entity_type, count in stats.items():
        table.add_row(entity_type.title(), str(count))

    console.print(table)
    console.print()
    console.print("[green]Indexing complete![/]")


@app.command()
def compose(
    boss_id: str | None = typer.Option(None, "--boss", "-b", help="Boss ID"),
    description: str | None = typer.Option(None, "--desc", "-d", help="Boss description"),
    characters: str | None = typer.Option(
        None, "--chars", "-c", help="Comma-separated character IDs"
    ),
    llm: str = typer.Option("ollama", "--llm", "-l", help="LLM provider (ollama or openai)"),
    model: str | None = typer.Option(None, "--model", "-m", help="LLM model name"),
    output_json: bool = typer.Option(False, "--json", help="Output raw JSON"),
):
    """Compose a team for a boss encounter."""
    console.print("[bold blue]COTC Tactician - Team Composition[/]")
    console.print()

    if not boss_id and not description:
        console.print("[red]Error: Must provide --boss or --desc[/]")
        raise typer.Exit(1)

    # Parse character list — explicit --chars overrides saved roster
    char_list = None
    if characters:
        char_list = [c.strip() for c in characters.split(",") if c.strip()]
    else:
        saved = load_roster()
        if saved and saved.characters:
            char_list = owned_character_ids(saved)
            console.print(
                f"[dim]Using roster from {roster_path()} ({len(char_list)} characters)[/]"
            )

    # Create pipeline
    try:
        pipeline = create_pipeline(llm_provider=llm, llm_model=model)
    except ImportError as e:
        console.print(f"[red]Error: Missing dependency for {llm}: {e}[/]")
        raise typer.Exit(1)

    with console.status("Initializing..."):
        pipeline.initialize()

    console.print(f"Boss: {boss_id or description[:50] + '...'}")
    if char_list:
        console.print(f"Available characters: {', '.join(char_list)}")
    console.print()

    with console.status("Analyzing and composing team..."):
        result = pipeline.compose_team(
            boss_id=boss_id,
            boss_description=description,
            available_character_ids=char_list,
        )

    if output_json:
        console.print(json.dumps(result, indent=2, default=str))
        return

    # Pretty print results
    if "error" in result:
        console.print(Panel(f"[red]{result['error']}[/]", title="Error"))
        return

    # Boss Analysis
    if "boss_analysis" in result:
        analysis = result["boss_analysis"]
        console.print(
            Panel(
                f"[bold]{analysis.get('summary', 'No summary')}[/]",
                title="Boss Analysis",
            )
        )

        if "key_mechanics" in analysis:
            console.print("\n[bold]Key Mechanics:[/]")
            for mech in analysis["key_mechanics"]:
                console.print(
                    f"  • {mech.get('mechanic_name', 'Unknown')}: "
                    f"{mech.get('counter_needed', 'No counter specified')}"
                )

    # Proposed Teams
    if "proposed_teams" in result:
        console.print("\n[bold blue]Proposed Teams:[/]")
        for i, team in enumerate(result["proposed_teams"], 1):
            console.print(
                Panel(
                    f"[bold]{team.get('name', f'Team {i}')}[/]\n"
                    f"Strategy: {team.get('strategy_type', 'unknown')}\n"
                    f"Confidence: {team.get('confidence', 'unknown')}\n"
                    f"Reason: {team.get('confidence_reason', 'N/A')}",
                    title=f"Team {i}",
                )
            )

            if "composition" in team:
                table = Table(show_header=True)
                table.add_column("Pos", style="cyan", width=4)
                table.add_column("Character", style="green")
                table.add_column("Role", style="yellow")
                table.add_column("Key Skills")

                for member in team["composition"]:
                    skills = member.get("key_skills", [])
                    if not skills and member.get("equipped_skills"):
                        skills = [
                            s.get("skill_name")
                            for s in member["equipped_skills"]
                            if s.get("skill_name")
                        ]
                    table.add_row(
                        str(member.get("position", "?")),
                        member.get("character_id", "?"),
                        member.get("role", "?"),
                        ", ".join(skills[:2]),
                    )

                console.print(table)

            if team.get("synergies_used"):
                console.print("\n[dim]Synergies:[/]")
                for syn in team["synergies_used"]:
                    console.print(f"  • {syn.get('synergy', 'Unknown')}")

            console.print()

    # Data Gaps
    if result.get("data_gaps"):
        console.print(
            Panel(
                "\n".join(f"• {gap}" for gap in result["data_gaps"]),
                title="[yellow]Data Gaps[/]",
            )
        )


@app.command()
def list_bosses():
    """List all indexed bosses."""
    with console.status("Loading data..."):
        service = create_retrieval_service()

    bosses = service.list_boss_ids()

    if not bosses:
        console.print("[yellow]No bosses indexed. Run 'index' command first.[/]")
        return

    console.print("[bold]Indexed Bosses:[/]")
    for boss_id in sorted(bosses):
        console.print(f"  • {boss_id}")


@app.command()
def list_characters():
    """List all indexed characters."""
    with console.status("Loading data..."):
        service = create_retrieval_service()

    characters = service.list_character_ids()

    if not characters:
        console.print("[yellow]No characters indexed. Run 'index' command first.[/]")
        return

    console.print("[bold]Indexed Characters:[/]")
    for char_id in sorted(characters):
        console.print(f"  • {char_id}")


@app.command()
def info(
    entity_type: str = typer.Argument(..., help="Type: boss, character, or team"),
    entity_id: str = typer.Argument(..., help="Entity ID"),
):
    """Get information about a specific entity."""
    with console.status("Loading data..."):
        service = create_retrieval_service()

    if entity_type == "boss":
        boss = service.get_boss_by_id(entity_id)
        data = boss.model_dump() if boss else None
    elif entity_type == "character":
        character = service.get_character_by_id(entity_id)
        data = character.model_dump() if character else None
    elif entity_type == "team":
        team = service.get_team_by_id(entity_id)
        data = team.model_dump() if team else None
    else:
        console.print(f"[red]Unknown entity type: {entity_type}[/]")
        raise typer.Exit(1)

    if data is None:
        console.print(f"[yellow]Not found: {entity_type} '{entity_id}'[/]")
        return

    console.print(json.dumps(data, indent=2, default=str))


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    entity_type: str = typer.Option(
        "all", "--type", "-t", help="Entity type: characters, bosses, teams, or all"
    ),
    limit: int = typer.Option(5, "--limit", "-n", help="Max results"),
):
    """Semantic search across game data."""
    with console.status("Loading data..."):
        service = create_retrieval_service()

    vs = service.vector_store

    results = []

    if entity_type in ("characters", "all"):
        chars = vs.search_characters(query, n_results=limit)
        for r in chars:
            r["type"] = "character"
            results.append(r)

    if entity_type in ("bosses", "all"):
        bosses = vs.search_bosses(query, n_results=limit)
        for r in bosses:
            r["type"] = "boss"
            results.append(r)

    if entity_type in ("teams", "all"):
        teams = vs.search_teams(query, n_results=limit)
        for r in teams:
            r["type"] = "team"
            results.append(r)

    if not results:
        console.print("[yellow]No results found.[/]")
        return

    table = Table(title=f"Search Results: '{query}'")
    table.add_column("Type", style="cyan")
    table.add_column("ID", style="green")
    table.add_column("Distance", justify="right")
    table.add_column("Preview")

    for r in sorted(results, key=lambda x: x.get("distance", 999))[:limit]:
        preview = r.get("document", "")[:50] + "..." if r.get("document") else ""
        table.add_row(
            r["type"],
            r["id"],
            f"{r.get('distance', 0):.3f}",
            preview,
        )

    console.print(table)


@app.command("roster-ui")
def roster_ui(
    port: int = typer.Option(8787, "--port", "-p", help="Local port"),
    no_open: bool = typer.Option(False, "--no-open", help="Do not open browser"),
    reload: bool = typer.Option(False, "--reload", help="Reload on file changes (dev)"),
):
    """Launch local web UI to manage your character roster."""
    try:
        import uvicorn
    except ImportError as e:
        console.print(
            "[red]Error: roster-ui requires the ui extra. "
            "Run: uv sync --extra ui[/]"
        )
        raise typer.Exit(1) from e

    from .roster_ui.app import create_app

    url = f"http://localhost:{port}"
    console.print(f"[bold blue]COTC Tactician — Roster UI[/]")
    console.print(f"Roster file: {roster_path()}")
    console.print(f"Open [link={url}]{url}[/] in your browser")
    if reload:
        console.print("[dim]Hot reload enabled — edit src/roster_ui/ and refresh[/]")
    console.print("[dim]Press Ctrl+C to stop[/]")
    console.print()

    if not no_open:
        import webbrowser

        webbrowser.open(url)

    data_dir = get_data_dir()
    if reload:
        import os

        os.environ.setdefault("COTC_DATA_DIR", str(data_dir))
        roster_ui_dir = Path(__file__).parent / "roster_ui"
        uvicorn.run(
            "src.roster_ui.app:create_app_for_uvicorn",
            factory=True,
            host="127.0.0.1",
            port=port,
            reload=True,
            reload_dirs=[str(roster_ui_dir)],
            log_level="warning",
        )
    else:
        app = create_app(data_dir)
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


@app.command("mcp-serve")
def mcp_serve():
    """
    Start the MCP server for Cursor/Claude integration.

    This exposes COTC game data as MCP tools that Claude can call.
    Use this instead of the compose command when working in Cursor.

    Configure Cursor by adding to ~/.cursor/mcp.json:

    {
      "mcpServers": {
        "cotc-tactician": {
          "command": "cotc-tactician",
          "args": ["mcp-serve"]
        }
      }
    }
    """
    from .mcp_server import run_mcp_server

    run_mcp_server()


def main():
    """Entry point."""
    app()


if __name__ == "__main__":
    main()
