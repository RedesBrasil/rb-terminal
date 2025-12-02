"""
AI Agent for SSH Terminal using PydanticAI.
Provides tools for executing commands on remote hosts.
"""

import asyncio
import json
import logging
from typing import Optional, Callable, Any
from dataclasses import dataclass

import httpx

from core.settings import get_settings_manager

logger = logging.getLogger(__name__)


@dataclass
class AgentDeps:
    """Dependencies for the AI agent."""
    execute_command: Callable[[str], Any]  # Async function to execute SSH commands
    on_command_executed: Optional[Callable[[str, str], None]] = None  # Callback(cmd, output)
    on_thinking: Optional[Callable[[str], None]] = None  # Callback for AI thinking
    device_type: Optional[str] = None  # Type of device (Linux, MikroTik, etc.)


class SSHAgent:
    """
    AI Agent that can execute SSH commands.
    Uses OpenRouter API with function calling.
    """

    BASE_SYSTEM_PROMPT = """Você é um especialista em administração de sistemas, redes e servidores.
Você tem experiência com Mikrotik RouterOS, Cisco IOS, Huawei e Linux.

Seu objetivo é ajudar o usuário a diagnosticar e resolver problemas executando comandos SSH.

Regras importantes:
1. Sempre leia a saída do comando antes de decidir o próximo passo
2. Seja conciso nas respostas
3. Explique o que você encontrou após cada comando
4. Se algo der errado, explique o problema e sugira soluções
5. Para comandos potencialmente perigosos (rm, format, reset, reboot), avise o usuário primeiro

Você tem acesso à ferramenta execute_command para rodar comandos no terminal SSH conectado."""

    DEVICE_TYPE_PROMPTS = {
        "linux": "\n\nVocê está conectado a um sistema Linux. Use comandos Linux padrão (bash, systemctl, ip, etc.).",
        "mikrotik": "\n\nVocê está conectado a um roteador MikroTik RouterOS. Use comandos RouterOS (interface print, ip address print, /system resource print, etc.).",
        "huawei": "\n\nVocê está conectado a um dispositivo Huawei. Use comandos Huawei CLI (display, system-view, etc.).",
        "cisco": "\n\nVocê está conectado a um dispositivo Cisco IOS. Use comandos Cisco CLI (show, configure terminal, etc.).",
    }

    TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "execute_command",
                "description": "Executa um comando SSH no dispositivo remoto conectado e retorna a saída",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "O comando a ser executado no terminal SSH"
                        }
                    },
                    "required": ["command"]
                }
            }
        }
    ]

    def __init__(self, deps: AgentDeps):
        """
        Initialize the SSH Agent.

        Args:
            deps: Agent dependencies including command executor
        """
        self.deps = deps
        self._settings_manager = get_settings_manager()
        self.api_key = self._settings_manager.get_api_key()
        self.model = self._settings_manager.get_model()
        self.messages: list[dict] = []
        self._cancelled = False
        self._http_client: Optional[httpx.AsyncClient] = None

    def _get_system_prompt(self) -> str:
        """
        Get the system prompt with device-specific context.

        Returns:
            System prompt string with device type information if available
        """
        prompt = self.BASE_SYSTEM_PROMPT

        device_type = self.deps.device_type
        if device_type:
            # Try to find a specific prompt for this device type
            device_key = device_type.lower()
            if device_key in self.DEVICE_TYPE_PROMPTS:
                prompt += self.DEVICE_TYPE_PROMPTS[device_key]
            else:
                # Generic message for custom device types
                prompt += f"\n\nVocê está conectado a um dispositivo do tipo: {device_type}. Use comandos apropriados para este sistema."

        return prompt

    @property
    def http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                base_url="https://openrouter.ai/api/v1",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/rb-terminal",
                    "X-Title": "RB Terminal"
                },
                timeout=60.0
            )
        return self._http_client

    def cancel(self) -> None:
        """Cancel the current operation."""
        self._cancelled = True
        logger.info("Agent cancelled")

    def reset(self) -> None:
        """Reset agent state for new conversation."""
        self.messages = []
        self._cancelled = False

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    async def _call_api(self, messages: list[dict], use_tools: bool = True) -> dict:
        """
        Call OpenRouter API.

        Args:
            messages: Chat messages
            use_tools: Whether to include tools

        Returns:
            API response
        """
        payload = {
            "model": self.model,
            "messages": messages,
        }

        if use_tools:
            payload["tools"] = self.TOOLS
            payload["tool_choice"] = "auto"
            # Force OpenRouter to only use providers that support tool calling
            # and enable fallback to other providers if one fails
            payload["provider"] = {
                "require_parameters": True,
                "allow_fallbacks": True
            }

        try:
            response = await self.http_client.post(
                "/chat/completions",
                json=payload
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"API error: {e.response.status_code} - {e.response.text}")
            raise RuntimeError(f"API error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Request failed: {e}")
            raise

    async def _execute_tool_call(self, tool_call: dict) -> str:
        """
        Execute a tool call and return result.

        Args:
            tool_call: Tool call from API response

        Returns:
            Tool execution result
        """
        function = tool_call.get("function", {})
        name = function.get("name", "")
        arguments = function.get("arguments", "{}")

        try:
            args = json.loads(arguments)
        except json.JSONDecodeError:
            return f"Error: Invalid arguments: {arguments}"

        if name == "execute_command":
            command = args.get("command", "")
            if not command:
                return "Error: No command provided"

            logger.info(f"Executing command: {command}")

            # Notify about command execution
            if self.deps.on_thinking:
                self.deps.on_thinking(f"Executando: {command}")

            try:
                output = await self.deps.execute_command(command)

                # Notify about command result
                if self.deps.on_command_executed:
                    self.deps.on_command_executed(command, output)

                return output if output else "(comando executado sem saída)"
            except asyncio.TimeoutError:
                return "Error: Command timed out after 30 seconds"
            except Exception as e:
                return f"Error executing command: {str(e)}"

        return f"Error: Unknown tool: {name}"

    async def chat(self, user_message: str) -> str:
        """
        Send a message to the agent and get a response.
        The agent may execute multiple commands before responding.

        Args:
            user_message: User's message/request

        Returns:
            Agent's final response
        """
        self._cancelled = False

        if not self.api_key:
            return "Erro: API key não configurada. Verifique o arquivo settings.json"

        # Add system message if first message
        if not self.messages:
            self.messages.append({
                "role": "system",
                "content": self._get_system_prompt()
            })

        # Add user message
        self.messages.append({
            "role": "user",
            "content": user_message
        })

        max_iterations = 10  # Prevent infinite loops
        iteration = 0

        while iteration < max_iterations:
            if self._cancelled:
                return "Operação cancelada pelo usuário."

            iteration += 1
            logger.info(f"Agent iteration {iteration}")

            try:
                response = await self._call_api(self.messages)
            except Exception as e:
                return f"Erro na comunicação com a IA: {str(e)}"

            if self._cancelled:
                return "Operação cancelada pelo usuário."

            choices = response.get("choices", [])
            if not choices:
                return "Erro: Resposta vazia da IA"

            message = choices[0].get("message", {})

            # Check for tool calls
            tool_calls = message.get("tool_calls", [])

            if tool_calls:
                # Add assistant message with tool calls
                self.messages.append({
                    "role": "assistant",
                    "content": message.get("content", ""),
                    "tool_calls": tool_calls
                })

                # Execute each tool call
                for tool_call in tool_calls:
                    if self._cancelled:
                        return "Operação cancelada pelo usuário."

                    tool_id = tool_call.get("id", "")
                    result = await self._execute_tool_call(tool_call)

                    # Add tool result
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": result
                    })

                # Continue loop to get next response
                continue

            # No tool calls - this is the final response
            content = message.get("content", "")

            # Add assistant response to history
            self.messages.append({
                "role": "assistant",
                "content": content
            })

            return content

        return "Erro: Número máximo de iterações atingido"


# Convenience function to create agent
def create_agent(
    execute_command: Callable[[str], Any],
    on_command_executed: Optional[Callable[[str, str], None]] = None,
    on_thinking: Optional[Callable[[str], None]] = None,
    device_type: Optional[str] = None
) -> SSHAgent:
    """
    Create an SSH Agent instance.

    Args:
        execute_command: Async function to execute SSH commands
        on_command_executed: Optional callback when command is executed
        on_thinking: Optional callback for agent thinking/status
        device_type: Type of device being connected (Linux, MikroTik, etc.)

    Returns:
        Configured SSHAgent instance
    """
    deps = AgentDeps(
        execute_command=execute_command,
        on_command_executed=on_command_executed,
        on_thinking=on_thinking,
        device_type=device_type
    )
    return SSHAgent(deps)
