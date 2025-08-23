import asyncio
import logging

import nest_asyncio
import streamlit as st
from agent import Assistant
from ui import (
    initialize_session_state,
    setup_page,
    sidebar_cleanup,
    sidebar_tips,
)
from utils import (
    MCP_CLIENT_CONFIG_FILE_PATH,
    SYSTEM_PROMPT_PATH,
    cleanup_mcp_client,
    get_system_prompt,
    load_config_from_json,
)

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

logger.info("Starting Chatbot...")

# Apply nest_asyncio: Allow nested calls within an already running event loop
nest_asyncio.apply()

# Create and reuse global event loop (create once and continue using)
if "event_loop" not in st.session_state:
    loop = asyncio.new_event_loop()
    st.session_state.event_loop = loop
    asyncio.set_event_loop(loop)


@st.cache_data
def load_system_prompt():
    """Load the system prompt from its configuration file."""
    return get_system_prompt(SYSTEM_PROMPT_PATH)


async def cleanup_resources():
    """
    Clean up resources when the application is shutting down or restarting.

    This function handles proper cleanup of:
    - MCP client connections
    - Event loops
    - Any other async resources
    """
    try:
        # Clean up MCP client
        if "assistant" in st.session_state and st.session_state.assistant:
            await cleanup_mcp_client(st.session_state.assistant)

        # if "event_loop" in st.session_state:
        #     loop = st.session_state.event_loop
        #     if not loop.is_running():
        #         await cleanup_event_loop(loop)

        # Clear session state resources
        resources_to_clear = [
            "assistant",
            "mcp_client",
            "messages",
            "thread_id",
        ]
        for resource in resources_to_clear:
            if resource in st.session_state:
                del st.session_state[resource]

        logger.info("Resource cleanup completed")

    except Exception:
        # Log the error but don't attempt recursive cleanup
        logger.exception("Error during resource cleanup:")
        # Still try to clear session state even if cleanup fails
        try:
            for key in list(st.session_state.keys()):
                del st.session_state[key]
        except KeyError:
            logger.exception("KeyError during resource cleanup:")


def initialize_assistant():
    """Initialize the Assistant with configuration."""
    if "assistant" not in st.session_state:
        try:
            logger.debug("Loading MCP client configuration...")
            mcp_client_config = load_config_from_json(MCP_CLIENT_CONFIG_FILE_PATH)
            logger.debug(f"Loaded MCP client config: {mcp_client_config}")

            logger.debug("Loading system prompt...")
            system_prompt = load_system_prompt()
            logger.debug("Loaded system prompt")

            logger.debug("Creating Assistant instance...")
            st.session_state.assistant = Assistant()

            logger.debug("Initializing assistant with MCP client...")
            loop = st.session_state.event_loop
            loop.run_until_complete(
                st.session_state.assistant.initialize(
                    mcp_client_config,
                    system_prompt,
                ),
            )
            logger.debug("Assistant initialization completed successfully")
        except Exception as exc:
            logger.exception("Failed to initialize assistant:")
            st.error(f"Failed to initialize assistant: {exc}")
            # Don't call cleanup recursively, just clear session state
            try:
                for key in ["assistant", "event_loop", "mcp_client"]:
                    if key in st.session_state:
                        del st.session_state[key]
            except KeyError as exc:
                logger.exception("KeyError during assistant initialization cleanup:")
            st.stop()


def main():
    """Main application function."""
    try:
        # Initialize session state and UI
        initialize_session_state()
        setup_page()

        # Initialize messages in session state if not present
        if "messages" not in st.session_state:
            st.session_state.messages = []

        # Initialize assistant
        initialize_assistant()

        # Render sidebar components
        sidebar_cleanup()
        sidebar_tips()

        # Display chat history
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        # Main chat interface
        if prompt := st.chat_input("What would you like to know?"):
            # Add user message to chat history
            st.session_state.messages.append({"role": "user", "content": prompt})

            # Display user message
            with st.chat_message("user"):
                st.markdown(prompt)

            # Generate and display assistant response
            with st.chat_message("assistant"), st.spinner("Thinking..."):
                try:
                    loop = st.session_state.event_loop

                    # Use the assistant's invoke method for better error handling
                    response = loop.run_until_complete(
                        st.session_state.assistant.invoke(
                            st.session_state.messages,
                            {"configurable": {"thread_id": st.session_state.thread_id}},
                        ),
                    )

                    # Extract the AIMessage content from the response
                    if (
                        isinstance(response, dict)
                        and "messages" in response
                        and response["messages"]
                    ):
                        # The AIMessage is the last message in the list
                        output = response["messages"][-1].content
                    elif isinstance(response, dict) and "output" in response:
                        output = response["output"]
                    else:
                        output = str(response)

                except Exception as e:
                    logger.exception("Error during agent invocation")
                    output = (
                        f"I encountered an error while processing your request: {e!s}"
                    )

                # Display the response
                logger.debug(output)
                st.markdown(output)

                # Add assistant response to chat history
                st.session_state.messages.append(
                    {"role": "assistant", "content": output},
                )

    except Exception as exc:
        st.error(f"Application error: {exc}")
        logger.exception("Unhandled application error:")
        # Don't call cleanup recursively, just clear session state
        try:
            for key in list(st.session_state.keys()):
                del st.session_state[key]
        except KeyError:
            logger.exception("KeyError during session state cleanup:")
        st.stop()


if __name__ == "__main__":
    main()
