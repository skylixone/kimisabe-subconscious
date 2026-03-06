#!/usr/bin/env python3
"""CLI for Kimi Subconscious."""

from __future__ import annotations

import os
import sys
import time
from datetime import timedelta
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .injector import SubconsciousInjector
from .letta_client import LettaClient, LettaError, SubconsciousAgent
from .models import DetectedInsight, InsightType
from .observability import HealthChecker, init_observability, StructuredLogger
from .parser import WireParser, format_for_letta, InsightDetector
from .phoenix import enable_phoenix_mode, should_auto_restart
from .state import StateManager

console = Console()


def get_project_path() -> Path:
    """Get the current project path."""
    return Path.cwd()


def ensure_setup(state: StateManager) -> tuple[LettaClient, SubconsciousAgent]:
    """Ensure Kimi Subconscious is set up. Returns client and agent."""
    api_key = state.get_api_key()
    
    if not api_key:
        console.print("[red]Error:[/red] Letta API key not configured.")
        console.print("Run [bold]kimisub setup[/bold] to configure.")
        sys.exit(1)
    
    base_url = state.get_letta_base_url()
    client = LettaClient(api_key=api_key, base_url=base_url)
    agent = SubconsciousAgent(client, agent_id=state.get_agent_id())
    
    # Resolve agent
    if not agent.agent_id:
        console.print("[red]Error:[/red] No Subconscious agent configured.")
        console.print("Run [bold]kimisub setup[/bold] to import the agent.")
        sys.exit(1)
    
    return client, agent


@click.group()
@click.version_option(version=__import__("kimi_subconscious").__version__)
def main():
    """Kimi Subconscious - A memory layer for Kimi Code."""
    pass


@main.command()
def setup():
    """Set up Kimi Subconscious."""
    console.print(Panel.fit("Kimi Subconscious Setup", style="bold blue"))
    
    state = StateManager()
    
    # Get API key
    api_key = state.get_api_key()
    if api_key:
        masked = api_key[:10] + "..." + api_key[-4:]
        console.print(f"Current API key: [dim]{masked}[/dim]")
        if not click.confirm("Change API key?"):
            return
    
    api_key = click.prompt("Enter your Letta API key", hide_input=True)
    state.set_api_key(api_key)
    
    # Test connection
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
        task = progress.add_task("Connecting to Letta...", total=None)
        
        try:
            client = LettaClient(api_key=api_key)
            models = client.list_models()
            progress.update(task, description=f"Connected! {len(models)} models available.")
            time.sleep(1)
        except Exception as e:
            progress.update(task, description=f"[red]Connection failed: {e}[/red]")
            sys.exit(1)
    
    # Import or configure agent
    agent_id = state.get_agent_id()
    if agent_id:
        console.print(f"Current agent: [dim]{agent_id}[/dim]")
        if not click.confirm("Re-import default agent?"):
            console.print("[green]Setup complete![/green]")
            return
    
    # Import default agent
    af_path = Path(__file__).parent.parent / "Subconscious.af"
    if not af_path.exists():
        console.print(f"[yellow]Warning:[/yellow] Default agent file not found at {af_path}")
        console.print("Please provide the path to the Subconscious.af file:")
        af_path = Path(click.prompt("Path to Subconscious.af"))
    
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
        task = progress.add_task("Importing agent...", total=None)
        
        try:
            agent = SubconsciousAgent(client)
            agent_id = agent.import_default_agent(af_path)
            state.set_agent_id(agent_id)
            progress.update(task, description=f"Agent imported: {agent_id}")
            
            # Ensure model is available
            agent.agent_id = agent_id
            new_model = agent.ensure_model_available()
            if new_model:
                progress.update(task, description=f"Model configured: {new_model}")
            
            time.sleep(1)
        except Exception as e:
            progress.update(task, description=f"[red]Import failed: {e}[/red]")
            sys.exit(1)
    
    console.print("[green]Setup complete![/green]")
    console.print(f"Agent ID: [bold]{agent_id}[/bold]")
    console.print("")
    console.print("Next steps:")
    console.print("  1. Run [bold]kimisub sync[/bold] in your project directories")
    console.print("  2. Or start the daemon: [bold]kimisub daemon --start[/bold]")


