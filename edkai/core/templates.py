"""Project template generator for Terminal Studio.

Creates entire project structures from built-in or AI-generated templates.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from edkai.ai.client import AIClient

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

DEFAULT_TEMPLATE_DIR = Path.home() / ".config" / "edkai" / "templates"


# ---------------------------------------------------------------------------
# TemplateManager
# ---------------------------------------------------------------------------

class TemplateManager:
    """Generates entire project structures from templates.

    Built-in templates provide scaffolding for common project archetypes:
    ``python-cli``, ``python-api``, ``react-app``, ``rust-cli``, ``go-api``.

    User-defined templates can be saved to and loaded from
    ``~/.config/edkai/templates/``.

    Example:
        >>> tm = TemplateManager()
        >>> tm.create_project("python-cli", Path("./my-tool"), {"NAME": "my_tool"})
    """

    def __init__(self, ai_client: AIClient | None = None) -> None:
        """Initialise the template manager.

        Args:
            ai_client: Optional AI client for custom template generation.
        """
        self._ai_client = ai_client
        self._builtins: Dict[str, dict[str, Any]] = self._load_builtins()
        self._custom_dir: Path = DEFAULT_TEMPLATE_DIR
        self._custom_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Built-in templates
    # ------------------------------------------------------------------

    def _load_builtins(self) -> Dict[str, dict[str, Any]]:
        """Return the hard-coded built-in project templates."""
        return {
            "python-cli": {
                "description": "Python CLI tool with argparse",
                "files": {
                    "$NAME/main.py": (
                        "#!/usr/bin/env python3\n"
                        "\"\"\"$DESCRIPTION\"\"\"\n"
                        "\n"
                        "import argparse\n"
                        "import sys\n"
                        "from pathlib import Path\n"
                        "\n"
                        "\n"
                        "def main(argv: List[str] | None = None) -> int:\n"
                        "    parser = argparse.ArgumentParser(description=\"$DESCRIPTION\")\n"
                        "    parser.add_argument(\"--version\", action=\"version\", version=\"%(prog)s 0.1.0\")\n"
                        "    args = parser.parse_args(argv)\n"
                        "    print(\"Hello from $NAME!\")\n"
                        "    return 0\n"
                        "\n"
                        "\n"
                        'if __name__ == "__main__":\n'
                        "    sys.exit(main())\n"
                    ),
                    "$NAME/__init__.py": (
                        "\"\"\"$NAME package.\"\"\"\n"
                        "\n"
                        '__version__ = "0.1.0"\n'
                    ),
                    "setup.py": (
                        "from setuptools import setup, find_packages\n"
                        "\n"
                        "setup(\n"
                        '    name="$NAME",\n'
                        '    version="0.1.0",\n'
                        '    description="$DESCRIPTION",\n'
                        '    author="$AUTHOR",\n'
                        '    packages=find_packages(),\n'
                        "    entry_points={\n"
                        '        "console_scripts": [\n'
                        '            "$NAME=$NAME.main:main",\n'
                        "        ],\n"
                        "    },\n"
                        '    python_requires=">=3.9",\n'
                        ")\n"
                    ),
                    "pyproject.toml": (
                        "[build-system]\n"
                        'requires = ["setuptools>=61.0", "wheel"]\n'
                        'build-backend = "setuptools.build_meta"\n'
                        "\n"
                        "[project]\n"
                        'name = "$NAME"\n'
                        'version = "0.1.0"\n'
                        'description = "$DESCRIPTION"\n'
                        'requires-python = ">=3.9"\n'
                        "\n"
                        "[project.scripts]\n"
                        "$NAME = \"$NAME.main:main\"\n"
                    ),
                    "README.md": (
                        "# $NAME\n"
                        "\n"
                        "$DESCRIPTION\n"
                        "\n"
                        "## Installation\n"
                        "\n"
                        "```bash\n"
                        "pip install -e .\n"
                        "```\n"
                        "\n"
                        "## Usage\n"
                        "\n"
                        "```bash\n"
                        "$NAME --help\n"
                        "```\n"
                    ),
                },
            },
            "python-api": {
                "description": "FastAPI web service with models and routes",
                "files": {
                    "$NAME/__init__.py": (
                        "\"\"\"$NAME API package.\"\"\"\n"
                        "\n"
                        '__version__ = "0.1.0"\n'
                    ),
                    "$NAME/main.py": (
                        "from fastapi import FastAPI\n"
                        "\n"
                        "from $NAME.routers import items\n"
                        "\n"
                        "app = FastAPI(title=\"$NAME\", version=\"0.1.0\")\n"
                        "\n"
                        "app.include_router(items.router, prefix=\"/items\", tags=[\"items\"])\n"
                        "\n"
                        "\n"
                        "@app.get(\"/\")\n"
                        "async def root():\n"
                        '    return {"message": "Welcome to $NAME"}\n'
                    ),
                    "$NAME/models.py": (
                        "from pydantic import BaseModel\n"
                        "\n"
                        "\n"
                        "class Item(BaseModel):\n"
                        '    name: str\n'
                        '    description: Optional[str] = None\n'
                        "\n"
                        "\n"
                        "class ItemCreate(Item):\n"
                        "    pass\n"
                    ),
                    "$NAME/routers/__init__.py": "",
                    "$NAME/routers/items.py": (
                        "from fastapi import APIRouter\n"
                        "\n"
                        "from $NAME.models import Item, ItemCreate\n"
                        "\n"
                        "router = APIRouter()\n"
                        "\n"
                        "\n"
                        "@router.get(\"/\")\n"
                        "async def list_items():\n"
                        '    return [{"name": "sample", "description": "A sample item"}]\n'
                        "\n"
                        "\n"
                        "@router.post(\"/\")\n"
                        "async def create_item(item: ItemCreate):\n"
                        '    return {"id": 1, **item.model_dump()}\n'
                    ),
                    "tests/__init__.py": "",
                    "tests/test_items.py": (
                        "from fastapi.testclient import TestClient\n"
                        "\n"
                        "from $NAME.main import app\n"
                        "\n"
                        "client = TestClient(app)\n"
                        "\n"
                        "\n"
                        "def test_list_items():\n"
                        "    response = client.get(\"/items/\")\n"
                        "    assert response.status_code == 200\n"
                        "\n"
                        "\n"
                        "def test_create_item():\n"
                        "    response = client.post(\"/items/\", json={\"name\": \"foo\"})\n"
                        "    assert response.status_code == 200\n"
                    ),
                    "pyproject.toml": (
                        "[project]\n"
                        'name = "$NAME"\n'
                        'version = "0.1.0"\n'
                        'description = "$DESCRIPTION"\n'
                        "dependencies = [\n"
                        '    "fastapi>=0.100",\n'
                        '    "uvicorn[standard]>=0.23",\n'
                        '    "pydantic>=2.0",\n'
                        "]\n"
                        "\n"
                        "[project.optional-dependencies]\n"
                        'test = ["pytest", "httpx"]\n'
                    ),
                    "README.md": (
                        "# $NAME\n"
                        "\n"
                        "$DESCRIPTION\n"
                        "\n"
                        "## Run\n"
                        "\n"
                        "```bash\n"
                        "uvicorn $NAME.main:app --reload\n"
                        "```\n"
                    ),
                },
            },
            "react-app": {
                "description": "React application scaffold",
                "files": {
                    "package.json": json.dumps(
                        {
                            "name": "$NAME",
                            "version": "0.1.0",
                            "private": True,
                            "dependencies": {
                                "react": "^18.2.0",
                                "react-dom": "^18.2.0",
                                "react-scripts": "5.0.1",
                            },
                            "scripts": {
                                "start": "react-scripts start",
                                "build": "react-scripts build",
                                "test": "react-scripts test",
                            },
                            "browserslist": {
                                "production": [">0.2%", "not dead", "not op_mini all"],
                                "development": [
                                    "last 1 chrome version",
                                    "last 1 firefox version",
                                    "last 1 safari version",
                                ],
                            },
                        },
                        indent=2,
                    )
                    + "\n",
                    "public/index.html": (
                        "<!DOCTYPE html>\n"
                        '<html lang="en">\n'
                        "  <head>\n"
                        '    <meta charset="utf-8" />\n'
                        '    <meta name="viewport" content="width=device-width, initial-scale=1" />\n'
                        '    <title>$NAME</title>\n'
                        "  </head>\n"
                        "  <body>\n"
                        '    <div id="root"></div>\n'
                        "  </body>\n"
                        "</html>\n"
                    ),
                    "public/manifest.json": json.dumps(
                        {"short_name": "$NAME", "name": "$NAME", "start_url": "."},
                        indent=2,
                    )
                    + "\n",
                    "src/index.js": (
                        "import React from 'react';\n"
                        "import ReactDOM from 'react-dom/client';\n"
                        "import App from './App';\n"
                        "\n"
                        "const root = ReactDOM.createRoot(document.getElementById('root'));\n"
                        "root.render(<App />);\n"
                    ),
                    "src/App.js": (
                        "import React from 'react';\n"
                        "\n"
                        "function App() {\n"
                        "  return (\n"
                        "    <div>\n"
                        "      <h1>Welcome to $NAME</h1>\n"
                        "      <p>$DESCRIPTION</p>\n"
                        "    </div>\n"
                        "  );\n"
                        "}\n"
                        "\n"
                        "export default App;\n"
                    ),
                    "src/App.css": (
                        "body {\n"
                        "  font-family: sans-serif;\n"
                        "  margin: 0;\n"
                        "  padding: 20px;\n"
                        "}\n"
                        "\n"
                        "h1 {\n"
                        "  color: #333;\n"
                        "}\n"
                    ),
                    "README.md": (
                        "# $NAME\n"
                        "\n"
                        "$DESCRIPTION\n"
                        "\n"
                        "## Getting Started\n"
                        "\n"
                        "```bash\n"
                        "npm install\n"
                        "npm start\n"
                        "```\n"
                    ),
                },
            },
            "rust-cli": {
                "description": "Rust CLI with Clap argument parsing",
                "files": {
                    "Cargo.toml": (
                        "[package]\n"
                        'name = "$NAME"\n'
                        'version = "0.1.0"\n'
                        'edition = "2021"\n'
                        "\n"
                        "[dependencies]\n"
                        'clap = { version = "4", features = ["derive"] }\n'
                    ),
                    "src/main.rs": (
                        "use clap::Parser;\n"
                        "\n"
                        "/// $DESCRIPTION\n"
                        "#[derive(Parser)]\n"
                        "#[command(version, about)]\n"
                        "struct Args {\n"
                        "    /// Name to greet\n"
                        "    #[arg(short, long)]\n"
                        "    name: Option<String>,\n"
                        "}\n"
                        "\n"
                        "fn main() {\n"
                        "    let args = Args::parse();\n"
                        '    let name = args.name.as_deref().unwrap_or("world");\n'
                        '    println!("Hello, {}!", name);\n'
                        "}\n"
                    ),
                    "README.md": (
                        "# $NAME\n"
                        "\n"
                        "$DESCRIPTION\n"
                        "\n"
                        "## Build\n"
                        "\n"
                        "```bash\n"
                        "cargo build --release\n"
                        "```\n"
                        "\n"
                        "## Run\n"
                        "\n"
                        "```bash\n"
                        "cargo run -- --help\n"
                        "```\n"
                    ),
                },
            },
            "go-api": {
                "description": "Go HTTP API with standard library",
                "files": {
                    "go.mod": (
                        "module $NAME\n"
                        "\n"
                        'go 1.21\n'
                    ),
                    "main.go": (
                        "package main\n"
                        "\n"
                        'import "fmt"\n'
                        'import "log"\n'
                        'import "net/http"\n'
                        "\n"
                        "func main() {\n"
                        '    http.HandleFunc("/", homeHandler)\n'
                        '    http.HandleFunc("/items", itemsHandler)\n'
                        '    fmt.Println("Server starting on :8080")\n'
                        '    log.Fatal(http.ListenAndServe(":8080", nil))\n'
                        "}\n"
                        "\n"
                        "func homeHandler(w http.ResponseWriter, r *http.Request) {\n"
                        '    w.Write([]byte("Welcome to $NAME"))\n'
                        "}\n"
                        "\n"
                        "func itemsHandler(w http.ResponseWriter, r *http.Request) {\n"
                        '    w.Write([]byte("Items endpoint"))\n'
                        "}\n"
                    ),
                    "handlers/items.go": (
                        "package handlers\n"
                        "\n"
                        'import "net/http"\n'
                        "\n"
                        "func GetItems(w http.ResponseWriter, r *http.Request) {\n"
                        '    w.Write([]byte("List of items"))\n'
                        "}\n"
                        "\n"
                        "func CreateItem(w http.ResponseWriter, r *http.Request) {\n"
                        '    w.Write([]byte("Item created"))\n'
                        "}\n"
                    ),
                    "README.md": (
                        "# $NAME\n"
                        "\n"
                        "$DESCRIPTION\n"
                        "\n"
                        "## Run\n"
                        "\n"
                        "```bash\n"
                        "go run main.go\n"
                        "```\n"
                    ),
                },
            },
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_templates(self) -> List[str]:
        """Return available template names.

        Returns:
            Sorted list of built-in and custom template names.
        """
        builtin_names = sorted(self._builtins.keys())
        custom_names: List[str] = []
        if self._custom_dir.exists():
            for p in self._custom_dir.iterdir():
                if p.suffix == ".json" and p.stem not in builtin_names:
                    custom_names.append(p.stem)
        return sorted(builtin_names + custom_names)

    def describe_template(self, template_name: str) -> str:
        """Return a short description of a template.

        Args:
            template_name: Template identifier.

        Returns:
            Description string, or empty if unknown.
        """
        if template_name in self._builtins:
            return self._builtins[template_name].get("description", "")
        custom = self._load_custom_template(template_name)
        if custom:
            return custom.get("description", "")
        return ""

    def create_project(
        self,
        template_name: str,
        target_path: str | Path,
        variables: Dict[str, str] | None = None,
    ) -> List[Path]:
        """Create a project from a template.

        Args:
            template_name: Name of the built-in or custom template.
            target_path: Directory where the project will be created.
            variables: Key/value substitutions for template variables
                (``$NAME``, ``$DESCRIPTION``, ``$AUTHOR`` …).

        Returns:
            List of paths that were created.

        Raises:
            ValueError: If the template does not exist.
        """
        tmpl = self._get_template(template_name)
        if tmpl is None:
            raise ValueError(f"Template '{template_name}' not found")

        target = Path(target_path)
        target.mkdir(parents=True, exist_ok=True)

        defaults = {
            "NAME": target.name,
            "DESCRIPTION": f"Generated {template_name} project",
            "AUTHOR": "",
            "YEAR": "2024",
        }
        defaults.update(variables or {})

        created: List[Path] = []
        for rel_path, content in tmpl.get("files", {}).items():
            resolved = self._substitute_variables(rel_path, defaults)
            file_path = target / resolved
            file_path.parent.mkdir(parents=True, exist_ok=True)
            clean_content = self._substitute_variables(content, defaults)
            file_path.write_text(clean_content, encoding="utf-8")
            created.append(file_path)

        return created

    def save_custom_template(
        self, name: str, description: str, files: Dict[str, str]
    ) -> Path:
        """Save a user-defined template to disk.

        Args:
            name: Template identifier.
            description: Human-readable description.
            files: Mapping of relative file paths to template contents.

        Returns:
            Path to the saved JSON file.
        """
        data = {"description": description, "files": files}
        file_path = self._custom_dir / f"{name}.json"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        return file_path

    def load_custom_template(self, name: str) -> Dict[str, Any] | None:
        """Load a previously saved custom template.

        Args:
            name: Template identifier.

        Returns:
            Template dictionary, or ``None`` if not found.
        """
        return self._load_custom_template(name)

    async def generate_custom_template(
        self, description: str, language: str
    ) -> Dict[str, Any]:
        """Generate a custom project template via AI.

        Args:
            description: What the project should do.
            language: Primary programming language.

        Returns:
            Template dictionary with ``description`` and ``files`` keys.

        Raises:
            RuntimeError: If no AI client is configured.
        """
        if self._ai_client is None:
            raise RuntimeError("No AI client configured for template generation")
        prompt = (
            f"Generate a JSON project template for a {language} project that "
            f"does the following: {description}. "
            "Return ONLY a JSON object with two keys: 'description' (string) "
            "and 'files' (object mapping relative file paths to file contents). "
            "Use $NAME and $DESCRIPTION as variable placeholders inside file contents."
        )
        response = await self._ai_client.complete(prompt, temperature=0.3, max_tokens=2048)
        try:
            parsed: Dict[str, Any] = json.loads(response)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"AI returned invalid JSON: {exc}") from exc
        return parsed

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_template(self, name: str) -> Dict[str, Any] | None:
        """Return a built-in or custom template dictionary."""
        if name in self._builtins:
            return self._builtins[name]
        return self._load_custom_template(name)

    def _load_custom_template(self, name: str) -> Dict[str, Any] | None:
        """Load a custom template from disk."""
        file_path = self._custom_dir / f"{name}.json"
        if not file_path.exists():
            return None
        with open(file_path, "r", encoding="utf-8") as fh:
            data: Dict[str, Any] = json.load(fh)
        return data

    @staticmethod
    def _substitute_variables(text: str, variables: Dict[str, str]) -> str:
        """Replace ``$KEY`` placeholders in *text* with *variables* values."""
        result = text
        for key, value in variables.items():
            result = result.replace(f"${key}", value)
        return result
