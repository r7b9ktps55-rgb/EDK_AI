"""Prompt templates for Terminal Studio AI assistant.

Provides system prompt constants and helper functions to generate
context-rich prompts for common coding tasks.
"""

from __future__ import annotations
from typing import Any, List, Optional


SYSTEM_PROMPT: str = (
    "You are a helpful, expert coding assistant integrated into Terminal Studio, "
    "a terminal-based IDE. You write clean, well-documented, idiomatic code. "
    "You explain concepts clearly and concisely. You review code for bugs, "
    "performance issues, and style improvements. You suggest fixes with "
    "specific line references when possible. Always prefer practical, "
    "production-ready solutions. Respond in the same language the user writes in."
)


def generate_code_prompt(task: str, language: str, context: Optional[str] = None) -> str:
    """Build a prompt for generating new code.

    Args:
        task: Description of what the code should do.
        language: Target programming language.
        context: Optional existing code or project context to consider.

    Returns:
        A formatted prompt string ready for the LLM.
    """
    lines: List[str] = [
        f"Generate {language} code for the following task:",
        "",
        task,
        "",
        "Requirements:",
        "- Write clean, idiomatic, well-commented code.",
        "- Include any necessary imports or setup.",
        "- Provide a brief explanation after the code block.",
    ]
    if context:
        lines.extend([
            "",
            "Existing context (file content or related code):",
            "```",
            context,
            "```",
        ])
    return "\n".join(lines)


def explain_code_prompt(code: str, language: str) -> str:
    """Build a prompt for explaining existing code.

    Args:
        code: The source code to explain.
        language: Programming language of the code.

    Returns:
        A formatted prompt string.
    """
    return (
        f"Explain the following {language} code step by step.\n\n"
        "For each significant block, describe:\n"
        "- What it does\n"
        "- Why it is written that way\n"
        "- Any potential edge cases or gotchas\n\n"
        "```\n"
        f"{code}\n"
        "```"
    )


def fix_code_prompt(code: str, error: str, language: str) -> str:
    """Build a prompt for fixing buggy code.

    Args:
        code: The source code that contains the error.
        error: The error message or description of the problem.
        language: Programming language of the code.

    Returns:
        A formatted prompt string.
    """
    return (
        f"Fix the following {language} code.\n\n"
        f"Error / problem description:\n{error}\n\n"
        "Instructions:\n"
        "- Identify the root cause.\n"
        "- Provide the corrected code in a single fenced block.\n"
        "- Briefly explain what was wrong and how you fixed it.\n\n"
        "```\n"
        f"{code}\n"
        "```"
    )


def review_code_prompt(code: str, language: str) -> str:
    """Build a prompt for reviewing code quality.

    Args:
        code: The source code to review.
        language: Programming language of the code.

    Returns:
        A formatted prompt string.
    """
    return (
        f"Review the following {language} code.\n\n"
        "Please assess:\n"
        "1. Bugs or logic errors\n"
        "2. Performance issues or inefficiencies\n"
        "3. Security concerns\n"
        "4. Style and readability\n"
        "5. Missing tests or error handling\n\n"
        "For each issue, give the line number (if applicable) and a concrete suggestion.\n"
        "Also mention anything particularly well done.\n\n"
        "```\n"
        f"{code}\n"
        "```"
    )


# ---------------------------------------------------------------------------
# Ghost / inline-completion prompts
# ---------------------------------------------------------------------------



def ghost_suggestion_prompt(context: str, language: str) -> str:
    """Build a prompt for ghost-text inline completion.

    Args:
        context: Code preceding the cursor (up to ~200 lines).
        language: Target programming language.

    Returns:
        A prompt that asks the model to continue the code with 1-5 lines.
    """
    return (
        f"You are an expert {language} programmer. "
        "Continue the code below with the most likely next 1-5 lines. "
        "Only output the continuation—no explanations, no markdown fences, no repetition of existing code.\n\n"
        "```\n"
        f"{context}\n"
        "```"
    )

def generate_from_comment_prompt(comment: str, language: str, context: Optional[str] = None) -> str:
    """Build a prompt to generate a full function/class from a comment description.

    Args:
        comment: Natural-language description (e.g. a comment line).
        language: Target programming language.
        context: Optional surrounding file context.

    Returns:
        A formatted prompt string.
    """
    lines: List[str] = [
        f"Generate a complete, idiomatic {language} implementation for the following description:",
        "",
        f"Description: {comment}",
        "",
        "Requirements:",
        "- Write a full function or class with proper signature.",
        "- Include necessary imports if used.",
        "- Add brief inline comments for non-obvious logic.",
        "- Do NOT wrap the output in markdown code fences.",
    ]
    if context:
        lines.extend([
            "",
            "Existing context:",
            "```",
            context,
            "```",
        ])
    return "\n".join(lines)