@main.command()
@click.option("--project", "-p", type=Path, help="Project path (default: current directory)")
def status(project: Path | None):
    """Show status for current project."""
    state = StateManager()
    project_path = project or get_project_path()
    project_hash = state.get_project_hash(project_path)
    
    # Build status table
    table = Table(title=f"Subconscious Status: {project_path.name}")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    
    # Project info
    table.add_row("Project Path", str(project_path))
    table.add_row("Project Hash", project_hash[:16] + "...")
    
    # Config
    api_key = state.get_api_key()
    table.add_row("API Key", "[dim]" + (api_key[:10] + "..." if api_key else "Not set") + "[/dim]")
    
    agent_id = state.get_agent_id()
    table.add_row("Agent ID", agent_id[:20] + "..." if agent_id else "Not set")
    
    # Sessions
    conversations = state.load_conversations(project_hash)
    table.add_row("Tracked Sessions", str(len(conversations)))
    
    # SUBCONSCIOUS.md
    sub_path = state.get_subconscious_path(project_hash, project_path)
    if sub_path.exists():
        table.add_row("SUBCONSCIOUS.md", str(sub_path))
        table.add_row("Last Modified", sub_path.stat().st_mtime)
    else:
        table.add_row("SUBCONSCIOUS.md", "[yellow]Not created yet[/yellow]")
    
    console.print(table)


