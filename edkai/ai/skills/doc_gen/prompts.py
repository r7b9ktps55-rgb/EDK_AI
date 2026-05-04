"""Prompt builder for the doc_gen skill."""
from edkai.ai.skills.manager import SkillResult


def build_prompt(user_input: str, context: dict) -> SkillResult:
    code = context.get("code", "")
    language = context.get("language", "")
    doc_type = context.get("doc_type", "docstrings")  # docstrings, readme, api_docs
    style = context.get("style", "google")  # google, numpy, sphinx/epytext

    style_examples = {
        "google": """Google style:
        \"\"\"Short one-line summary.

        More detailed description if needed. Can span multiple lines.

        Args:
            param1: Description of param1.
            param2: Description of param2.

        Returns:
            Description of return value.

        Raises:
            ValueError: When something is invalid.
        \"\"\" """,
        "numpy": """NumPy style:
        \"\"\"Short one-line summary.

        Extended description.

        Parameters
        ----------
        param1 : type
            Description.
        param2 : type
            Description.

        Returns
        -------
        type
            Description.

        Raises
        ------
        ValueError
            When something is invalid.
        \"\"\" """,
        "sphinx": """Sphinx/epydoc style:
        \"\"\"Short one-line summary.

        Extended description.

        @param param1: Description.
        @type param1: type
        @return: Description.
        @rtype: type
        @raise ValueError: When invalid.
        \"\"\" """,
    }

    prompt = f"""Generate {doc_type} for the following {language} code.

{f"Use {style} docstring format." if doc_type == "docstrings" else ""}

{style_examples.get(style, "")}

Code to document:
```{language}
{code}
```

{f"Generate a comprehensive README.md including:" if doc_type == "readme" else ""}
{f"1. Project title and one-line description" if doc_type == "readme" else ""}
{f"2. Installation instructions" if doc_type == "readme" else ""}
{f"3. Usage examples with code snippets" if doc_type == "readme" else ""}
{f"4. API reference for key functions/classes" if doc_type == "readme" else ""}
{f"5. Configuration options if applicable" if doc_type == "readme" else ""}
{f"Generate API documentation including:" if doc_type == "api_docs" else ""}
{f"1. Module overview" if doc_type == "api_docs" else ""}
{f"2. Class and function signatures with parameters" if doc_type == "api_docs" else ""}
{f"3. Type information and return values" if doc_type == "api_docs" else ""}
{f"4. Usage examples" if doc_type == "api_docs" else ""}

For docstrings, document every public function, class, and method with:
- One-line summary
- Args/Parameters with types
- Return value with type
- Exceptions raised
- Usage examples for complex functions

Output the fully documented code ready to use."""

    return SkillResult(prompt=prompt, context=context)