def generate_docstring_prompt(code: str, language: str) -> str:
    """Build a prompt to generate a docstring for a function/class.

    Args:
        code: The function or class body to document.
        language: Programming language of the code.

    Returns:
        A formatted prompt string.
    """
    style = "Google/NumPy" if language == "python" else "language-idiomatic"
    return (
        f"Generate a {style} style docstring for the following {language} code.\n"
        "Only output the docstring text—no markdown fences, no extra commentary.\n\n"
        "```\n"
        f"{code}\n"
        "```"
    )

def refactor_prompt(code: str, instruction: str, language: str) -> str:
    """Build a prompt for AI-powered code refactoring.

    Args:
        code: The source code to refactor.
        instruction: Human instruction, e.g. "extract to function".
        language: Programming language of the code.

    Returns:
        A formatted prompt string.
    """
    return (
        f"Refactor the following {language} code according to this instruction: {instruction}\n\n"
        "Requirements:\n"
        "- Preserve all existing behavior (no functional changes unless requested).\n"
        "- Improve readability and maintainability.\n"
        "- Only output the refactored code—no explanations, no markdown fences.\n\n"
        "```\n"
        f"{code}\n"
        "```"
    )

def optimize_prompt(code: str, language: str) -> str:
    """Build a prompt for AI-powered code optimization.

    Args:
        code: The source code to optimize.
        language: Programming language of the code.

    Returns:
        A formatted prompt string.
    """
    return (
        f"Optimize the following {language} code for performance and clarity.\n\n"
        "Requirements:\n"
        "- Preserve exact external behavior.\n"
        "- Reduce time/space complexity where possible.\n"
        "- Use idiomatic patterns and builtins.\n"
        "- Only output the optimized code—no explanations, no markdown fences.\n\n"
        "```\n"
        f"{code}\n"
        "```"
    )

def explain_selection_prompt(code: str, language: str) -> str:
    """Build a prompt for explaining a code selection.

    Args:
        code: The selected source code.
        language: Programming language of the code.

    Returns:
        A formatted prompt string.
    """
    return (
        f"Explain the following {language} code in plain English. "
        "Describe what it does, why it works, and any notable edge cases or assumptions.\n\n"
        "```\n"
        f"{code}\n"
        "```"
    )

def inline_description_prompt(description: str, language: str, file_context: Optional[str] = None) -> str:
    """Build a prompt to generate code from an inline natural-language description.

    Args:
        description: Natural-language description, e.g. "function to validate email".
        language: Target programming language.
        file_context: Optional surrounding file content.

    Returns:
        A formatted prompt string.
    """
    lines: List[str] = [
        f"Generate {language} code for: {description}",
        "",
        "Requirements:",
        "- Provide a complete, self-contained implementation.",
        "- Include necessary imports.",
        "- Only output the code—no markdown fences, no extra commentary.",
    ]
    if file_context:
        lines.extend([
            "",
            "File context:",
            "```",
            file_context,
            "```",
        ])
    return "\n".join(lines)

def generate_tests_prompt(code: str, language: str, framework: Optional[str] = None) -> str:
    """Build a prompt for generating unit tests.

    Args:
        code: The source code to generate tests for.
        language: Programming language of the code.
        framework: Target test framework (e.g. ``pytest``, ``jest``).
            If omitted the model should pick the idiomatic default.

    Returns:
        A formatted prompt string.
    """
    fw_line = f"\nUse the {framework} framework." if framework else ""
    return (
        f"Generate comprehensive unit tests for the following {language} code.{fw_line}\n\n"
        "Requirements:\n"
        "- Test all public functions and methods.\n"
        "- Include happy-path and error-path cases.\n"
        "- Mock external dependencies where appropriate.\n"
        "- Use standard idioms for the chosen framework.\n"
        "- Output ONLY the complete test file content (no extra prose).\n\n"
        "```\n"
        f"{code}\n"
        "```"
    )

def generate_edge_cases_prompt(code: str, language: str) -> str:
    """Build a prompt for listing edge cases.

    Args:
        code: The source code to analyse.
        language: Programming language of the code.

    Returns:
        A formatted prompt string.
    """
    return (
        f"Analyse the following {language} code and list important edge cases "
        "that should be tested.\n\n"
        "Return each edge case as a single bullet line starting with '- '.\n"
        "Focus on: boundary values, null/empty inputs, concurrency, "
        "type mismatches, and resource limits.\n\n"
        "```\n"
        f"{code}\n"
        "```"
    )