@main.command()
@click.option("--project", "-p", type=Path, help="Project path (default: current directory)")
@click.option("--force", "-f", is_flag=True, help="Force send even if no insights detected")
def sync(project: Path | None, force: bool):
    """Sync current project session to Letta."""
    state = StateManager()
    project_path = project or get_project_path()
    project_hash = state.get_project_hash(project_path)
    
    console.print(Panel.fit(f"Sync: {project_path.name}", style="bold blue"))
    
    # Setup check
    client, agent = ensure_setup(state)
    
    # Find Kimi session
    kimi_sessions = state.get_kimi_sessions_dir()
    if not kimi_sessions:
        console.print("[red]Error:[/red] Kimi sessions directory not found.")
        sys.exit(1)
    
    project_session_dir = kimi_sessions / project_hash
    if not project_session_dir.exists():
        console.print(f"[yellow]No active Kimi session for this project.[/yellow]")
        console.print(f"Start a Kimi session in {project_path} first.")
        sys.exit(0)
    
    # Get most recent session
    sessions = sorted(project_session_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    if not sessions:
        console.print("[yellow]No sessions found.[/yellow]")
        sys.exit(0)
    
    session_id = sessions[0].name
    session_path = sessions[0]
    wire_path = session_path / "wire.jsonl"
    
    if not wire_path.exists():
        console.print("[yellow]No wire.jsonl found.[/yellow]")
        sys.exit(0)
    
    console.print(f"Session: [dim]{session_id}[/dim]")
    
    # Parse wire.jsonl
    with console.status("Parsing conversation..."):
        parser = WireParser(wire_path)
        
        # Load last read position
        last_read = state.load_last_read(project_hash, session_id)
        new_messages, new_offset = parser.parse_new(last_read["offset"])
        
        if not new_messages and not force:
            console.print("[green]No new messages to sync.[/green]")
            return
        
        console.print(f"New messages: [bold]{len(new_messages)}[/bold]")
        
        # Build turns
        parser.parse_all()  # Load all to build complete turns
        turns = parser.build_turns()
        
        # Detect insights
        detector = InsightDetector(turns)
        insights = detector.detect_insights()
        
        console.print(f"Insights detected: [bold]{len(insights)}[/bold]")
        for insight in insights:
            console.print(f"  • {insight.type.value}: {insight.description}")
    
    if not insights and not force:
        console.print("[dim]No insights to send. Use --force to send anyway.[/dim]")
        return
    
    # Get or create conversation
    with console.status("Connecting to Letta..."):
        conversation_id = state.get_conversation_id(project_hash, session_id)
        
        if not conversation_id:
            conversation_id = client.create_conversation(agent.agent_id)
            state.set_conversation_id(project_hash, session_id, conversation_id, agent.agent_id)
            console.print(f"Created conversation: [dim]{conversation_id}[/dim]")
    
    # Format and send
    with console.status("Sending to Letta..."):
        content = format_for_letta(turns, insights if insights else None)
        
        # Record insights in local DB
        for insight in insights:
            state.record_insight(
                project_hash,
                insight.type.value,
                insight.confidence,
                insight.description,
                session_id,
                sent_to_letta=True,
            )
        
        # Send to Letta
        success = client.send_message(conversation_id, content)
        
        if not success:
            console.print("[yellow]Conversation busy - will retry on next sync.[/yellow]")
            return
        
        # Update last read
        state.save_last_read(project_hash, session_id, new_offset, last_read.get("last_message_id"))
    
    console.print("[green]Sync complete![/green]")
    
    # Check for new guidance
    with console.status("Checking for guidance..."):
        time.sleep(2)  # Give Letta a moment to respond
        
        last_seen = state.get_last_seen_message(project_hash, session_id)
        guidance_messages, newest_id = agent.get_new_guidance(conversation_id, last_seen)
        
        if guidance_messages:
            console.print(f"\n[bold]New guidance from Subconscious:[/bold]")
            for msg in guidance_messages:
                console.print(Panel(msg, style="blue"))
            
            # Update SUBCONSCIOUS.md
            state.set_last_seen_message(project_hash, session_id, newest_id)
            update_subconscious(project_hash, project_path, agent, conversation_id, guidance_messages)


def update_subconscious(
    project_hash: str,
    project_path: Path,
    agent: SubconsciousAgent,
    conversation_id: str,
    guidance: list[str],
) -> None:
    """Update SUBCONSCIOUS.md with new guidance."""
    state = StateManager()
    
    # Get memory blocks
    try:
        blocks = agent.get_memory_blocks()
    except Exception:
        blocks = []
    
    # Generate content
    injector = SubconsciousInjector(agent_name="Subconscious")
    content = injector.generate(
        memory_blocks=blocks,
        guidance_messages=guidance,
        agent_id=agent.agent_id,
        conversation_id=conversation_id,
        is_hosted="localhost" not in agent.client.base_url,
    )
    
    # Write file
    path = state.write_subconscious(project_hash, content, project_path)
    state.ensure_gitignore(project_path)
    
    console.print(f"\n[green]Updated:[/green] {path}")


@main.command()
@click.option("--project", "-p", type=Path, help="Project path (default: current directory)")
def consolidate(project: Path | None):
    """Run daily memory consolidation."""
    state = StateManager()
    project_path = project or get_project_path()
    project_hash = state.get_project_hash(project_path)
    
    console.print(Panel.fit(f"Daily Consolidation: {project_path.name}", style="bold blue"))
    
    # Setup check
    client, agent = ensure_setup(state)
    
    # Get unsent insights
    unsent = state.get_unsent_insights(project_hash)
    
    console.print(f"Unsent insights: [bold]{len(unsent)}[/bold]")
    
    # Find or create a conversation for consolidation
    # We use a special "consolidation" session ID
    consolidation_session = "consolidation"
    conversation_id = state.get_conversation_id(project_hash, consolidation_session)
    
    if not conversation_id:
        conversation_id = client.create_conversation(agent.agent_id)
        state.set_conversation_id(project_hash, consolidation_session, conversation_id, agent.agent_id)
    
    # Send consolidation message
    with console.status("Consolidating memories..."):
        message = f"""<kimi_consolidation>
<timestamp>{time.strftime("%Y-%m-%d %H:%M")}</timestamp>

<unsent_insights count="{len(unsent)}">
{chr(10).join(f"  - [{i['type']}] {i['description']}" for i in unsent[:20])}
</unsent_insights>

<instructions>
This is your daily memory consolidation. Review the unsent insights above,
update your memory blocks as needed, and prepare guidance for the next session.
Focus on patterns, preferences, and any pending items that need attention.
</instructions>
</kimi_consolidation>"""
        
        success = client.send_message(conversation_id, message)
        
        if success:
            # Mark insights as sent
            if unsent:
                state.mark_insights_sent(project_hash, [i["id"] for i in unsent])
            console.print("[green]Consolidation sent![/green]")
        else:
            console.print("[yellow]Conversation busy - skipped.[/yellow]")
    
    # Check for guidance
    with console.status("Checking for guidance..."):
        time.sleep(2)
        
        last_seen = state.get_last_seen_message(project_hash, consolidation_session)
        guidance_messages, newest_id = agent.get_new_guidance(conversation_id, last_seen)
        
        if guidance_messages:
            console.print(f"\n[bold]Guidance from Subconscious:[/bold]")
            for msg in guidance_messages:
                console.print(Panel(msg, style="blue"))
            
            state.set_last_seen_message(project_hash, consolidation_session, newest_id)
            update_subconscious(project_hash, project_path, agent, conversation_id, guidance_messages)


@main.command()
def guidance():
    """View current guidance."""
    state = StateManager()
    project_path = get_project_path()
    project_hash = state.get_project_hash(project_path)
    
    content = state.get_subconscious_content(project_hash, project_path)
    
    if not content:
        console.print("[yellow]No SUBCONSCIOUS.md found.[/yellow]")
        console.print("Run [bold]kimisub sync[/bold] to generate it.")
        return
    
    console.print(content)


@main.group()
def daemon():
    """Manage the background daemon."""
    pass


@daemon.command(name="start")
@click.option("--foreground", "-f", is_flag=True, help="Run in foreground (don't detach)")
def daemon_start(foreground: bool):
    """Start the background daemon."""
    from .daemon import start_daemon
    
    state = StateManager()
    
    # Check if already running
    pid_file = state.data_dir / "daemon.pid"
    if pid_file.exists():
        try:
            with open(pid_file) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)  # Check if process exists
            console.print(f"[yellow]Daemon already running (PID {pid})[/yellow]")
            return
        except (ValueError, OSError, ProcessLookupError):
            # Stale PID file
            pid_file.unlink()
    
    if foreground:
        console.print("Starting daemon in foreground...")
        start_daemon(foreground=True)
    else:
        console.print("Starting daemon...")
        pid = start_daemon(foreground=False)
        console.print(f"[green]Daemon started (PID {pid})[/green]")


