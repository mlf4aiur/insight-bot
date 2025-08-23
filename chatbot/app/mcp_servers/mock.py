import logging
import os
import random
from datetime import UTC, datetime
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://localhost:5001")

# Create an MCP server
mcp = FastMCP()


def fetch_user(user_id: int) -> dict[str, Any]:
    """Helper function to fetch a user from the external service."""
    try:
        response = httpx.get(f"{USER_SERVICE_URL}/users/{user_id}")
        if response.status_code == httpx.codes.OK:
            return response.json()
        if response.status_code == httpx.codes.NOT_FOUND:
            logger.error(
                "Unexpected error (Status Code: %s) for user %s",
                response.status_code,
                user_id,
            )
            return {"error": f"User with ID {user_id} not found"}
        else:
            return {"error": "An unexpected error occurred"}
    except httpx.RequestError:
        logger.exception(
            "Unexpected error for URL %s user %d",
            USER_SERVICE_URL,
            user_id,
        )
        return {"error": "Failed to retrieve user due to network issue"}
    except httpx.HTTPStatusError:
        logger.exception("HTTP error for URL %s user %d", USER_SERVICE_URL, user_id)
        return {"error": "HTTP error while fetching user"}
    except Exception:
        logger.exception(
            "Unexpected error for URL %s user %d",
            USER_SERVICE_URL,
            user_id,
        )
        return {"error": "An unexpected error occurred"}


@mcp.tool()
def get_user(user_id: int = 1) -> dict[str, Any]:
    """
    Retrieve a user by ID from the mock user service.

    Args:
        user_id (int): The ID of the user to retrieve. Defaults to 1.

    Returns:
        dict[str, Any]: A simplified user data response with status information.

    """
    logger.info(f"[TOOL CALL] get_user called with user_id={user_id}")
    logger.debug(f"[TOOL CALL] get_user - fetching user from {USER_SERVICE_URL}")

    start_time = datetime.now(UTC)
    result = fetch_user(user_id)
    end_time = datetime.now(UTC)
    duration = (end_time - start_time).total_seconds()

    logger.info(f"[TOOL CALL] get_user completed in {duration:.3f} seconds")
    logger.debug(f"[TOOL CALL] get_user result: {result}")
    return result


@mcp.tool()
def generate_mock_data(count: int = 5) -> dict[str, Any]:
    """
    Generate a specified number of mock user data entries.

    Args:
        count (int): The number of mock users to generate. Defaults to 5.

    Returns:
        dict[str, Any]: A simplified response with user data and summary statistics.

    """
    logger.info(f"[TOOL CALL] generate_mock_data called with count={count}")
    logger.debug(f"[TOOL CALL] generate_mock_data - generating {count} mock users")

    start_time = datetime.now(UTC)
    results = [fetch_user(random.choice([1, 2, 3, 4, 5])) for _ in range(count)]
    end_time = datetime.now(UTC)
    duration = (end_time - start_time).total_seconds()

    # Process results into simplified format
    successful_users = []
    failed_count = 0

    for result in results:
        if "error" not in result:
            successful_users.append(
                {
                    "id": result.get("id"),
                    "name": result.get("name"),
                    "email": result.get("email"),
                    "department": result.get("department"),
                    "role": result.get("role"),
                },
            )
        else:
            failed_count += 1

    logger.info(f"[TOOL CALL] generate_mock_data completed in {duration:.3f} seconds")
    logger.debug(
        f"[TOOL CALL] generate_mock_data result: {len(successful_users)} successful, {failed_count} failed",
    )

    # Return simplified response
    response = {
        "success": failed_count == 0,
        "summary": {
            "requested": count,
            "generated": len(successful_users),
            "failed": failed_count,
            "response_time_ms": round(duration * 1000, 2),
        },
        "users": successful_users,
    }

    if failed_count > 0:
        response["error"] = (
            f"Service unavailable - {failed_count} users failed to generate"
        )
        response["troubleshooting"] = {
            "service_url": USER_SERVICE_URL,
            "suggested_action": "Check the logs for the user and profile services: docker-compose logs user profile",
        }

    return response


# Run the server
if __name__ == "__main__":
    # Run the server
    logger.info(f"Starting mock MCP server with User Service URL: {USER_SERVICE_URL}")
    mcp.run(transport="stdio")