def auto_fix_prompt(code: str, error_output: str, language: str) -> str:
    """Build a prompt for diagnosing and fixing code.

    Args:
        code: The source code that contains the error.
        error_output: Error message, traceback, or compiler output.
        language: Programming language of the code.

    Returns:
        A formatted prompt string.
    """
    return (
        f"Diagnose and fix the following {language} code.\n\n"
        f"Error output:\n```\n{error_output}\n```\n\n"
        "Instructions:\n"
        "- Identify the root cause of the error.\n"
        "- Provide the corrected code in a single fenced code block.\n"
        "- After the code block, briefly explain what was wrong and how you fixed it.\n\n"
        "```\n"
        f"{code}\n"
        "```"
    )

def diagnose_only_prompt(code: str, error_output: str, language: str) -> str:
    """Build a prompt for diagnosis only (no fix).

    Args:
        code: The source code that contains the error.
        error_output: Error message, traceback, or compiler output.
        language: Programming language of the code.

    Returns:
        A formatted prompt string.
    """
    return (
        f"Diagnose the following {language} code. Do NOT provide fixed code.\n\n"
        f"Error output:\n```\n{error_output}\n```\n\n"
        "Explain:\n"
        "- What the root cause of the error is.\n"
        "- Which line(s) are involved.\n"
        "- What approach should be taken to fix it.\n\n"
        "```\n"
        f"{code}\n"
        "```"
    )

def lint_fix_prompt(code: str, language: str) -> str:
    """Build a prompt for linting / style fixing.

    Args:
        code: The source code to lint.
        language: Programming language of the code.

    Returns:
        A formatted prompt string.
    """
    return (
        f"Review and clean up the following {language} code for style, "
        "linting issues, and best-practice violations.\n\n"
        "Instructions:\n"
        "- Provide the cleaned code in a single fenced code block.\n"
        "- After the code block, list each issue found as a bullet line starting with '- '.\n"
        "- Include line numbers where applicable.\n\n"
        "```\n"
        f"{code}\n"
        "```"
    )


# ---------------------------------------------------------------------------
# Security analysis prompts
# ---------------------------------------------------------------------------


def analyze_vulnerability_prompt(vuln: dict) -> str:
    """Build a prompt for AI vulnerability analysis and confirmation.

    Args:
        vuln: Dictionary containing vulnerability fields such as
            ``name``, ``vuln_type``, ``severity``, ``url``, ``parameter``,
            ``payload``, ``evidence``, ``description``.

    Returns:
        A formatted prompt string requesting structured analysis output.
    """
    lines: List[str] = [
        "You are an expert application security analyst. Analyze the following vulnerability finding and provide a structured assessment.",
        "",
        "=== VULNERABILITY DETAILS ===",
        f"Name: {vuln.get('name', 'Unknown')}",
        f"Type: {vuln.get('vuln_type', 'Unknown')}",
        f"Initial Severity: {vuln.get('severity', 'unknown')}",
        f"URL: {vuln.get('url', 'N/A')}",
        f"Parameter: {vuln.get('parameter', 'N/A')}",
        f"Payload: {vuln.get('payload', 'N/A')}",
        f"Evidence: {vuln.get('evidence', 'N/A')}",
        f"Description: {vuln.get('description', 'N/A')}",
        "",
        "=== YOUR TASK ===",
        "1. TRUE POSITIVE ASSESSMENT: Is this a genuine vulnerability or a false positive? Explain your reasoning.",
        "2. PROOF OF CONCEPT: Generate a concrete PoC (curl command, Python script, or HTTP request) that demonstrates the vulnerability.",
        "3. IMPACT ASSESSMENT: Describe the real-world impact if exploited (data loss, RCE, privilege escalation, etc.).",
        "4. REMEDIATION: Suggest a specific, actionable fix with code or configuration changes.",
        "5. SEVERITY RATING: Re-assess severity as critical / high / medium / low / info with justification.",
        "",
        "=== OUTPUT FORMAT ===",
        "Respond in this exact format (each section on its own line):",
        "",
        "CONFIRMED: true/false",
        "CONFIDENCE: 0.0-1.0",
        "POC: ```\n<PoC code>\n```",
        "IMPACT: <impact description>",
        "FIX: ```\n<fix code or instructions>\n```",
        "SEVERITY: critical/high/medium/low/info",
        "NOTES: <any additional notes>",
        "",
        "Be thorough and specific. If you believe this is a false positive, explain why and still provide the other fields as 'N/A'.",
    ]
    return "\n".join(lines)