@daemon.command(name="stop")
def daemon_stop():
    """Stop the background daemon."""
    state = StateManager()
    pid_file = state.data_dir / "daemon.pid"
    
    if not pid_file.exists():
        console.print("[yellow]Daemon not running.[/yellow]")
        return
    
    try:
        with open(pid_file) as f:
            pid = int(f.read().strip())
        
        os.kill(pid, 15)  # SIGTERM
        console.print(f"[green]Daemon stopped (PID {pid})[/green]")
        pid_file.unlink()
    except (ValueError, OSError, ProcessLookupError) as e:
        console.print(f"[red]Error stopping daemon: {e}[/red]")
        pid_file.unlink()


@daemon.command(name="status")
def daemon_status():
    """Check daemon status."""
    state = StateManager()
    pid_file = state.data_dir / "daemon.pid"
    
    if pid_file.exists():
        try:
            with open(pid_file) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            console.print(f"[green]Daemon running (PID {pid})[/green]")
        except (ValueError, OSError, ProcessLookupError):
            console.print("[yellow]Daemon not running (stale PID file)[/yellow]")
            pid_file.unlink()
    else:
        console.print("[yellow]Daemon not running.[/yellow]")


@main.command()
def config():
    """Show configuration."""
    state = StateManager()
    
    table = Table(title="Kimi Subconscious Configuration")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Data Directory", str(state.data_dir))
    table.add_row("Config File", str(state.config_path))
    
    cfg = state.get_config()
    api_key = cfg.get("letta_api_key", "")
    table.add_row("API Key", api_key[:10] + "..." + api_key[-4:] if api_key else "Not set")
    
    agent_id = cfg.get("agent_id", "")
    table.add_row("Agent ID", agent_id[:30] + "..." if agent_id else "Not set")
    
    table.add_row("Base URL", cfg.get("letta_base_url", "https://api.letta.com"))
    
    phoenix = cfg.get("phoenix_mode", False)
    table.add_row("Phoenix Mode", "[green]enabled[/green]" if phoenix else "[dim]disabled[/dim]")
    
    console.print(table)


