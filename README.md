# EDK_AI v6 — Ultimate AI Code Agent

> **"Like Claude Code, but in your terminal, with 14 free AI models"**

EDK_AI is a terminal-based AI coding agent that combines a beautiful TUI IDE with an intelligent conversational agent. Write, edit, refactor, and explore code with AI assistance — all without leaving your terminal. Works with **14 free AI providers** out of the box.

## Features

- **Agent Mode** — Conversational AI agent that reads, writes, edits, and runs code
- **14 Free AI Providers** — Auto-fallback when rate limits hit
- **741 NL Patterns** — Talk in natural language (EN, RU, ZH, ES, DE, FR, JP, PT)
- **Beautiful TUI** — GitHub Dark theme, syntax highlighting, status bar
- **Skills System** — 10 modular AI skills (code review, refactor, test gen, etc.)
- **Auto Provider Switching** — When one model hits limit, automatically tries next

## Quick Start

```bash
# Install
pip install git+https://github.com/r7b9ktps55-rgb/EDK_AI.git

# Launch IDE
edkai

# Launch Agent
edkai --agent

# Test connection
edkai config --test
```

## 14 Free AI Providers

| Provider | Free Tier | Speed | Best For |
|----------|-----------|-------|----------|
| **GitHub Models** | 50 chat + 2K completions/month | Medium | General coding |
| **Groq** | 14,400 req/day | **Ultra-fast** | Real-time assistance |
| **Google Gemini** | 1,500 req/day | Fast | Documentation |
| **Cerebras** | 1M tokens/day | **2600+ t/s** | Large code analysis |
| **Mistral** | 1B tokens/month | Fast | Code generation |
| **OpenRouter** | 50 req/day | Medium | Model variety |
| **Cloudflare** | 10K neurons/day | Edge | Quick tasks |
| **Cohere** | 1K req/month | Medium | Command generation |
| **DeepSeek** | 5M tokens signup | Fast | Deep reasoning |
| **Together** | $25 credits | Medium | Latest models |
| **NVIDIA** | 40 RPM | Medium | GPU inference |
| **SiliconFlow** | 3 free models | Medium | Chinese models |
| **Ollama** | Unlimited (local) | Local | Privacy |
| **OpenAI-compat** | Fallback | — | Custom endpoints |

## Natural Language Commands

EDK_AI understands natural language in **8 languages**:

```
> покажи main.py           → read_file(path="main.py")
> find all TODO            → search_code(pattern="TODO")
> запусти тесты            → shell(command="pytest")
> git status               → git_status()
> commit update            → git_commit(message="update")
> 创建文件 test.py          → write_file(path="test.py")
> format code              → shell(command="black .")
> optimize this            → optimize skill
```

## Architecture

```
edkai/
  agent/              # AI Agent (REPL, tools, orchestrator, NL router)
  ai/
    providers/        # 14 AI providers + auto-fallback
    skills/           # 10 gstack-style skills
  core/               # Config, project, git, runner
  widgets/            # TUI widgets (AgentPanel, Editor, FileTree...)
  syntax/             # Syntax highlighting
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+A` | Toggle Agent Panel |
| `Ctrl+S` | Save file |
| `Ctrl+Q` | Quit |
| `Ctrl+P` | Command palette |
| `Ctrl+F` | Search files |
| `Ctrl+G` | Git panel |
| `Ctrl+T` | Test panel |

## License

MIT
