"""Prompt builder for the optimize skill."""
from edkai.ai.skills.manager import SkillResult


def build_prompt(user_input: str, context: dict) -> SkillResult:
    code = context.get("code", "")
    language = context.get("language", "")
    metric = context.get("metric", "general")  # general, cpu, memory, latency, throughput
    constraints = context.get("constraints", "")

    metric_focus = {
        "cpu": "Focus on reducing CPU usage: eliminate unnecessary computations, use vectorized operations, reduce loop nesting, and leverage compiled extensions.",
        "memory": "Focus on reducing memory usage: use generators instead of lists, stream large datasets, avoid unnecessary object creation, and use __slots__ or compact data structures.",
        "latency": "Focus on reducing response time: optimize hot paths, use caching/memoization, reduce I/O blocking, and add asynchronous operations where beneficial.",
        "throughput": "Focus on increasing throughput: parallelize work, batch operations, use connection pooling, and minimize lock contention.",
    }

    prompt = f"""Analyze and optimize the following {language} code for better performance.

{metric_focus.get(metric, "Optimize for overall performance including CPU, memory, and latency.")}

{f"Constraints: {constraints}" if constraints else ""}

Original code:
```{language}
{code}
```

Provide your optimization analysis in this structure:

1. **Performance Profile** - Identify the bottlenecks with Big-O analysis
   - Current time complexity:
   - Current space complexity:
   - Hot spots (lines/functions consuming most resources):

2. **Optimization Strategy** - Explain the approach taken
   - Algorithmic improvements:
   - Data structure changes:
   - Language-specific optimizations:

3. **Optimized Code** - The complete optimized solution
```{language}
[optimized code here]
```

4. **Benchmark Comparison** - Expected improvements
   - Time complexity after optimization:
   - Space complexity after optimization:
   - Estimated speedup:
   - Trade-offs (if any):

5. **Further Optimizations** - Additional ideas if the user needs even more performance"""

    return SkillResult(prompt=prompt, context=context)
