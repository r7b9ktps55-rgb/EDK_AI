"""Prompt builder for the explain skill."""
from edkai.ai.skills.manager import SkillResult


def build_prompt(user_input: str, context: dict) -> SkillResult:
    code = context.get("code", "")
    language = context.get("language", "")
    topic = context.get("topic", "")
    level = context.get("level", "intermediate")  # beginner, intermediate, advanced
    style = context.get("style", "concise")  # concise, detailed, tutorial

    level_guidance = {
        "beginner": "Assume the reader is new to programming or this language. Define all technical terms. Use analogies to everyday concepts. Avoid jargon without explanation.",
        "intermediate": "Assume basic programming knowledge. Explain language-specific or advanced concepts. Briefly define less common terms.",
        "advanced": "Assume deep familiarity with the language and patterns. Focus on subtle behavior, edge cases, implementation details, and optimization considerations.",
    }

    prompt = f"""Explain the following in clear, accessible language.

{level_guidance.get(level, level_guidance["intermediate"])}

{f"Explanation style: {style}" if style else ""}

{f"Code to explain:
```{language}
{code}
```" if code else ""}

{f"Topic to explain: {topic}" if topic else ""}

Original request: {user_input}

Structure your explanation as follows:
1. **Big Picture** - What does this code/topic do at a high level?
2. **Step-by-Step Breakdown** - Walk through the logic or concept piece by piece
3. **Key Concepts** - Important patterns, functions, or principles involved
{f"4. **Analogy** - A real-world analogy to make it concrete" if level == "beginner" else ""}
4. **Practical Notes** - Common pitfalls, best practices, or related concepts to explore

Use bullet points and short paragraphs for readability. Include code snippets where they help illustrate the explanation."""

    return SkillResult(prompt=prompt, context=context)
