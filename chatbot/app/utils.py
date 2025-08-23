import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Base directory and configuration paths
BASE_DIR = Path(__file__).parent
DOTENV_PATH = BASE_DIR.parent / ".env"
MCP_CLIENT_CONFIG_FILE_PATH = BASE_DIR / "config/mcp_client.json"
SYSTEM_PROMPT_PATH = BASE_DIR / "config/prompts/system.txt"

# Load environment variables
load_dotenv(dotenv_path=DOTENV_PATH)

# Environment configuration with validation
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
LANGCHAIN_MODEL = os.getenv("LANGCHAIN_MODEL", "google_genai:gemini-2.5-flash")


class ConfigurationError(Exception):
    """Raised when configuration loading or validation fails."""


def get_system_prompt(file_path: Path) -> str:
    """
    Get the system prompt from a configuration file.

    Args:
        file_path: Path to the .txt prompt file

    Returns:
        The content of the prompt file

    Raises:
        FileNotFoundError: If the file doesn't exist
        ConfigurationError: If the prompt is empty

    """
    if not file_path.exists():
        msg = f"Prompt file not found: {file_path}"
        raise FileNotFoundError(msg)

    try:
        with file_path.open(encoding="utf-8") as f:
            content = f.read().strip()

        if not content:
            msg = f"Empty prompt file: {file_path}"
            raise ConfigurationError(msg)

        logger.debug(f"Loaded prompt from: {file_path}")
        return content

    except (OSError, UnicodeDecodeError) as e:
        error_msg = f"Failed to read prompt file {file_path}: {e!s}"
        logger.exception(error_msg)
        raise ConfigurationError(error_msg) from e


def load_config_from_json(
    file_path: Path,
) -> dict[str, Any]:
    """
    Load JSON configuration from a file.

    Args:
        file_path: Path to the JSON configuration file

    Returns:
        Dictionary containing the configuration data

    Raises:
        ConfigurationError: If configuration cannot be loaded

    """

    def _raise_config_error(msg: str, cause: Exception | None = None) -> None:
        """Inner function to raise ConfigurationError."""
        if cause:
            raise ConfigurationError(msg) from cause
        raise ConfigurationError(msg)

    if not file_path.exists():
        msg = f"Config file not found: {file_path}"
        _raise_config_error(msg)

    try:
        with file_path.open("r", encoding="utf-8") as f:
            config = json.load(f)

        if not isinstance(config, dict):
            msg = (
                f"Config file {file_path} does not contain a JSON object, "
                f"found: {type(config).__name__}"
            )
            _raise_config_error(msg)

        logger.info(f"Successfully loaded config from {file_path}")

    except json.JSONDecodeError as e:
        msg = f"Invalid JSON in config file {file_path}: {e!s}"
        _raise_config_error(msg, e)

    except ConfigurationError:
        # Re-raise our own errors
        raise

    except (OSError, UnicodeDecodeError) as e:
        # Handle file I/O and encoding errors
        msg = f"Failed to read config file {file_path}: {e!s}"
        _raise_config_error(msg, e)

    else:
        return config


async def cleanup_mcp_client(assistant: Any) -> None:
    """
    Helper to clean up MCP client connections.

    Args:
        assistant: Assistant instance containing MCP client

    Note:
        This function is designed to be fault-tolerant and will not raise exceptions

    """
    if not assistant:
        return

    logger.info("Starting MCP client cleanup")

    try:
        # Use the assistant's cleanup method if available
        if hasattr(assistant, "cleanup"):
            await assistant.cleanup()
            logger.info("Assistant cleanup completed")
        elif hasattr(assistant, "mcp_client") and assistant.mcp_client:
            # Fallback to direct MCP client cleanup
            mcp_client = assistant.mcp_client
            try:
                if hasattr(mcp_client, "close"):
                    await mcp_client.close()
                elif hasattr(mcp_client, "__aexit__"):
                    await mcp_client.__aexit__(None, None, None)
                logger.info("MCP client connections closed successfully")
            except Exception:
                logger.exception("Error closing MCP client:")
            finally:
                assistant.mcp_client = None

    except Exception:
        logger.exception("Unexpected error during MCP client cleanup:")


async def cleanup_event_loop(loop: asyncio.AbstractEventLoop | None) -> None:
    """
    Helper to clean up event loop and pending tasks.

    Args:
        loop: Event loop to clean up

    Note:
        This function is designed to be fault-tolerant and will not raise exceptions

    """
    if not loop or loop.is_closed():
        return

    logger.info("Starting event loop cleanup")

    try:
        # Get all tasks for this specific loop
        all_tasks = asyncio.all_tasks()
        pending_tasks = [
            task for task in all_tasks if not task.done() and task.get_loop() == loop
        ]

        if pending_tasks:
            logger.info(f"Cancelling {len(pending_tasks)} pending tasks")

            # Cancel all pending tasks
            for task in pending_tasks:
                task.cancel()

            # Wait for all tasks to complete cancellation
            await asyncio.gather(*pending_tasks, return_exceptions=True)
            logger.info("All pending tasks cancelled")

        # Close the event loop
        loop.close()
        logger.info("Event loop closed successfully")

    except RuntimeError as e:
        # Handle case where loop is already running
        if "Event loop is running" in str(e):
            logger.warning("Cannot close event loop while it's running")
        else:
            logger.exception("Runtime error during event loop cleanup:")
    except Exception:
        logger.exception("Unexpected error during event loop cleanup:")
