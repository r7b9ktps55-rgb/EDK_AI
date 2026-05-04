# EDK_AI v5 — Universal AI Code Agent

> **"Like Claude Code, but in your terminal, with free AI models"**

EDK_AI is a terminal-based IDE with an integrated AI coding agent. Write, edit, refactor, and explore code with AI assistance — all without leaving your terminal. Works with free AI providers out of the box.

## Features

- **Agent Mode** — Conversational AI agent that can read, write, and refactor code
- **Free AI Providers** — Works with GitHub Models, Ollama, and Google Gemini at zero cost
- **Skills System** — Modular skill plugins (code-edit, test-run, git, search, file-ops)
- **TUI IDE** — Full terminal IDE with file tree, editor, terminal, and AI panels
- **Multi-Provider** — Seamlessly switch between AI providers
- **Local-First** — Your code never leaves your machine with Ollama

## Installation

### One-Line Installer

```bash
curl -fsSL https://raw.githubusercontent.com/r7b9ktps55-rgb/edkai/main/install.sh | bash
```

### Manual Installation

```bash
git clone https://github.com/r7b9ktps55-rgb/tstudio.git ~/.local/share/edkai
cd ~/.local/share/edkai
pip install -e "."
```

### Requirements

- Python >= 3.9
- pip

## Quick Start

### Launch the TUI IDE

```bash
edkai                          # Open current directory
edkai /path/to/project       # Open specific project
edkai --agent                # Start in agent REPL mode
```

### First-Time Setup

```bash
# Test your AI connection
edkai config --test

# List available providers
edkai config --list-providers

# Set active provider
edkai config --set-provider github_models
```

### Agent Mode

Agent mode provides a conversational interface to the AI coding assistant:

```bash
$ edkai --agent
EDK_AI Agent v5
> Explain the main function in app.py
  The main function initializes the application by...
> Refactor to use async/await
  I've updated the main function to use async/await pattern...
> Run the tests
  Running pytest... 12 passed, 0 failed
```

## Free AI Providers

EDK_AI works with multiple free AI providers:

| Provider | Models | Rate Limit | Setup |
|----------|--------|------------|-------|
| **GitHub Models** | Phi-4, Llama 3.3, Mistral | 150 req/day | GitHub token |
| **Ollama** | Llama, Mistral, CodeLlama | Unlimited | Install Ollama app |
| **Google Gemini** | Gemini 2.0 Flash | 60 req/min | API key (free tier) |

### Provider Configuration

Providers are configured in `~/.config/edkai/config.json`:

```json
{
  "active_provider": "github_models",
  "providers": [
    {
      "name": "github_models",
      "base_url": "https://models.inference.ai.azure.com",
      "default_model": "Phi-4",
      "api_key": "${GITHUB_TOKEN}",
      "enabled": true
    },
    {
      "name": "ollama",
      "base_url": "http://localhost:11434",
      "default_model": "codellama",
      "enabled": true
    },
    {
      "name": "gemini",
      "base_url": "https://generativelanguage.googleapis.com",
      "default_model": "gemini-2.0-flash",
      "api_key": "${GEMINI_API_KEY}",
      "enabled": false
    }
  ]
}
```

Environment variables (like `${GITHUB_TOKEN}`) are resolved at runtime.

## Skills System

The agent uses a modular skills system to perform actions:

| Skill | Description | Example |
|-------|-------------|---------|
| `code-edit` | Read, write, and modify files | "Refactor this function" |
| `test-run` | Run tests and report results | "Run the test suite" |
| `git` | Git operations (status, diff, commit) | "Show me the diff" |
| `search` | Search code across the project | "Find all TODO comments" |
| `file-ops` | List, grep, and navigate files | "Show me all Python files" |

Skills are automatically selected by the agent based on your request.

## Key Bindings

### Global

| Key | Action |
|-----|--------|
| `Ctrl+Q` | Quit |
| `Ctrl+S` | Save file |
| `Ctrl+O` | Open file |
| `Ctrl+N` | New file |
| `Ctrl+W` | Close current tab |
| `Ctrl+Tab` | Next tab |
| `Ctrl+Shift+Tab` | Previous tab |

### Editor

| Key | Action |
|-----|--------|
| `Ctrl+F` | Find in file |
| `Ctrl+H` | Replace |
| `Ctrl+G` | Go to line |
| `Ctrl+/` | Toggle comment |
| `Ctrl+D` | Duplicate line |
| `Alt+Up/Down` | Move line up/down |
| `Ctrl+Space` | AI autocomplete |

### Panels

| Key | Action |
|-----|--------|
| `Ctrl+B` | Toggle sidebar |
| `Ctrl+J` | Toggle terminal panel |
| `Ctrl+Shift+A` | Toggle AI agent panel |
| `Ctrl+Shift+G` | Toggle git panel |
| `Ctrl+Shift+T` | Toggle test panel |
| `Ctrl+P` | Command palette |

### Agent Panel

| Key | Action |
|-----|--------|
| `Enter` | Submit message |
| `Ctrl+Enter` | Multiline input |
| `Ctrl+C` | Cancel current operation |
| `Up/Down` | Navigate message history |

## Architecture

```
edkai/
├── main.py              # CLI entry point
├── app.py               # Textual App (main TUI)
├── core/
│   ├── config.py        # Configuration management
│   └── project.py       # Project state
├── ai/
│   ├── client.py        # Unified AI client
│   └── providers.py     # Provider registry
├── agent/
│   ├── orchestrator.py  # Agent loop & planning
│   ├── repl.py          # Agent REPL interface
│   └── skills.py        # Skill definitions
├── widgets/             # Textual widgets
│   ├── agent_panel.py   # AI agent REPL panel
│   ├── ai_panel.py      # AI chat panel
│   ├── editor.py        # Code editor
│   ├── file_tree.py     # Project file tree
│   ├── terminal.py      # Integrated terminal
│   ├── git_panel.py     # Git status panel
│   ├── search_panel.py  # Project search
│   ├── test_panel.py    # Test runner panel
│   └── status_bar.py    # Status bar
└── themes/              # Color themes
```

The application follows a layered architecture:

1. **TUI Layer** — Textual widgets handle rendering and user input
2. **Agent Layer** — Orchestrator manages the AI reasoning loop
3. **AI Layer** — Provider-agnostic client for LLM communication
4. **Core Layer** — Project state, configuration, and file operations

## Configuration

Configuration is stored in `~/.config/edkai/config.json`:

```json
{
  "active_provider": "github_models",
  "theme": "dark",
  "agent_max_iterations": 10,
  "auto_save": true,
  "show_line_numbers": true,
  "tab_size": 4,
  "use_spaces": true,
  "providers": []
}
```

## Development

```bash
# Clone the repository
git clone https://github.com/r7b9ktps55-rgb/tstudio.git
cd edkai

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Run the TUI
python -m edkai
```

## License

MIT License — see LICENSE for details.
