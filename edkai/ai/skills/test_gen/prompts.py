"""Prompt builder for the test_gen skill."""
from edkai.ai.skills.manager import SkillResult


def build_prompt(user_input: str, context: dict) -> SkillResult:
    code = context.get("code", "")
    language = context.get("language", "")
    framework = context.get("framework", "pytest")  # pytest, unittest, jest
    coverage_target = context.get("coverage_target", "comprehensive")

    framework_templates = {
        "pytest": "Use pytest with fixtures, parametrize for multiple test cases, and pytest.raises for exception testing.",
        "unittest": "Use Python's built-in unittest framework with TestCase classes, setUp/tearDown, and assert methods.",
        "jest": "Use Jest with describe/it blocks, expect assertions, and mocking via jest.fn().",
    }

    prompt = f"""Generate {coverage_target} unit tests for the following {language} code using {framework}.

{framework_templates.get(framework, "Use standard testing patterns for the language.")}

Code under test:
```{language}
{code}
```

Requirements for the tests:
1. **Happy path tests** - Normal expected behavior with valid inputs
2. **Edge case tests** - Boundary values, empty inputs, maximum values
3. **Error handling tests** - Invalid inputs, exceptions, failure modes
4. **Parametrized tests** - Multiple similar cases using parametrization
5. **Mocking** - Mock external dependencies (files, APIs, databases) where appropriate

Additional guidelines:
- Use descriptive test names that explain what is being tested
- Follow Arrange-Act-Assert pattern
- Include docstrings explaining test intent
- Target high branch coverage (aim for 90%+)
- Group related tests in classes or describe blocks

Output only the test code with necessary imports, ready to run."""

    return SkillResult(prompt=prompt, context=context)
