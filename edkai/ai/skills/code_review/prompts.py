"""Prompt builder for the code_review skill."""
from edkai.ai.skills.manager import SkillResult


def build_prompt(user_input: str, context: dict) -> SkillResult:
    code = context.get("code", "")
    language = context.get("language", "")
    focus = context.get("focus", "general")  # general, security, performance, style

    focus_instructions = {
        "security": "Focus primarily on security vulnerabilities: injection risks, authentication flaws, insecure dependencies, sensitive data exposure, and OWASP Top 10 issues.",
        "performance": "Focus primarily on performance issues: algorithmic complexity, unnecessary allocations, I/O bottlenecks, caching opportunities, and resource leaks.",
        "style": "Focus primarily on style and maintainability: naming conventions, code organization, documentation gaps, and adherence to language-specific style guides.",
    }

    prompt = f"""Review the following {language} code for bugs, security issues, performance problems, and style violations.

{focus_instructions.get(focus, "Cover all categories: bugs, security, performance, and style.")}

```{language}
{code}
```

Provide specific, actionable feedback with line references. Rate severity: [CRITICAL], [WARNING], [INFO].

Format each finding as:
- **[SEVERITY] Category - Brief Title**
  - Location: Line X (or function/module)
  - Issue: Detailed description
  - Fix: Specific code suggestion or approach

End with a summary count and any high-priority recommendations."""

    return SkillResult(prompt=prompt, context=context)
