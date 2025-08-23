import logging
import random
import time

from flask import Flask, jsonify
from opentelemetry import trace
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor

app = Flask(__name__)

# Instrument Flask application
FlaskInstrumentor().instrument_app(app)
LoggingInstrumentor().instrument()

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

profiles = {
    "1": {"user_id": 1, "name": "Alice", "email": "alice@example.com"},
    "2": {"user_id": 2, "name": "Bob", "email": "bob@example.com"},
    "3": {"user_id": 3, "name": "Charlie", "email": "charlie@example.com"},
}


@app.route("/", methods=["GET"])
def root():
    return jsonify(message="Hello Flask"), 200


@app.route("/health", methods=["GET"])
def health_check():
    return jsonify(status="ok"), 200


@app.route("/profiles/<user_id>", methods=["GET"])
def get_profile(user_id):
    delay = random.randint(1, 1000)
    error_rate = 0.2

    logger.info(
        "Received request for user_id=%s, delay=%dms, error_rate=%.2f",
        user_id,
        delay,
        error_rate,
    )

    # Simulate delay
    with tracer.start_as_current_span("slow") as span:
        start_time = time.time()
        logger.info("Simulating delay of %dms", delay)
        span.set_attribute("delay", delay)
        time.sleep(delay / 1000)
        duration = time.time() - start_time
        logger.info("Completed slow operation in %.2f seconds", duration)

    # Simulate random failure
    if random.random() < error_rate:
        logger.error("Simulated 500 error for user_id=%s", user_id)
        return jsonify({"error": "Internal Server Error"}), 500

    profile = profiles.get(user_id)
    if profile:
        logger.info("Returning profile for user_id=%s", user_id)
        return jsonify(profile)
    logger.error("User not found: user_id=%s", user_id)
    return jsonify({"error": "User not found"}), 404


if __name__ == "__main__":
    app.run(debug=False)  # Flask debug mode with reloader breaks instrumentation
