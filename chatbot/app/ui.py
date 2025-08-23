import uuid

import streamlit as st


def setup_page():
    """Configure the Streamlit page settings and title."""
    st.set_page_config(
        page_title="Insight Bot",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title("Insight Bot")


def sidebar_cleanup():
    button_key = "reset_cleanup_resources_button"
    if st.sidebar.button(
        "Reset & Cleanup Resources",
        help="Clean up all resources and restart the assistant",
        use_container_width=True,
        key=button_key,
    ):
        st.session_state.session_initialized = False
        st.session_state.messages = []
        del st.session_state["thread_id"]
        st.success("Resources cleaned up successfully!")
        # Automatically rerun the app to reinitialize everything
        st.rerun()


def sidebar_tips():
    """Display a sidebar section with tips and example queries."""
    st.sidebar.header("Tips")
    # Add helpful tips section
    st.sidebar.markdown(
        """
- **Jaeger**: "What are the dependencies for the 'user-service' over the last 2 hours?"
- **Loki**: "Show all error logs from the user-service in the last 2 hours."
- **Prometheus**: "List all available metrics."
""",
    )


def initialize_session_state():
    """Initialize Streamlit session state variables."""
    if "session_initialized" not in st.session_state:
        st.session_state.session_initialized = False
        st.session_state.messages = []

    if "thread_id" not in st.session_state:
        st.session_state.thread_id = str(uuid.uuid4())
