"""Prompt builder for the shell_helper skill."""
from edkai.ai.skills.manager import SkillResult


def build_prompt(user_input: str, context: dict) -> SkillResult:
    shell = context.get("shell", "bash")  # bash, zsh, fish, powershell
    task = context.get("task", "")
    working_dir = context.get("working_dir", "")
    files = context.get("files", "")
    danger_level = context.get("danger_level", "safe")  # safe, caution, destructive

    safety_warnings = {
        "destructive": "WARNING: This command may DELETE or OVERWRITE data. Show a clear warning and suggest dry-run alternatives (e.g., --dry-run, -n, or echo to preview).",
        "caution": "CAUTION: This command modifies system state. Suggest verification steps before execution.",
        "safe": "This is a read-only or non-destructive operation.",
    }

    shell_notes = {
        "bash": "Generate POSIX-compliant bash commands that work in most Linux environments.",
        "zsh": "Generate zsh commands leveraging zsh-specific features like glob qualifiers and advanced parameter expansion.",
        "fish": "Generate fish shell commands with fish-friendly syntax (no bashisms).",
        "powershell": "Generate PowerShell cmdlets and pipelines with proper parameter usage.",
    }

    prompt = f"""Generate a shell command for the following task.

Target shell: {shell}
{shell_notes.get(shell, shell_notes["bash"])}

{safety_warnings.get(danger_level, "")}

{f"Working directory: {working_dir}" if working_dir else ""}
{f"Relevant files/context:
{files}" if files else ""}

Task description: {task or user_input}

Provide your response in this format:

1. **Command** - The complete, copy-paste ready command
   ```{shell}
   [command here]
   ```

2. **Explanation** - Break down what each part does
   - Flag/option explanations
   - Pipeline stages
   - Variable substitutions

3. **Prerequisites** - Any tools that need to be installed

4. **Safety Notes** - Warnings about destructive operations or side effects
   {f"- ALWAYS suggest a dry-run version first" if danger_level == "destructive" else ""}
   {f"- Suggest backing up data before running" if danger_level == "destructive" else ""}

5. **Alternatives** - Other ways to achieve the same result (e.g., GUI tools, different commands)

Keep commands concise and efficient. Prefer standard Unix tools over external dependencies when possible."""

    return SkillResult(prompt=prompt, context=context)
