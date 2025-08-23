import logging
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from utils import GOOGLE_API_KEY, LANGCHAIN_MODEL

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class Assistant:
    """
    Main assistant class for observability and monitoring analysis.

    This class manages the integration between MCP servers and LangGraph agents
    to provide observability and monitoring capabilities.

    Attributes:
        memory: Memory saver for conversation persistence
        agent: The LangGraph ReAct agent
        mcp_client: Multi-server MCP client for tool access
        system_prompt: The system prompt for the agent

    """

    def __init__(self) -> None:
        """Initialize the Assistant with default values."""
        self.memory: MemorySaver = MemorySaver()
        self.agent: Any | None
        self.mcp_client: MultiServerMCPClient | None
        self.system_prompt: str | None = None
        self._initialized: bool = False

    async def initialize(
        self,
        mcp_client_config: dict[str, Any],
        system_prompt: str,
    ) -> None:
        """
        Initialize the assistant with MCP client and a system prompt.

        Args:
            mcp_client_config: Configuration for MCP client connections
            system_prompt: The system prompt for the agent

        """
        if self._initialized:
            logger.warning("Assistant already initialized, skipping re-initialization")
            return

        try:
            logger.info("Starting Assistant initialization")
            self._validate_inputs(mcp_client_config, system_prompt)
            self.system_prompt = system_prompt
            logger.info("Stored system prompt")

            await self._setup_mcp_client(mcp_client_config)
            tools = await self._retrieve_tools()
            self._log_tools(tools)
            model = LANGCHAIN_MODEL
            self._validate_model_config(model)
            self._create_agent(model, tools, self.system_prompt)
            self._initialized = True
            logger.info("Assistant initialization completed successfully")
        except Exception:
            logger.exception("Unexpected error during initialization:")

    def _validate_inputs(
        self,
        mcp_client_config: dict[str, Any],
        system_prompt: str,
    ) -> None:
        if not mcp_client_config:
            msg = "MCP client configuration cannot be empty"
            raise ValueError(msg)
        if not system_prompt:
            msg = "System prompt cannot be empty"
            raise ValueError(msg)
        logger.debug(f"MCP client config: {mcp_client_config}")

    async def _setup_mcp_client(self, mcp_client_config: dict[str, Any]) -> None:
        try:
            self.mcp_client = MultiServerMCPClient(mcp_client_config)
            logger.info("MCP client initialized successfully")
        except Exception:
            logger.exception("Failed to initialize MCP client:")

    async def _retrieve_tools(self) -> list[Any]:
        logger.info("Retrieving tools from MCP servers...")
        try:
            tools = await self.mcp_client.get_tools()
            if not tools:
                logger.warning("No tools retrieved from MCP servers")
                tools = []
            logger.info(f"Retrieved {len(tools)} tools from MCP servers")
        except Exception:
            logger.exception("Failed to retrieve tools from MCP servers:")
        else:
            return tools

    def _log_tools(self, tools: list[Any]) -> None:
        for i, tool in enumerate(tools):
            logger.debug(f"Tool {i + 1}: {tool.name}")
            logger.debug(f"  Description: {tool.description}")
            if hasattr(tool, "args_schema") and tool.args_schema:
                logger.debug(f"  Args schema: {tool.args_schema}")

    def _validate_model_config(self, model: str) -> None:
        if not GOOGLE_API_KEY and "google" in model:
            logger.warning(
                "GOOGLE_API_KEY not found in environment variables. "
                "This may cause authentication issues.",
            )
        logger.info(f"Creating LangGraph agent with model: {model}")

    def _create_agent(self, model: str, tools: list[Any], system_prompt: str) -> None:
        try:
            self.agent = create_react_agent(
                model=model,
                tools=tools,
                prompt=system_prompt,
                checkpointer=self.memory,
            )
            logger.info("LangGraph agent created successfully")
        except Exception:
            logger.exception("Failed to create LangGraph agent:")

    async def cleanup(self) -> None:
        """
        Clean up resources and connections.

        This method should be called when shutting down the assistant
        to ensure proper cleanup of MCP client connections and other resources.
        """
        logger.info("Starting Assistant cleanup")

        try:
            # Clean up MCP client
            if self.mcp_client:
                try:
                    # Attempt to close MCP client connections
                    if hasattr(self.mcp_client, "close"):
                        await self.mcp_client.close()
                    elif hasattr(self.mcp_client, "__aexit__"):
                        await self.mcp_client.__aexit__(None, None, None)
                    logger.info("MCP client connections closed")
                except Exception:
                    logger.exception("Error closing MCP client:")
                finally:
                    self.mcp_client = None

            # Clear agent references
            self.agent = None

            # Clear other data
            self.system_prompt = None
            self._initialized = False

            logger.info("Assistant cleanup completed")

        except Exception:
            logger.exception("Error during assistant cleanup:")
            # Still try to clear references even if cleanup fails
            self.mcp_client = None
            self.agent = None
            self.system_prompt = None
            self._initialized = False

    @property
    def is_initialized(self) -> bool:
        """
        Check if the assistant is properly initialized.

        Returns:
            bool: True if initialized, False otherwise

        """
        return self._initialized

    async def invoke(
        self,
        messages: list[dict[str, Any]],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Invoke the agent with the given input.

        Args:
            messages: List of message dictionaries containing 'role' and 'content'
            config: Configuration dictionary for the agent invocation

        Returns:
            Dictionary containing the agent's response

        Raises:
            RuntimeError: If assistant is not initialized
            ValueError: If input data is invalid

        """
        if not self._initialized:
            msg = "Assistant not initialized. Call initialize() first."
            raise RuntimeError(msg)

        if not self.agent:
            msg = "Agent not available"
            raise RuntimeError(msg)

        try:
            return await self.agent.ainvoke(
                {"messages": messages},
                config,
            )
        except Exception:
            logger.exception("Error during agent invocation:")
            raise

    def get_available_tools(self) -> list[str]:
        """
        Get list of available tool names.

        Returns:
            list of tool names available to the agent

        """
        if not self._initialized or not self.agent:
            return []

        try:
            tools = self.agent.tools
            return [tool.name for tool in tools] if tools else []
        except Exception:
            logger.exception("Error getting available tools:")
            return []
