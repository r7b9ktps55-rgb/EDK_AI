"""AI chat panel widget for Terminal Studio.

Provides a scrollable chat history, message input, quick-action buttons,
and streaming display of AI responses using the AIClient.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Button, Input, Static

from edkai.ai.client import AIClient, AIError, AINetworkError
from edkai.ai import prompts


class ChatMessage(Static):
    """A single chat message bubble."""

    DEFAULT_CSS = """
    ChatMessage {
        height: auto;
        margin: 1 0;
        padding: 1 2;
        border: solid $primary-darken-2;
        background: $surface;
    }
    ChatMessage.user {
        border: solid $success-darken-2;
        background: $success-darken-3;
    }
    ChatMessage.assistant {
        border: solid $accent-darken-2;
        background: $surface-darken-1;
    }
    ChatMessage.loading {
        border: solid $warning;
        background: $warning-darken-3;
    }
    """

    def __init__(
        self,
        content: str,
        role: str = "assistant",
        *,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        """Initialise a chat message.

        Args:
            content: Message text (Rich markup is supported).
            role: ``user``, ``assistant``, or ``loading``.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(
            content,
            name=name,
            id=id,
            classes=f"{role} {classes or ''}".strip(),
        )
        self.role = role

    def update_content(self, content: str) -> None:
        """Update the displayed text in place."""
        self.update(content)


