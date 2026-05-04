"""Symbol extraction engine for Terminal Studio.

Parses source files to identify classes, functions, methods, variables,
and other named symbols.  Python is handled via the :mod:`ast` module;
all other languages use carefully-crafted regular expressions.
"""

from __future__ import annotations

import ast
import asyncio
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Symbol:
    """A single extracted symbol."""

    name: str
    """Identifier name."""

    type: str
    """One of ``class``, ``function``, ``method``, ``variable``,
    ``enum``, ``trait``, ``interface``, ``struct``, ``macro``, etc."""

    line: int
    """1-based line number where the symbol is defined."""

    col: int
    """0-based column offset where the symbol is defined."""

    file: str
    """Absolute path to the source file."""

    signature: str = ""
    """A short signature string (e.g. ``def foo(a: int) -> str``)."""

    docstring: str = ""
    """First docstring / comment attached to the symbol, if any."""


# ---------------------------------------------------------------------------
# Language dispatch
# ---------------------------------------------------------------------------

_LANGUAGE_MAP: Dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mjs": "javascript",
    ".rs": "rust",
    ".go": "go",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
}


def _detect_language_from_path(path: str) -> str:
    """Infer a language identifier from a file path."""
    ext = Path(path).suffix.lower()
    return _LANGUAGE_MAP.get(ext, "")


# ---------------------------------------------------------------------------
# Python extraction (AST)
# ---------------------------------------------------------------------------


def _extract_python(file_path: str) -> List[Symbol]:
    """Extract symbols from a Python source file using :mod:`ast`."""
    try:
        source = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    lines = source.splitlines()
    symbols: List[Symbol] = []

    def _doc(node: ast.AST) -> str:
        """Return the docstring of *node* if present."""
        if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef, ast.Module)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                return body[0].value.value.strip().split("\n")[0]
        return ""

    def _signature(func: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        """Build a short signature string from a function node."""
        args = func.args
        parts: List[str] = []
        # positional / kwonly / args
        all_args = args.posonlyargs + args.args + args.kwonlyargs
        defaults_offset = len(all_args) - len(args.defaults)
        for i, arg in enumerate(all_args):
            arg_str = arg.arg
            if arg.annotation:
                arg_str += f": {ast.unparse(arg.annotation)}"
            if i >= defaults_offset and args.defaults:
                default = args.defaults[i - defaults_offset]
                arg_str += f"={ast.unparse(default)}"
            parts.append(arg_str)
        if args.vararg and args.vararg.arg:
            parts.append(f"*{args.vararg.arg}")
        if args.kwarg and args.kwarg.arg:
            parts.append(f"**{args.kwarg.arg}")
        sig = f"def {func.name}({', '.join(parts)})"
        if func.returns:
            sig += f" -> {ast.unparse(func.returns)}"
        return sig

    def _visit(node: ast.AST, parent_type: str = "") -> None:
        if isinstance(node, ast.ClassDef):
            sym = Symbol(
                name=node.name,
                type="class",
                line=node.lineno,
                col=node.col_offset,
                file=file_path,
                signature=f"class {node.name}",
                docstring=_doc(node),
            )
            symbols.append(sym)
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    child_type = "method" if child.args.args and child.args.args[0].arg in ("self", "cls") else "function"
                    child_sym = Symbol(
                        name=child.name,
                        type=child_type,
                        line=child.lineno,
                        col=child.col_offset,
                        file=file_path,
                        signature=_signature(child),
                        docstring=_doc(child),
                    )
                    symbols.append(child_sym)
                    # Do NOT recurse into methods to avoid duplicate symbols.
                    continue
                _visit(child, "class")

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sym = Symbol(
                name=node.name,
                type="function",
                line=node.lineno,
                col=node.col_offset,
                file=file_path,
                signature=_signature(node),
                docstring=_doc(node),
            )
            symbols.append(sym)

        elif isinstance(node, ast.Assign) and parent_type != "class":
            for target in node.targets:
                if isinstance(target, ast.Name):
                    symbols.append(
                        Symbol(
                            name=target.id,
                            type="variable",
                            line=node.lineno,
                            col=node.col_offset,
                            file=file_path,
                            signature=f"{target.id} = ...",
                            docstring="",
                        )
                    )

        elif isinstance(node, ast.AnnAssign) and parent_type != "class":
            if isinstance(node.target, ast.Name):
                symbols.append(
                    Symbol(
                        name=node.target.id,
                        type="variable",
                        line=node.lineno,
                        col=node.col_offset,
                        file=file_path,
                        signature=f"{node.target.id}: {ast.unparse(node.annotation)} = ..." if node.annotation else f"{node.target.id} = ...",
                        docstring="",
                    )
                )

        elif isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom):
            # Skip imports at module level
            pass
        else:
            for child in ast.iter_child_nodes(node):
                _visit(child, parent_type)

    for child in ast.iter_child_nodes(tree):
        _visit(child)

    return symbols


