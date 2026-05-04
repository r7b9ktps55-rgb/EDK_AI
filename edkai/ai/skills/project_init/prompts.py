"""Prompt builder for the project_init skill."""
from edkai.ai.skills.manager import SkillResult


def build_prompt(user_input: str, context: dict) -> SkillResult:
    project_type = context.get("project_type", "")  # web, cli, library, api
    language = context.get("language", "python")  # python, javascript, typescript, rust, go
    name = context.get("name", "my-project")
    features = context.get("features", [])  # e.g., ["testing", "linting", "ci/cd", "docker"]
    description = context.get("description", "")

    structure_templates = {
        "python": """Python project structure:
    {name}/
    ├── src/{name}/          # Source package
    ├── tests/               # Test files
    ├── docs/                # Documentation
    ├── pyproject.toml       # Project config
    ├── README.md
    ├── LICENSE
    └── .gitignore""",
        "javascript": """Node.js project structure:
    {name}/
    ├── src/                 # Source files
    ├── tests/               # Test files
    ├── package.json         # Dependencies
    ├── README.md
    ├── LICENSE
    └── .gitignore""",
        "rust": """Rust project structure:
    {name}/
    ├── src/
    │   └── main.rs          # Entry point
    ├── tests/               # Integration tests
    ├── Cargo.toml           # Package config
    ├── README.md
    ├── LICENSE
    └── .gitignore""",
        "go": """Go project structure:
    {name}/
    ├── cmd/                 # Entry points
    ├── internal/            # Private code
    ├── pkg/                 # Public libraries
    ├── go.mod               # Module definition
    ├── README.md
    ├── LICENSE
    └── .gitignore""",
    }

    prompt = f"""Generate a complete project scaffold for a new {language} {project_type} project named '{name}'.

{f"Description: {description}" if description else ""}

{f"Requested features: {', '.join(features)}" if features else ""}

Recommended project structure:
{structure_templates.get(language, structure_templates['python']).format(name=name)}

Generate the following files with full content:

1. **README.md** - Project overview, installation, usage
2. **Main configuration file** - pyproject.toml/package.json/Cargo.toml/go.mod with appropriate dependencies
3. **Entry point** - Main source file with boilerplate
4. **Test stub** - First test file with a simple test
5. **.gitignore** - Language-appropriate ignore patterns
6. **License** - MIT license file

{f"7. **Dockerfile** - Multi-stage build" if "docker" in features else ""}
{f"8. **CI/CD config** - GitHub Actions workflow for testing and linting" if "ci/cd" in features else ""}
{f"9. **Linting config** - Ruff/ESLint/clippy/golangci-lint configuration" if "linting" in features else ""}
{f"10. **Pre-commit hooks** - .pre-commit-config.yaml or husky setup" if "pre-commit" in features else ""}

Use modern best practices for {language} development. Include type hints, proper error handling, and logging setup where appropriate."""

    return SkillResult(prompt=prompt, context=context)
