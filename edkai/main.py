"""CLI entry point for Terminal Studio v5.

Commands:
  edkai              — Launch TUI IDE
  edkai agent        — Launch AI agent REPL
  edkai config       — Configure settings
"""
from __future__ import annotations
import argparse
import asyncio
import sys
from pathlib import Path

from edkai.core.config import StudioConfig
from edkai.core.project import Project


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="edkai",
        description="Terminal Studio v5 — Universal AI Code Agent",
    )
    parser.add_argument("--version", action="store_true", help="Show version")
    parser.add_argument("--provider", default="auto", help="AI provider (github_models, ollama, gemini, openai_compat, auto)")
    parser.add_argument("--model", default="", help="AI model override")
    parser.add_argument("--agent", action="store_true", help="Start in agent mode")
    parser.add_argument("path", nargs="?", default=".", help="Project path")
    
    args = parser.parse_args(argv)
    
    if args.version:
        print("edkai 0.5.0")
        return 0
    
    # Agent mode
    if args.agent or args.path == "agent":
        return asyncio.run(_run_agent(args))
    
    # Config mode
    if args.path == "config":
        return _run_config(args)
    
    # IDE mode (default)
    return _run_ide(args)


def _run_ide(args) -> int:
    """Launch TUI IDE."""
    from edkai.app import StudioApp
    
    target = Path(args.path).expanduser().resolve()
    if target.is_file():
        project = Project(target.parent)
        project.open_file(target)
    else:
        project = Project(target)
    
    config = StudioConfig.load()
    app = StudioApp(project=project, config=config)
    app.run()
    return 0


async def _run_agent(args) -> int:
    """Launch AI agent REPL."""
    from edkai.ai.providers import ProviderRegistry
    from edkai.ai.client import AIClient
    from edkai.agent.orchestrator import AgentOrchestrator
    from edkai.agent.repl import AgentREPL
    
    config = StudioConfig.load()
    if args.provider != "auto":
        config.active_provider = args.provider
    if args.model:
        for p in config.providers:
            if p.name == config.active_provider or config.active_provider == "auto":
                p.default_model = args.model
                break
    
    registry = ProviderRegistry(config)
    try:
        client = registry.get_client(config.active_provider)
    except Exception as e:
        print(f"Failed to initialize AI provider: {e}", file=sys.stderr)
        print("Tip: Run 'edkai config --list-providers' to see available providers.", file=sys.stderr)
        return 1
    
    project_root = Path.cwd()
    orchestrator = AgentOrchestrator(client, project_root, config)
    repl = AgentREPL(orchestrator)
    await repl.start()
    return 0


def _run_config(args) -> int:
    """Handle config commands."""
    config = StudioConfig.load()
    
    if hasattr(args, 'list_providers') and args.list_providers:
        print("Available AI providers:")
        for p in config.providers:
            status = "✓" if p.enabled else "✗"
            print(f"  [{status}] {p.name}: {p.base_url} (default: {p.default_model})")
        return 0
    
    if hasattr(args, 'set_provider') and args.set_provider:
        config.active_provider = args.set_provider
        config.save()
        print(f"Active provider set to: {args.set_provider}")
        return 0
    
    if hasattr(args, 'test') and args.test:
        from edkai.ai.providers import ProviderRegistry
        registry = ProviderRegistry(config)
        provider = registry.default_provider
        if not provider:
            print("No configured provider found.", file=sys.stderr)
            return 1
        print(f"Testing provider: {provider.name} (model: {provider.default_model})")
        try:
            result = asyncio.get_event_loop().run_until_complete(
                provider.complete("Say 'Hello from Terminal Studio!' in one word.")
            )
            print(f"✓ Success: {result.strip()}")
        except Exception as e:
            print(f"✗ Failed: {e}", file=sys.stderr)
            return 1
        return 0
    
    # Default: show config
    print(f"Terminal Studio v5 Configuration")
    print(f"  Active provider: {config.active_provider}")
    print(f"  Theme: {config.theme}")
    print(f"  Agent max iterations: {config.agent_max_iterations}")
    print(f"  Config file: {Path.home() / '.config' / 'edkai' / 'config.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