# ---------------------------------------------------------------------------
# Regex-based extractors
# ---------------------------------------------------------------------------

# Shared helpers


def _extract_with_regex(
    file_path: str,
    patterns: Dict[str, str],
) -> List[Symbol]:
    """Generic regex-based symbol extractor.

    *patterns* maps a symbol type to a regex string.  Each regex must
    contain a named group ``name`` and may contain ``signature``.
    """
    try:
        text = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return []

    symbols: List[Symbol] = []
    compiled: Dict[str, re.Pattern[str]] = {
        kind: re.compile(pat, re.MULTILINE) for kind, pat in patterns.items()
    }

    for kind, pattern in compiled.items():
        for m in pattern.finditer(text):
            name = m.group("name")
            line = text[: m.start()].count("\n") + 1
            col = m.start() - text.rfind("\n", 0, m.start())
            if col < 0:
                col = m.start()
            sig = m.group("signature") if "signature" in m.groupdict() else ""
            symbols.append(
                Symbol(
                    name=name,
                    type=kind,
                    line=line,
                    col=col,
                    file=file_path,
                    signature=sig.strip() if sig else f"{kind} {name}",
                    docstring="",
                )
            )

    # Deduplicate and sort by position
    seen: set[tuple[int, int]] = set()
    uniq: List[Symbol] = []
    for s in sorted(symbols, key=lambda x: (x.line, x.col)):
        key = (s.line, s.col)
        if key not in seen:
            seen.add(key)
            uniq.append(s)
    return uniq


def _extract_javascript_typescript(file_path: str) -> List[Symbol]:
    """Extract symbols from JavaScript / TypeScript files."""
    patterns = {
        "class": r"(?:export\s+)?class\s+(?P<name>[A-Za-z_$][\w$]*)\s*(?P<signature>[^{]*)",
        "function": r"(?:export\s+)?(?:async\s+)?function\s+(?P<name>[A-Za-z_$][\w$]*)\s*(?P<signature>\([^)]*\))",
        "method": r"(?P<name>[A-Za-z_$][\w$]*)\s*(?P<signature>\([^)]*\))\s*\{[^}]*\}",
        "interface": r"(?:export\s+)?interface\s+(?P<name>[A-Za-z_$][\w$]*)\s*(?P<signature>[^{]*)",
        "variable": r"(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*=?",
    }
    return _extract_with_regex(file_path, patterns)


def _extract_rust(file_path: str) -> List[Symbol]:
    """Extract symbols from Rust source files."""
    patterns = {
        "struct": r"(?:pub\s+)?struct\s+(?P<name>[A-Za-z_][\w]*)\s*(?P<signature>[^{]*)",
        "enum": r"(?:pub\s+)?enum\s+(?P<name>[A-Za-z_][\w]*)\s*(?P<signature>[^{]*)",
        "trait": r"(?:pub\s+)?trait\s+(?P<name>[A-Za-z_][\w]*)\s*(?P<signature>[^{]*)",
        "function": r"(?:pub\s+)?(?:async\s+)?fn\s+(?P<name>[A-Za-z_][\w]*)\s*(?P<signature>\([^)]*\))(?:\s*->\s*[^{]+)?",
        "macro": r"macro_rules!\s+(?P<name>[A-Za-z_][\w]*)\s*(?P<signature>\{[^}]*\})?",
        "impl": r"impl(?:<[^>]+>)?\s+(?P<name>[A-Za-z_][\w:]*)\s*(?:for\s+[A-Za-z_][\w:]*)?\s*(?P<signature>[^{]*)",
        "type": r"(?:pub\s+)?type\s+(?P<name>[A-Za-z_][\w]*)\s*=",
    }
    return _extract_with_regex(file_path, patterns)


