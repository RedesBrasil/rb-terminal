"""
Chat Coordinator - Handles chat widget and conversation management.
Extracted from main_window.py for better separation of concerns.
"""

import asyncio
import logging
from typing import Optional, Callable, List, Tuple

from PySide6.QtCore import QObject, Signal

from core.data_manager import DataManager, ChatMessage
from gui.tab_session import TabSession
from gui.chat_widget import ChatWidget

logger = logging.getLogger(__name__)


class ChatCoordinator(QObject):
    """
    Coordinates chat widget, AI agent, and conversation persistence.

    Responsibilities:
    - Restoring chat state for sessions
    - Saving conversations to persistent storage
    - Processing chat messages through the agent
    - Managing conversation switching
    """

    # Signals
    processing_started = Signal()
    processing_finished = Signal()
    balance_updated = Signal(float)

    def __init__(self, chat_widget: ChatWidget, data_manager: DataManager, parent=None):
        super().__init__(parent)
        self._chat = chat_widget
        self._data_manager = data_manager
        self._agent_task: Optional[asyncio.Task] = None

    @property
    def agent_task(self) -> Optional[asyncio.Task]:
        """Get current agent task."""
        return self._agent_task

    def restore_chat_for_session(self, session: TabSession) -> None:
        """Restore chat widget state for a session."""
        # Clear current chat messages
        self._chat.clear_messages()

        # Load conversations for this host (if saved host)
        if session.host_id:
            convs = self._data_manager.get_conversations_for_host(session.host_id)
            conv_list = [(c.id, c.title, c.updated_at) for c in convs]
            self._chat.set_conversations(conv_list)
            self._chat.set_current_conversation(session.chat_state.conversation_id)
        else:
            # Quick connect - no saved conversations
            self._chat.set_conversations([])
            self._chat.set_current_conversation(None)

        # Restore display messages from session state
        if session.chat_state.display_messages:
            self._chat.restore_messages(session.chat_state.display_messages)

        # Sync agent messages if continuing a conversation
        if session.agent and session.chat_state.conversation_id:
            conv = self._data_manager.get_conversation_by_id(session.chat_state.conversation_id)
            if conv and conv.messages:
                # Restore agent.messages from conversation
                session.agent.messages = [
                    {
                        "role": m.role,
                        "content": m.content,
                        **({"tool_calls": m.tool_calls} if m.tool_calls else {}),
                        **({"tool_call_id": m.tool_call_id} if m.tool_call_id else {})
                    }
                    for m in conv.messages
                ]
                # Restore usage stats
                session.agent.usage_stats.prompt_tokens = conv.prompt_tokens
                session.agent.usage_stats.completion_tokens = conv.completion_tokens
                session.agent.usage_stats.total_tokens = conv.prompt_tokens + conv.completion_tokens
                session.agent.usage_stats.total_cost = conv.total_cost
                # Update cost display
                self._chat.update_cost(
                    conv.total_cost,
                    conv.prompt_tokens,
                    conv.completion_tokens
                )
        elif session.agent:
            # No conversation, show current session stats if any
            stats = session.agent.usage_stats
            if stats.total_tokens > 0:
                self._chat.update_cost(
                    stats.total_cost,
                    stats.prompt_tokens,
                    stats.completion_tokens
                )

        # Fetch account balance when restoring session
        if session.agent:
            asyncio.ensure_future(self._update_account_balance(session))

    async def _update_account_balance(self, session: TabSession) -> None:
        """Fetch and update account balance display."""
        if not session.agent:
            return
        try:
            balance = await session.agent.get_account_balance()
            self._chat.update_balance(balance)
            self.balance_updated.emit(balance)
        except Exception as e:
            logger.debug(f"Failed to update balance: {e}")

    def save_chat_to_conversation(self, session: TabSession) -> None:
        """Save current chat to persistent conversation."""
        # Only save for saved hosts (not quick connect)
        if not session.host_id or not session.agent:
            return

        # Convert agent messages to ChatMessage objects
        chat_messages = []
        for msg in session.agent.messages:
            chat_messages.append(ChatMessage(
                role=msg.get("role", "user"),
                content=msg.get("content", ""),
                tool_calls=msg.get("tool_calls"),
                tool_call_id=msg.get("tool_call_id")
            ))

        if not chat_messages:
            return

        # Get usage stats from agent
        usage = session.agent.usage_stats
        prompt_tokens = usage.prompt_tokens
        completion_tokens = usage.completion_tokens
        total_cost = usage.total_cost

        if session.chat_state.conversation_id:
            # Update existing conversation
            self._data_manager.update_conversation(
                session.chat_state.conversation_id,
                chat_messages,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_cost=total_cost
            )
        else:
            # Create new conversation
            conv = self._data_manager.create_conversation(session.host_id)
            session.chat_state.conversation_id = conv.id
            self._data_manager.update_conversation(
                conv.id,
                chat_messages,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_cost=total_cost
            )

        # Refresh conversation list in UI
        convs = self._data_manager.get_conversations_for_host(session.host_id)
        conv_list = [(c.id, c.title, c.updated_at) for c in convs]
        self._chat.set_conversations(conv_list)
        self._chat.set_current_conversation(session.chat_state.conversation_id)

    async def process_message(self, session: TabSession, message: str, web_search: bool = False) -> None:
        """Process chat message with AI agent."""
        if not session or not session.agent or not session.ssh_session:
            self._chat.add_message("Erro: Conecte-se a um host primeiro.", is_user=False)
            return

        self._chat.set_processing(True)
        self.processing_started.emit()

        try:
            response = await session.agent.chat(message, web_search=web_search)
            self._chat.add_message(response, is_user=False)

            # Update session chat state with current display messages
            session.chat_state.display_messages = self._chat.get_display_messages()

            # Save to persistent storage (only for saved hosts)
            self.save_chat_to_conversation(session)

            # Update account balance after response
            await self._update_account_balance(session)

        except asyncio.CancelledError:
            self._chat.add_message("Operacao cancelada.", is_user=False)
        except Exception as e:
            logger.error(f"Agent error: {e}")
            self._chat.add_message(f"Erro: {str(e)}", is_user=False)
        finally:
            self._chat.set_processing(False)
            self.processing_finished.emit()

    def start_message_processing(self, session: TabSession, message: str, web_search: bool = False) -> asyncio.Task:
        """Start processing a chat message and return the task."""
        self._agent_task = asyncio.ensure_future(self.process_message(session, message, web_search))
        return self._agent_task

    def stop_agent(self, session: TabSession) -> None:
        """Stop the current agent task."""
        if session and session.agent:
            session.agent.cancel()
        if self._agent_task and not self._agent_task.done():
            self._agent_task.cancel()

    def on_conversation_changed(self, session: TabSession, conv_id: str) -> None:
        """Handle conversation selection from dropdown."""
        if not session:
            return

        # Save current web search state before switching
        session.chat_state.web_search_enabled = self._chat.is_web_search_enabled()

        # Save current state first
        if session.chat_state.conversation_id and session.agent:
            self.save_chat_to_conversation(session)

        # Clear chat
        self._chat.clear_messages()

        if conv_id:
            # Load existing conversation
            conv = self._data_manager.get_conversation_by_id(conv_id)
            if conv:
                session.chat_state.conversation_id = conv_id

                # Restore display messages (only user and assistant with content)
                display_msgs = []
                for msg in conv.messages:
                    if msg.role == "user":
                        display_msgs.append((msg.content, True))
                    elif msg.role == "assistant" and msg.content:
                        display_msgs.append((msg.content, False))

                session.chat_state.display_messages = display_msgs
                self._chat.restore_messages(display_msgs)

                # Restore agent messages
                if session.agent:
                    session.agent.messages = [
                        {
                            "role": m.role,
                            "content": m.content,
                            **({"tool_calls": m.tool_calls} if m.tool_calls else {}),
                            **({"tool_call_id": m.tool_call_id} if m.tool_call_id else {})
                        }
                        for m in conv.messages
                    ]
                    # Restore usage stats from saved conversation
                    session.agent.usage_stats.prompt_tokens = conv.prompt_tokens
                    session.agent.usage_stats.completion_tokens = conv.completion_tokens
                    session.agent.usage_stats.total_tokens = conv.prompt_tokens + conv.completion_tokens
                    session.agent.usage_stats.total_cost = conv.total_cost

                # Update cost display
                self._chat.update_cost(
                    conv.total_cost,
                    conv.prompt_tokens,
                    conv.completion_tokens
                )

                # Reset web search state (not persisted per conversation)
                session.chat_state.web_search_enabled = False
                self._chat.set_web_search_enabled(False)
        else:
            # New conversation
            session.chat_state.clear()
            self._chat.set_web_search_enabled(False)
            if session.agent:
                session.agent.reset()

    def on_new_conversation(self, session: TabSession) -> None:
        """Handle new conversation request."""
        if not session:
            return

        # Save current conversation first (if exists)
        if session.chat_state.conversation_id and session.agent:
            self.save_chat_to_conversation(session)

        # Clear state
        session.chat_state.clear()
        self._chat.clear_messages()
        self._chat.set_current_conversation(None)
        self._chat.set_web_search_enabled(False)

        if session.agent:
            session.agent.reset()
