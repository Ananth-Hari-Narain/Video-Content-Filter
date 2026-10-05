from botocore.exceptions import ConnectionError as BotoConnectionError
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pika.exceptions import AMQPError
from psycopg import OperationalError as PostgresOperationalError
from redis.exceptions import RedisError
import logging

from backend.api.routes import router

app = FastAPI(title="Video Content Filter API")

# Connectivity failures for each backing service. These can surface either from inside a route or while 
# FastAPI is resolving a dependency, so a global handler catches both.
SERVICE_NAMES = {
    BotoConnectionError: "Object storage (S3/R2)",
    RedisError: "Redis",
    AMQPError: "RabbitMQ",
    PostgresOperationalError: "Postgres",
}
SERVICE_UNAVAILABLE_ERRORS = tuple(SERVICE_NAMES)
logger = logging.getLogger(__name__)


def handle_service_unavailable(request: Request, exc: Exception) -> JSONResponse:
    service = next(name for t, name in SERVICE_NAMES.items() if isinstance(exc, t))
    logger.error("%s unavailable on %s %s", service, request.method, request.url.path, exc_info=exc)
    return JSONResponse(status_code=503, content={"detail": f"{service} is temporarily unavailable."})


for _exc_type in SERVICE_UNAVAILABLE_ERRORS:
    app.add_exception_handler(_exc_type, handle_service_unavailable)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
