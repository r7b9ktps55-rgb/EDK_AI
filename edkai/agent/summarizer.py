"""Conversation summarizer with sliding window.

Keeps recent messages in full, summarizes older ones to fit context window.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConversationWindow:
    """A window of conversation messages."""
    messages: list[dict[str, str]] = field(default_factory=list)
    summary: str = ""  # Summary of older messages
    total_messages: int = 0


class ConversationSummarizer:
    """Manages conversation history with sliding window.
    
    Strategy:
    - Keep last N messages in full (default 20)
    - Summarize everything before that into a compact summary
    - Preserve all tool calls and their results in summary
    """
    
    def __init__(self, keep_recent: int = 20) -> None:
        self.keep_recent = keep_recent
        self.all_messages: list[dict[str, str]] = []
        self.summary: str = ""
        self.total_count: int = 0
    
    def add_message(self, role: str, content: str, **kwargs: Any) -> None:
        """Add a message to history."""
        msg = {"role": role, "content": content, **kwargs}
        self.all_messages.append(msg)
        self.total_count += 1
    
    def get_context_messages(self) -> list[dict[str, str]]:
        """Get messages for AI context — recent in full + summary of older."""
        if len(self.all_messages) <= self.keep_recent:
            return [{"role": m["role"], "content": m["content"]} 
                    for m in self.all_messages]
        
        # Recent messages in full
        recent = self.all_messages[-self.keep_recent:]
        recent_simple = [{"role": m["role"], "content": m["content"]} 
                        for m in recent]
        
        # If we have a summary, prepend it
        if self.summary:
            summary_msg = {
                "role": "system",
                "content": f"[Earlier conversation summary]:\n{self.summary}",
            }
            return [summary_msg] + recent_simple
        
        return recent_simple
    
    async def summarize_old_messages(self, ai_client: Any) -> str:
        """Summarize older messages using AI.
        
        Called when conversation exceeds keep_recent * 1.5 messages.
        """
        if len(self.all_messages) <= self.keep_recent:
            return ""
        
        old_messages = self.all_messages[:-self.keep_recent]
        
        # Build text to summarize
        lines: list[str] = []
        for m in old_messages:
            role = m["role"]
            content = m["content"]
            # Truncate very long messages
            if len(content) > 500:
                content = content[:500] + "..."
            lines.append(f"{role}: {content}")
        
        to_summarize = "\n".join(lines)
        
        prompt = f"""Summarize this conversation history concisely. 
Focus on: what files were discussed, what changes were made, what decisions were taken.
Keep under 300 words.

{to_summarize}"""
        
        try:
            summary = ""
            async for chunk in ai_client.chat(
                [{"role": "user", "content": prompt}],
                stream=False,
            ):
                summary += chunk
            
            self.summary = summary.strip()
            
            # Remove summarized messages from active storage
            self.all_messages = self.all_messages[-self.keep_recent:]
            
            return self.summary
        except Exception:
            # If summarization fails, just keep raw messages
            return ""
    
    def should_summarize(self) -> bool:
        """Check if we should summarize now."""
        return len(self.all_messages) > int(self.keep_recent * 1.5)
    
    def clear(self) -> None:
        """Clear all history."""
        self.all_messages.clear()
        self.summary = ""
        self.total_count = 0
    
    @property
    def message_count(self) -> int:
        return self.total_count