def _extract_go(file_path: str) -> List[Symbol]:
    """Extract symbols from Go source files."""
    patterns = {
        "struct": r"type\s+(?P<name>[A-Za-z_][\w]*)\s+struct\s*(?P<signature>[^{]*)",
        "interface": r"type\s+(?P<name>[A-Za-z_][\w]*)\s+interface\s*(?P<signature>[^{]*)",
        "function": r"func\s+(?:\([^)]+\)\s+)?(?P<name>[A-Za-z_][\w]*)\s*(?P<signature>\([^)]*\))",
        "variable": r"(?:var|const)\s+(?P<name>[A-Za-z_][\w]*)\s*=?",
        "type": r"type\s+(?P<name>[A-Za-z_][\w]*)\s+(?!struct|interface)(?P<signature>[^{\n]+)",
    }
    return _extract_with_regex(file_path, patterns)


def _extract_c_cpp(file_path: str) -> List[Symbol]:
    """Extract symbols from C / C++ source files."""
    patterns = {
        "function": r"(?:[A-Za-z_][\w*\s&]*\s+)?(?P<name>[A-Za-z_][\w]*)\s*(?P<signature>\([^)]*\))\s*\{[^}]*\}",
        "struct": r"(?:typedef\s+)?struct\s+(?P<name>[A-Za-z_][\w]*)\s*(?P<signature>[^{]*)",
        "enum": r"(?:typedef\s+)?enum\s+(?P<name>[A-Za-z_][\w]*)\s*(?P<signature>[^{]*)",
        "typedef": r"typedef\s+(?:struct\s+)?(?:enum\s+)?[A-Za-z_][\w*\s&]*\s+(?P<name>[A-Za-z_][\w]*)\s*;",
        "variable": r"(?:const\s+)?(?:static\s+)?(?:extern\s+)?[A-Za-z_][\w*\s&]*\s+(?P<name>[A-Za-z_][\w]*)\s*=?[^()]*;",
    }
    return _extract_with_regex(file_path, patterns)


# ---------------------------------------------------------------------------
# SymbolExtractor
# ---------------------------------------------------------------------------


class SymbolExtractor:
    """Extracts classes, functions, variables and other symbols from source code.

    Supported languages:
    * **Python** — parsed with :mod:`ast` (most accurate).
    * **JavaScript / TypeScript** — regex-based.
    * **Rust** — regex-based.
    * **Go** — regex-based.
    * **C / C++** — regex-based.
    """

    def extract(self, file_path: str, language: str) -> List[Symbol]:
        """Extract symbols from a single source file.

        Args:
            file_path: Absolute path to the source file.
            language: Language identifier (``python``, ``javascript``, etc.).

        Returns:
            A list of :class:`Symbol` sorted by position in the file.
        """
        lang = language.lower()
        if lang == "python":
            return _extract_python(file_path)
        if lang in ("javascript", "typescript"):
            return _extract_javascript_typescript(file_path)
        if lang == "rust":
            return _extract_rust(file_path)
        if lang == "go":
            return _extract_go(file_path)
        if lang in ("c", "cpp", "c++"):
            return _extract_c_cpp(file_path)
        return []

    def extract_project(self, root: str) -> Dict[str, List[Symbol]]:
        """Extract symbols from every recognised source file under *root*.

        Args:
            root: Directory to scan recursively.

        Returns:
            A mapping ``file_path -> [Symbol, ...]``.
        """
        result: Dict[str, List[Symbol]] = {}
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                path = str(Path(dirpath) / name)
                lang = _detect_language_from_path(path)
                if not lang:
                    continue
                symbols = self.extract(path, lang)
                if symbols:
                    result[path] = symbols
        return result

    def search_symbols(
        self,
        query: str,
        root: str,
    ) -> List[Symbol]:
        """Fuzzy-search all symbols in *root* by name.

        Args:
            query: User-typed search string.
            root: Project root directory.

        Returns:
            Symbols whose name fuzzily matches *query*, sorted by score.
        """
        from edkai.core.fuzzy_search import _fuzzy_score

        all_symbols: List[Symbol] = []
        project = self.extract_project(root)
        for syms in project.values():
            all_symbols.extend(syms)

        q = query.lower()
        scored: List[tuple[int, Symbol]] = []
        for sym in all_symbols:
            score, _ = _fuzzy_score(q, sym.name)
            if score > 0:
                scored.append((score, sym))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored]
