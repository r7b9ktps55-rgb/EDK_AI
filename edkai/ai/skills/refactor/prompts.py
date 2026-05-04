"""Prompt builder for the refactor skill."""
from edkai.ai.skills.manager import SkillResult


def build_prompt(user_input: str, context: dict) -> SkillResult:
    code = context.get("code", "")
    language = context.get("language", "")
    goals = context.get("goals", "general improvement")  # e.g., "reduce complexity", "extract classes"
    style_guide = context.get("style_guide", "")  # e.g., "PEP 8", "Google Style"

    prompt = f"""Refactor the following {language} code to improve its quality while preserving all existing behavior.

Refactoring goals: {goals}
{f"Style guide to follow: {style_guide}" if style_guide else ""}

```{language}
{code}
```

Provide the refactored code and explain each significant change:

1. **What was changed** - The specific refactoring applied
2. **Why it helps** - The benefit of the change (readability, performance, maintainability)
3. **Before vs After** - Brief comparison if helpful

Principles to apply:
- Reduce cyclomatic complexity and function length
- Apply the DRY (Don't Repeat Yourself) principle
- Use meaningful names and add type hints where appropriate
- Extract functions/classes where they improve clarity
- Remove dead code and unnecessary comments
- Prefer early returns over nested conditionals

Output the complete refactored code first, then the explanation of changes."""

    return SkillResult(prompt=prompt, context=context)
