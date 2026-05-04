"""Diff engine for generating and formatting code diffs."""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DiffHunk:
    """A single hunk in a unified diff."""
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str]  # Lines with +, -, or prefix
    header: str = ""


class DiffEngine:
    """Generate and parse unified diffs."""
    
    @staticmethod
    def unified_diff(
        original: str,
        modified: str,
        file_name: str = "file",
    ) -> str:
        """Generate unified diff between two strings."""
        original_lines = original.splitlines(keepends=True)
        modified_lines = modified.splitlines(keepends=True)
        
        # Ensure lines end with newline for proper diff output
        if original_lines and not original_lines[-1].endswith("\n"):
            original_lines[-1] += "\n"
        if modified_lines and not modified_lines[-1].endswith("\n"):
            modified_lines[-1] += "\n"
        
        diff = difflib.unified_diff(
            original_lines,
            modified_lines,
            fromfile=f"a/{file_name}",
            tofile=f"b/{file_name}",
        )
        
        return "".join(diff)
    
    @staticmethod
    def parse_diff(diff_text: str) -> list[DiffHunk]:
        """Parse unified diff text into hunks."""
        hunks: list[DiffHunk] = []
        lines = diff_text.split("\n")
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Look for hunk header: @@ -start,count +start,count @@
            if line.startswith("@@"):
                match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)", line)
                if match:
                    old_start = int(match.group(1))
                    old_count = int(match.group(2) if match.group(2) is not None else "1")
                    new_start = int(match.group(3))
                    new_count = int(match.group(4) if match.group(4) is not None else "1")
                    header = match.group(5).strip()

                    hunk_lines: list[str] = []
                    i += 1
                    while i < len(lines) and not lines[i].startswith("@@"):
                        hunk_lines.append(lines[i])
                        i += 1
                    # Strip trailing empty line from split
                    if hunk_lines and hunk_lines[-1] == "":
                        hunk_lines.pop()

                    hunks.append(DiffHunk(
                        old_start=old_start,
                        old_count=old_count,
                        new_start=new_start,
                        new_count=new_count,
                        lines=hunk_lines,
                        header=header,
                    ))
                    continue
            
            i += 1
        
        return hunks
    
    @staticmethod
    def colorize_diff(diff_text: str) -> str:
        """Add ANSI color codes to diff text for terminal display.
        
        Returns text with:
        - Red for removed lines (-)
        - Green for added lines (+)
        - Gray for context
        - Cyan for headers
        """
        lines = diff_text.split("\n")
        colored: list[str] = []
        
        for line in lines:
            if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
                colored.append(f"\033[36m{line}\033[0m")  # Cyan header
            elif line.startswith("+"):
                colored.append(f"\033[32m{line}\033[0m")  # Green added
            elif line.startswith("-"):
                colored.append(f"\033[31m{line}\033[0m")  # Red removed
            else:
                colored.append(f"\033[90m{line}\033[0m")  # Gray context
        
        return "\n".join(colored)
    
    @staticmethod
    def stats(diff_text: str) -> dict[str, int]:
        """Get diff statistics: files changed, insertions, deletions."""
        lines = diff_text.split("\n")
        insertions = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
        deletions = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
        files = sum(1 for l in lines if l.startswith("--- "))

        return {
            "files_changed": max(files, 0),
            "insertions": max(insertions, 0),
            "deletions": max(deletions, 0),
        }
