import logging
import os

import httpx
from fastapi import FastAPI, HTTPException, status
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource

app = FastAPI(title="user-service")

# Instrument FastAPI application
FastAPIInstrumentor.instrument_app(app, excluded_urls="/health")
HTTPXClientInstrumentor().instrument()

resource = Resource.create()
log_exporter = OTLPLogExporter()
logger_provider = LoggerProvider(resource=resource)
logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
uvicorn_access_logger = logging.getLogger("uvicorn.access")
uvicorn_access_logger.addHandler(handler)
logging.getLogger().addHandler(handler)
LoggingInstrumentor().instrument(logger_provider=logger_provider)
logger = logging.getLogger(__name__)

# Load profile service base URL from environment
PROFILE_SERVICE_URL = os.getenv("PROFILE_SERVICE_URL", "http://localhost:5001")


@app.get("/health")
async def health_check():
    return {"status": "OK"}


@app.get("/")
async def root():
    logger.info("Processing root request")
    return {"message": "Hello FastAPI"}


@app.get("/users/{user_id}")
async def get_user(user_id: str):
    url = f"{PROFILE_SERVICE_URL}/profiles/{user_id}"
    logger.info("Fetching profile from %s", url)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
    except httpx.RequestError as exc:
        logger.exception("Error connecting to profile-service")
        raise HTTPException(
            status_code=502,
            detail="Profile service unavailable",
        ) from exc

    if response.status_code == status.HTTP_200_OK:
        profile = response.json()
        return {"user_id": user_id, "profile": profile}
    elif response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(status_code=404, detail="User not found")
    else:
        logger.error("Profile service error: %s", response.text)
        raise HTTPException(status_code=502, detail="Profile service error")