def generate_poc_prompt(vuln_type: str, url: str, payload: str) -> str:
    """Build a prompt for generating a Proof-of-Concept exploit.

    Args:
        vuln_type: The vulnerability type slug, e.g. ``sqli``, ``xss``.
        url: The affected endpoint URL.
        payload: The payload that triggered the finding.

    Returns:
        A formatted prompt string requesting a concrete PoC.
    """
    return (
        f"You are an expert penetration tester. Generate a concrete Proof-of-Concept (PoC) "
        f"for a {vuln_type} vulnerability.\n\n"
        f"Target URL: {url}\n"
        f"Known payload: {payload}\n\n"
        "Requirements:\n"
        "- Provide a working curl command OR a short Python script that demonstrates the exploit.\n"
        "- Include expected output or response indicators that prove the vulnerability exists.\n"
        "- Add brief comments explaining what each part of the PoC does.\n"
        "- The PoC must be safe for testing (read-only where possible).\n\n"
        "Output ONLY the PoC code wrapped in a markdown code block."
    )


def security_report_summary_prompt(scan_result: dict) -> str:
    """Build a prompt for generating an executive security report summary.

    Args:
        scan_result: Dictionary with scan metadata including
            ``target``, ``severity_counts``, ``confirmed_count``,
            ``duration_seconds``, ``vulnerability_count``.

    Returns:
        A formatted prompt string requesting a natural-language executive summary.
    """
    counts = scan_result.get("severity_counts", {})
    total = scan_result.get("vulnerability_count", sum(counts.values()))
    confirmed = scan_result.get("confirmed_count", "N/A")
    target = scan_result.get("target", "Unknown target")
    duration = scan_result.get("duration_seconds", "N/A")

    return (
        "You are a senior security analyst writing an executive summary for stakeholders.\n\n"
        f"Scan target: {target}\n"
        f"Total findings: {total}\n"
        f"Severity breakdown: Critical={counts.get('critical', 0)}, "
        f"High={counts.get('high', 0)}, "
        f"Medium={counts.get('medium', 0)}, "
        f"Low={counts.get('low', 0)}, "
        f"Info={counts.get('info', 0)}\n"
        f"AI-confirmed true positives: {confirmed}\n"
        f"Scan duration: {duration}s\n\n"
        "Write a concise 3-5 sentence executive summary in professional tone.\n"
        "Highlight the most critical risks, overall posture, and immediate actions needed.\n"
        "Do not use markdown headers—just plain paragraphs."
    )


def remediation_plan_prompt(vulns: List[dict]) -> str:
    """Build a prompt for generating a prioritized remediation plan.

    Args:
        vuln: List of vulnerability dictionaries, each containing at least
            ``name``, ``vuln_type``, ``severity``, ``url``, ``fix``.

    Returns:
        A formatted prompt string requesting a priority-ordered remediation roadmap.
    """
    lines: List[str] = [
        "You are a security engineering lead. Create a prioritized remediation plan for the following vulnerabilities.",
        "",
        "=== VULNERABILITIES ===",
    ]
    for idx, v in enumerate(vulns, 1):
        lines.extend([
            f"{idx}. {v.get('name', 'Unknown')} ({v.get('vuln_type', 'unknown')})",
            f"   Severity: {v.get('severity', 'unknown')}",
            f"   URL: {v.get('url', 'N/A')}",
            f"   Suggested fix: {v.get('fix', 'N/A')}",
            "",
        ])

    lines.extend([
        "=== YOUR TASK ===",
        "Produce a remediation roadmap with the following for each item:",
        "- Priority order (1 = fix first)",
        "- Estimated effort (Quick / Medium / Large)",
        "- Recommended assignee role (e.g. Backend Dev, DevOps, Security Team)",
        "- Specific action items with file/endpoint references",
        "",
        "=== OUTPUT FORMAT ===",
        "For each vulnerability, output exactly these lines:",
        "",
        "PRIORITY: <number>",
        "NAME: <vulnerability name>",
        "EFFORT: Quick/Medium/Large",
        "ASSIGNEE: <role>",
        "ACTIONS: <bullet list of concrete steps>",
        "---",
        "",
        "Order by severity first (critical > high > medium > low > info), then by exploitability.",
    ])
    return "\n".join(lines)
