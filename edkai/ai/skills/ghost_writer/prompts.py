"""Prompt builder for the ghost_writer skill."""
from edkai.ai.skills.manager import SkillResult


def build_prompt(user_input: str, context: dict) -> SkillResult:
    code = context.get("code", "")
    language = context.get("language", "")
    cursor_position = context.get("cursor_position", "end")  # end, middle, after_signature
    style_notes = context.get("style_notes", "")
    num_suggestions = context.get("num_suggestions", 1)

    cursor_guidance = {
        "end": "Continue from the end of the provided code. Complete the current block or add the next logical section.",
        "middle": "The cursor is positioned in the middle of the code. Complete the current statement, function, or block that is partially written.",
        "after_signature": "A function/method signature has been provided. Write the complete implementation body based on the signature name, parameters, and return type.",
    }

    prompt = f"""Complete or continue the following {language} code.

{cursor_guidance.get(cursor_position, cursor_guidance["end"])}

{f"Style notes: {style_notes}" if style_notes else ""}

Partial code:
```{language}
{code}
```

Original request: {user_input}

{f"Provide {num_suggestions} alternative implementations." if num_suggestions > 1 else ""}

Guidelines for completion:
1. **Match existing style** - Follow the naming conventions, patterns, and structure already used
2. **Type consistency** - Respect type hints and return annotations
3. **Error handling** - Add appropriate error handling for edge cases
4. **Docstrings** - Include docstrings for new functions if the existing code has them
5. **Imports** - List any new imports needed at the top
6. **Completeness** - Ensure the code is runnable and logically complete

{f"For multiple suggestions, label them Alternative 1, Alternative 2, etc. with brief explanations of the trade-offs." if num_suggestions > 1 else ""}

Output only the completed code (and any new imports needed), no extra explanation unless asked."""

    return SkillResult(prompt=prompt, context=context)
