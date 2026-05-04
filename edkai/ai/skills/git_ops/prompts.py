"""Prompt builder for the git_ops skill."""
from edkai.ai.skills.manager import SkillResult


def build_prompt(user_input: str, context: dict) -> SkillResult:
    diff = context.get("diff", "")
    status = context.get("status", "")
    operation = context.get("operation", "commit")  # commit, branch, merge, explain, history
    style = context.get("style", "conventional")  # conventional, verbose, atomic
    language = context.get("language", "")

    style_guide = {
        "conventional": """Use Conventional Commits format:
        <type>(<scope>): <description>
        
        [optional body]
        
        [optional footer]
        
        Types: feat, fix, docs, style, refactor, test, chore, perf, ci, build""",
        "verbose": "Write detailed commit messages explaining the what and why of changes.",
        "atomic": "Suggest breaking changes into the smallest logical, independent commits.",
    }

    prompt = f"""Assist with the following Git operation: {operation}

{f"Commit message style: {style}" if operation == "commit" else ""}
{style_guide.get(style, "") if operation == "commit" else ""}

{f"Git diff:
```diff
{diff}
```" if diff else ""}

{f"Git status:
```
{status}
```" if status else ""}

{f"Programming language: {language}" if language else ""}

Original request: {user_input}

{f"For commit message generation:" if operation == "commit" else ""}
{f"1. Analyze the diff to understand what changed" if operation == "commit" else ""}
{f"2. Group related changes into logical commits if needed" if operation == "commit" else ""}
{f"3. Write clear, descriptive commit messages" if operation == "commit" else ""}
{f"4. Include breaking change indicators if applicable" if operation == "commit" else ""}

{f"For branch strategy:" if operation == "branch" else ""}
{f"1. Suggest appropriate branch names following conventions" if operation == "branch" else ""}
{f"2. Recommend branching strategy (feature branch, git-flow, trunk-based)" if operation == "branch" else ""}

{f"For merge conflict resolution:" if operation == "merge" else ""}
{f"1. Explain the conflict context" if operation == "merge" else ""}
{f"2. Suggest the best resolution approach" if operation == "merge" else ""}

{f"For diff explanation:" if operation == "explain" else ""}
{f"1. Summarize what changed at a high level" if operation == "explain" else ""}
{f"2. Highlight important or risky changes" if operation == "explain" else ""}
{f"3. Note any potential issues introduced" if operation == "explain" else ""}

Provide specific, actionable Git commands where helpful."""

    return SkillResult(prompt=prompt, context=context)
