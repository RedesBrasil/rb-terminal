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

from core.data_manager import get_data_manager

logger = logging.getLogger(__name__)


@dataclass
class UsageStats:
    """Token usage and cost statistics."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0

    def add(self, prompt: int, completion: int, cost: float = 0.0) -> None:
        """Add usage from a single API call."""
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens += prompt + completion
        self.total_cost += cost

    def reset(self) -> None:
        """Reset all statistics."""
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.total_cost = 0.0


@dataclass
class AgentDeps:
    """Dependencies for the AI agent."""
    execute_command: Callable[[str], Any]  # Async function to execute SSH commands
    on_command_executed: Optional[Callable[[str, str], None]] = None  # Callback(cmd, output)
    on_thinking: Optional[Callable[[str], None]] = None  # Callback for AI thinking
    on_usage_update: Optional[Callable[[UsageStats], None]] = None  # Callback for usage updates
    # Host connection info
    host_name: Optional[str] = None  # Display name of the host
    host_address: Optional[str] = None  # IP address or hostname
    host_port: Optional[int] = None  # SSH port
    username: Optional[str] = None  # SSH username
    # Device metadata
    device_type: Optional[str] = None  # Type of device (Roteador, Switch, etc.)
    manufacturer: Optional[str] = None
    os_version: Optional[str] = None
    functions: Optional[list] = None
    groups: Optional[list] = None
    tags: Optional[list] = None
    notes: Optional[str] = None


class SSHAgent:
    """
    AI Agent that can execute SSH commands.
    Uses OpenRouter API with function calling.
    """

    DEFAULT_SYSTEM_PROMPT = """Você é um especialista em administração de sistemas, redes e servidores.

Seu objetivo é ajudar o usuário a diagnosticar e resolver problemas executando comandos SSH.