@main.command()
@click.option("--deep", "-d", is_flag=True, help="Perform deep checks (API, storage)")
@click.option("--json", "-j", is_flag=True, help="Output as JSON")
def health(deep: bool, json: bool):
    """Check health of the subconscious system."""
    state = StateManager()
    
    # Initialize observability for health check
    logger, liveness, metrics = init_observability(state.data_dir)
    checker = HealthChecker(state, logger, liveness, metrics)
    
    with console.status("Checking health..." if deep else "Checking basic health..."):
        status = checker.check(deep=deep)
    
    if json:
        console.print(status.to_json(indent=True))
        return
    
    # Visual output
    overall_color = {
        "healthy": "green",
        "degraded": "yellow",
        "unhealthy": "red",
        "unknown": "dim",
    }.get(status.overall, "dim")
    
    console.print(Panel(
        f"[bold {overall_color}]{status.overall.upper()}[/bold {overall_color}]",
        title="Health Status",
        border_style=overall_color,
    ))
    
    table = Table(title="Components")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Details", style="dim")
    
    # Daemon
    if status.daemon_running:
        uptime = ""
        if status.daemon_uptime_seconds:
            uptime_str = str(timedelta(seconds=int(status.daemon_uptime_seconds)))
            uptime = f"uptime: {uptime_str}"
        table.add_row("Daemon", "[green]running[/green]", f"PID {status.daemon_pid} {uptime}")
    else:
        table.add_row("Daemon", "[red]stopped[/red]", "")
    
    # Watchdog
    if status.watcher_alive:
        age = f"{status.watchdog_ping_age_seconds:.0f}s ago" if status.watchdog_ping_age_seconds else ""
        table.add_row("Watchdog", "[green]alive[/green]", age)
    else:
        stale = f"{status.watchdog_ping_age_seconds:.0f}s stale" if status.watchdog_ping_age_seconds else "no heartbeat"
        table.add_row("Watchdog", "[red]stale[/red]", stale)
    
    # API (deep check only)
    if deep:
        if status.api_reachable:
            latency = f"{status.api_latency_ms:.0f}ms" if status.api_latency_ms else ""
            table.add_row("API", "[green]reachable[/green]", latency)
        else:
            error = status.api_last_error or "unreachable"
            table.add_row("API", "[red]unreachable[/red]", error[:50])
    
    # Storage
    if status.storage_writable:
        free = ""
        if status.storage_free_bytes:
            free_gb = status.storage_free_bytes / (1024**3)
            free = f"{free_gb:.1f}GB free ({status.storage_free_percent:.0f}%)"
        table.add_row("Storage", "[green]writable[/green]", free)
    else:
        table.add_row("Storage", "[red]not writable[/red]", "")
    
    # Queue
    queue_status = f"{status.unsent_insights_count} unsent"
    if status.oldest_unsent_age_hours and status.oldest_unsent_age_hours > 24:
        queue_status = f"[yellow]{queue_status}[/yellow]"
    table.add_row("Queue", queue_status, "")
    
    console.print(table)
    
    # Recent errors
    if status.recent_errors:
        console.print(f"\n[yellow]Recent errors ({len(status.recent_errors)} in last hour):[/yellow]")
        for err in status.recent_errors[-5:]:
            console.print(f"  [dim]{err['timestamp']}[/dim] {err['component']}: {err['message']}")
    
    # Log location
    from platformdirs import user_log_dir
    log_dir = Path(user_log_dir("kimi-subconscious", "kimi-subconscious"))
    console.print(f"\n[dim]Logs: {log_dir}[/dim]")


@main.group()
def phoenix():
    """Auto-restart (Phoenix) mode - seamless memory integration."""
    pass


@phoenix.command(name="enable")
def phoenix_enable():
    """Enable auto-restart when new guidance arrives."""
    enable_phoenix_mode(True)
    console.print("[green]Phoenix mode enabled.[/green]")
    console.print("Kimi will now auto-restart when new memories are integrated.")
    console.print("")
    console.print("[dim]The flow:[/dim]")
    console.print("  1. You: 'Remember to use aerospace-ui'")
    console.print("  2. Daemon sends to Letta → Gets guidance back")
    console.print("  3. Kimi auto-restarts with --continue")
    console.print("  4. You: 🕶️ 'I know kung-fu'")


@phoenix.command(name="disable")
def phoenix_disable():
    """Disable auto-restart."""
    enable_phoenix_mode(False)
    console.print("[yellow]Phoenix mode disabled.[/yellow]")
    console.print("Use 'kimisub sync' manually to refresh context.")


if __name__ == "__main__":
    main()