class AIPanel(Static):
    """AI assistant chat panel.

    Displays a scrollable chat history, an input field, quick-action buttons,
    and handles streaming AI responses via :class:`AIClient`.
    """

    DEFAULT_CSS = """
    AIPanel {
        layout: vertical;
        height: 1fr;
        border: solid $accent;
    }
    AIPanel #chat-scroll {
        height: 1fr;
        background: $surface-darken-1;
    }
    AIPanel #chat-history {
        height: auto;
    }
    AIPanel #quick-actions {
        height: auto;
        dock: bottom;
    }
    AIPanel #input-row {
        height: auto;
        dock: bottom;
    }
    AIPanel #message-input {
        width: 1fr;
    }
    """

    _client: AIClient | None = None
    _context_file: Optional[str] = None
    _context_code: Optional[str] = None
    _chat_messages: List[Dict[str, str]]  # OpenAI-format message history
    _streaming: bool = False

    def __init__(
        self,
        client: AIClient | None = None,
        *,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        """Initialise the AI panel.

        Args:
            client: An optional :class:`AIClient` instance.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._client = client
        self._chat_messages = [
            {"role": "system", "content": prompts.SYSTEM_PROMPT},
        ]

    def compose(self) -> ComposeResult:
        """Compose the AI panel UI."""
        with VerticalScroll(id="chat-scroll"):
            yield Vertical(id="chat-history")
        with Horizontal(id="quick-actions"):
            yield Button("Generate", id="btn-generate", variant="primary")
            yield Button("Explain", id="btn-explain", variant="default")
            yield Button("Fix", id="btn-fix", variant="error")
            yield Button("Review", id="btn-review", variant="default")
        with Horizontal(id="input-row"):
            yield Input(
                placeholder="Ask the assistant... (Ctrl+Enter to send)",
                id="message-input",
            )
            yield Button("Send", id="btn-send", variant="primary")

    # ------------------------------------------------------------------
    # Context helpers
    # ------------------------------------------------------------------

    def set_context(self, file_path: str, code: str) -> None:
        """Set the current file context for AI prompts.

        Args:
            file_path: Path to the active source file.
            code: Content of the active source file.
        """
        self._context_file = file_path
        self._context_code = code

    def clear_chat(self) -> None:
        """Clear the chat history and UI."""
        self._chat_messages = [
            {"role": "system", "content": prompts.SYSTEM_PROMPT},
        ]
        history = self.query_one("#chat-history", Vertical)
        history.remove_children()

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    def _add_message(self, content: str, role: str = "assistant") -> ChatMessage:
        """Append a message widget to the chat history.

        Args:
            content: Text content (Rich markup supported).
            role: Message role.

        Returns:
            The created :class:`ChatMessage` widget.
        """
        history = self.query_one("#chat-history", Vertical)
        msg = ChatMessage(content, role=role)
        history.mount(msg)
        # Scroll to the bottom.
        scroll = self.query_one("#chat-scroll", VerticalScroll)
        scroll.scroll_end(animate=False)
        return msg

    def _add_loading(self) -> ChatMessage:
        """Add a loading indicator message."""
        return self._add_message("Thinking ...", role="loading")

    def _remove_loading(self, widget: ChatMessage) -> None:
        """Remove a loading indicator from the chat history."""
        widget.remove()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle quick-action and send button presses."""
        button_id = event.button.id
        if button_id == "btn-send":
            await self._send_user_message()
        elif button_id == "btn-generate":
            await self._quick_action("generate")
        elif button_id == "btn-explain":
            await self._quick_action("explain")
        elif button_id == "btn-fix":
            await self._quick_action("fix")
        elif button_id == "btn-review":
            await self._quick_action("review")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Ctrl+Enter or plain Enter in the message input."""
        if event.input.id == "message-input":
            await self._send_user_message()

    async def _send_user_message(self) -> None:
        """Read the input field and send a free-form user message to the AI."""
        inp = self.query_one("#message-input", Input)
        text = inp.value.strip()
        if not text:
            return
        inp.value = ""

        self._add_message(text, role="user")
        self._chat_messages.append({"role": "user", "content": text})
        await self._stream_ai_response()

    async def _quick_action(self, action: str) -> None:
        """Execute a quick action using the current file context.

        Args:
            action: One of ``generate``, ``explain``, ``fix``, ``review``.
        """
        if self._context_code is None or self._context_file is None:
            self._add_message(
                "[no file context set — open a file first]",
                role="assistant",
            )
            return

        # Determine language from file extension.
        from pathlib import Path

        ext = Path(self._context_file).suffix.lstrip(".").lower()
        language_map = {
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "tsx": "typescript",
            "rs": "rust",
            "go": "go",
            "c": "c",
            "cpp": "cpp",
            "cc": "cpp",
            "sh": "bash",
        }
        language = language_map.get(ext, ext)

        if action == "generate":
            prompt_text = prompts.generate_code_prompt(
                task="Generate code based on the current file.",
                language=language,
                context=self._context_code,
            )
        elif action == "explain":
            prompt_text = prompts.explain_code_prompt(
                code=self._context_code,
                language=language,
            )
        elif action == "fix":
            prompt_text = prompts.fix_code_prompt(
                code=self._context_code,
                error="The user has not specified an error; review and fix any obvious issues.",
                language=language,
            )
        elif action == "review":
            prompt_text = prompts.review_code_prompt(
                code=self._context_code,
                language=language,
            )
        else:
            return

        self._add_message(f"[{action}] {self._context_file}", role="user")
        self._chat_messages.append({"role": "user", "content": prompt_text})
        await self._stream_ai_response()

    # ------------------------------------------------------------------
    # Streaming AI response
    # ------------------------------------------------------------------

    async def _stream_ai_response(self) -> None:
        """Stream the AI response and update the UI."""
        if self._client is None:
            self._add_message(
                "[AI client not configured — set API key and base URL]",
                role="assistant",
            )
            return
        if self._streaming:
            return

        self._streaming = True
        loading = self._add_loading()

        # Container for the assistant's reply.
        assistant_content = ""
        msg_widget: ChatMessage | None = None

        try:
            async for chunk in self._client.chat(
                self._chat_messages,
                stream=True,
            ):
                if msg_widget is None:
                    self._remove_loading(loading)
                    msg_widget = self._add_message("", role="assistant")

                assistant_content += chunk
                msg_widget.update_content(assistant_content)
                # Keep scrolled to bottom.
                scroll = self.query_one("#chat-scroll", VerticalScroll)
                scroll.scroll_end(animate=False)
                # Brief yield so UI stays responsive.
                await asyncio.sleep(0.01)

            if msg_widget is None:
                self._remove_loading(loading)
                self._add_message("[no response from AI]", role="assistant")
            else:
                self._chat_messages.append(
                    {"role": "assistant", "content": assistant_content}
                )

        except AINetworkError as exc:
            self._remove_loading(loading)
            self._add_message(
                f"[network error: {exc}]",
                role="assistant",
            )
        except AIError as exc:
            self._remove_loading(loading)
            self._add_message(
                f"[AI error: {exc}]",
                role="assistant",
            )
        except Exception as exc:
            self._remove_loading(loading)
            self._add_message(
                f"[unexpected error: {exc}]",
                role="assistant",
            )
        finally:
            self._streaming = False