Regras importantes:
1. Sempre leia a saída do comando antes de decidir o próximo passo
2. Seja conciso nas respostas
3. Explique o que você encontrou após cada comando
4. Se algo der errado, explique o problema e sugira soluções
5. Para comandos potencialmente perigosos (rm, format, reset, reboot), avise o usuário primeiro"""

    # This is always injected at the end of the prompt (hidden from user)
    TOOL_INSTRUCTION = "\n\nVocê tem acesso à ferramenta execute_command para rodar comandos no terminal SSH conectado."

    DEFAULT_MAX_ITERATIONS = 10

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
        self._data_manager = get_data_manager()
        self.messages: list[dict] = []
        self._cancelled = False
        self._http_client: Optional[httpx.AsyncClient] = None
        self._cached_api_key: Optional[str] = None  # Track API key for client invalidation
        self.usage_stats = UsageStats()

    @property
    def api_key(self) -> str:
        """Get current API key from settings (dynamic)."""
        return self._data_manager.get_api_key()

    @property
    def model(self) -> str:
        """Get current model from settings (dynamic)."""
        return self._data_manager.get_model()

    def _get_system_prompt(self) -> str:
        """
        Get the system prompt with device-specific context.

        Returns:
            System prompt string with host information automatically injected
        """
        # Use custom prompt if configured, otherwise use default
        custom_prompt = self._data_manager.get_ai_system_prompt()
        prompt = custom_prompt if custom_prompt else self.DEFAULT_SYSTEM_PROMPT

        # Add host connection info
        connection_info = []

        if self.deps.host_name:
            connection_info.append(f"Nome: {self.deps.host_name}")

        if self.deps.host_address:
            connection_info.append(f"Endereço: {self.deps.host_address}")

        if self.deps.host_port:
            connection_info.append(f"Porta: {self.deps.host_port}")

        if self.deps.username:
            connection_info.append(f"Usuário: {self.deps.username}")

        if connection_info:
            prompt += "\n\nInformações de conexão:\n- " + "\n- ".join(connection_info)

        # Add additional host metadata context
        metadata_parts = []

        if self.deps.device_type:
            metadata_parts.append(f"Tipo: {self.deps.device_type}")

        if self.deps.manufacturer:
            metadata_parts.append(f"Fabricante: {self.deps.manufacturer}")

        if self.deps.os_version:
            metadata_parts.append(f"Sistema/Versão: {self.deps.os_version}")

        if self.deps.functions:
            metadata_parts.append(f"Funções: {', '.join(self.deps.functions)}")

        if self.deps.groups:
            metadata_parts.append(f"Grupos: {', '.join(self.deps.groups)}")

        if self.deps.tags:
            metadata_parts.append(f"Tags: {', '.join(self.deps.tags)}")

        if self.deps.notes:
            metadata_parts.append(f"Observações: {self.deps.notes}")

        if metadata_parts:
            prompt += "\n\nMetadados do dispositivo:\n- " + "\n- ".join(metadata_parts)

        # Always add tool instruction at the end (hidden from user's editable prompt)
        prompt += self.TOOL_INSTRUCTION

        return prompt

    @property
    def http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client. Recreates if API key changed."""
        current_api_key = self.api_key

        # Recreate client if API key changed or client doesn't exist
        if (self._http_client is None or
            self._http_client.is_closed or
            self._cached_api_key != current_api_key):

            # Close existing client if open
            if self._http_client and not self._http_client.is_closed:
                # Schedule close in background to avoid blocking
                asyncio.create_task(self._http_client.aclose())

            self._cached_api_key = current_api_key
            self._http_client = httpx.AsyncClient(
                base_url="https://openrouter.ai/api/v1",
                headers={
                    "Authorization": f"Bearer {current_api_key}",
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
        self.usage_stats.reset()

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    async def get_account_balance(self) -> Optional[float]:
        """
        Fetch account balance/credits from OpenRouter.

        Returns:
            Balance in USD, or None if failed
        """
        try:
            response = await self.http_client.get("/credits")
            if response.status_code == 200:
                data = response.json().get("data", {})
                total_credits = data.get("total_credits", 0)
                total_usage = data.get("total_usage", 0)
                # Balance = credits purchased - credits used
                return float(total_credits) - float(total_usage)
        except Exception as e:
            logger.debug(f"Failed to fetch account balance: {e}")
        return None

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
            result = response.json()

            # Process usage stats
            await self._process_usage(result)

            return result
        except httpx.HTTPStatusError as e:
            logger.error(f"API error: {e.response.status_code} - {e.response.text}")
            raise RuntimeError(f"API error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Request failed: {e}")
            raise

    async def _process_usage(self, response: dict) -> None:
        """
        Process usage information from API response.

        Args:
            response: API response containing usage data
        """
        usage = response.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        # Update stats with tokens first (cost will be fetched async)
        self.usage_stats.add(prompt_tokens, completion_tokens, 0.0)

        # Notify callback immediately with token counts
        if self.deps.on_usage_update:
            self.deps.on_usage_update(self.usage_stats)

        # Fetch cost asynchronously in background
        gen_id = response.get("id", "")
        if gen_id:
            asyncio.create_task(self._fetch_and_update_cost(gen_id))

    async def _fetch_and_update_cost(self, gen_id: str) -> None:
        """
        Fetch cost in background and update stats when available.

        Args:
            gen_id: Generation ID from the API response
        """
        # Wait a bit for OpenRouter to index the generation
        await asyncio.sleep(1.0)

        cost = await self._fetch_generation_cost(gen_id)
        if cost > 0:
            # Add only the cost (tokens already counted)
            self.usage_stats.total_cost += cost

            # Notify callback with updated cost
            if self.deps.on_usage_update:
                self.deps.on_usage_update(self.usage_stats)

    async def _fetch_generation_cost(self, gen_id: str, retries: int = 3) -> float:
        """
        Fetch the real cost from OpenRouter generation endpoint.

        Args:
            gen_id: Generation ID from the API response
            retries: Number of retry attempts (generation may not be available immediately)

        Returns:
            Cost in USD
        """
        for attempt in range(retries):
            try:
                # Small delay before fetching - generation needs time to be indexed
                if attempt > 0:
                    await asyncio.sleep(0.5 * attempt)

                response = await self.http_client.get(
                    f"/generation?id={gen_id}"
                )
                if response.status_code == 200:
                    data = response.json().get("data", {})
                    # Cost is in USD
                    cost = data.get("total_cost", 0.0)
                    if cost > 0:
                        return cost
                elif response.status_code == 404 and attempt < retries - 1:
                    # Generation not yet available, retry
                    continue
            except Exception as e:
                logger.debug(f"Failed to fetch generation cost (attempt {attempt + 1}): {e}")
        return 0.0

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

    def _get_max_iterations(self) -> int:
        """Return user-configured iteration limit."""
        try:
            return self._data_manager.get_max_iterations()
        except Exception:
            return self.DEFAULT_MAX_ITERATIONS

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

        max_iterations = self._get_max_iterations()
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
    on_usage_update: Optional[Callable[[UsageStats], None]] = None,
    # Host connection info
    host_name: Optional[str] = None,
    host_address: Optional[str] = None,
    host_port: Optional[int] = None,
    username: Optional[str] = None,
    # Device metadata
    device_type: Optional[str] = None,
    manufacturer: Optional[str] = None,
    os_version: Optional[str] = None,
    functions: Optional[list] = None,
    groups: Optional[list] = None,
    tags: Optional[list] = None,
    notes: Optional[str] = None
) -> SSHAgent:
    """
    Create an SSH Agent instance.

    Args:
        execute_command: Async function to execute SSH commands
        on_command_executed: Optional callback when command is executed
        on_thinking: Optional callback for agent thinking/status
        on_usage_update: Optional callback for usage statistics updates
        host_name: Display name of the host
        host_address: IP address or hostname
        host_port: SSH port
        username: SSH username
        device_type: Type of device being connected (Roteador, Switch, etc.)
        manufacturer: Device manufacturer (e.g., Cisco, MikroTik)
        os_version: Operating system and version
        functions: Device functions/roles
        groups: Device groups
        tags: Device tags
        notes: Additional notes about the device

    Returns:
        Configured SSHAgent instance
    """
    deps = AgentDeps(
        execute_command=execute_command,
        on_command_executed=on_command_executed,
        on_thinking=on_thinking,
        on_usage_update=on_usage_update,
        host_name=host_name,
        host_address=host_address,
        host_port=host_port,
        username=username,
        device_type=device_type,
        manufacturer=manufacturer,
        os_version=os_version,
        functions=functions,
        groups=groups,
        tags=tags,
        notes=notes
    )
    return SSHAgent(deps)
