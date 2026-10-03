"""Fixtures for integration tests.

These run the real R2Storage / JobCache / JobQueue / JobRepository classes against real
services started from docker-compose.test.yml (Postgres, Redis, RabbitMQ, and S3Mock standing
in for Cloudflare R2). "Outage" fixtures point a client at a dead port instead of stopping a
container, which is fast and doesn't disturb other tests.
"""

import subprocess
import time
from pathlib import Path
from typing import LiteralString, cast

import boto3
import pika
import psycopg
import pytest
import redis
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

from backend.main import app
from backend.api.dependencies import (
    get_settings,
    get_r2_client,
    get_redis_client,
    get_rabbitmq_channel,
    get_db_connection,
)
from backend.api.services.storage import R2Storage
from backend.api.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[4]
COMPOSE_FILE = REPO_ROOT / "docker-compose.test.yml"
SCHEMA_FILE = Path(__file__).parent / "schema.sql"

S3_ENDPOINT = "http://localhost:59000"
REDIS_URL = "redis://localhost:56379/0"
RABBITMQ_URL = "amqp://guest:guest@localhost:55672/%2F"
DATABASE_URL = "postgresql://vcf:vcf@localhost:55432/vcf"
DEAD_PORT = 1  # nothing listens here, so connections are refused immediately

TEST_SETTINGS = Settings(
    cloudflare_account_id="test",
    r2_access_key_id="minioadmin",
    r2_secret_access_key="minioadmin",
    upstash_redis_job_store_url=REDIS_URL,
    rabbitmq_url=RABBITMQ_URL,
    database_url=DATABASE_URL,
    bucket_name="vcf-test-bucket",
    job_queue_name="jobs_queue_test",
)

# Needed so test does not hang for default 60s+ for retry/backoff.
# This is testing the app gracefully handles failure to reach s3 / r2 bucket.
_FAST_FAIL_S3_CONFIG = Config(
    signature_version="s3v4",
    s3={"addressing_style": "path"},
    connect_timeout=1,
    retries={"max_attempts": 1},
    # Recent boto3 adds CRC32 checksums by default, which S3-compatible backends (S3Mock, R2) mishandle on multipart uploads
    request_checksum_calculation="when_required",
    response_checksum_validation="when_required",
)


def _make_s3_client(endpoint_url: str = S3_ENDPOINT):
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id="minioadmin",
        aws_secret_access_key="minioadmin",
        region_name="auto",
        config=_FAST_FAIL_S3_CONFIG,
    )


def _wait_until(check, name: str, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            check()
            return
        except Exception as e:  # noqa: BLE001 - any failure just means "not ready yet"
            last_error = e
            time.sleep(0.5)
    raise RuntimeError(f"{name} did not become ready within {timeout}s: {last_error!r}")


def _check_redis() -> None:
    redis.Redis.from_url(REDIS_URL).ping()


def _check_rabbitmq() -> None:
    pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL)).close()


def _check_postgres() -> None:
    psycopg.connect(DATABASE_URL, connect_timeout=2).close()


def _check_s3mock() -> None:
    _make_s3_client().list_buckets()


@pytest.fixture(scope="session", autouse=True)
def backing_services():
    """Start (if needed) and wait for the test services, then apply the schema and create the bucket."""
    subprocess.run(["docker", "compose", "-f", str(COMPOSE_FILE), "down", "-v"], capture_output=True)
    result = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"Could not start test services with docker compose:\n{result.stderr or result.stdout}")
    _wait_until(_check_redis, "redis")
    _wait_until(_check_rabbitmq, "rabbitmq")
    _wait_until(_check_postgres, "postgres")
    _wait_until(_check_s3mock, "s3mock")

    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(cast(LiteralString, SCHEMA_FILE.read_text()))

    s3 = _make_s3_client()
    try:
        s3.create_bucket(Bucket=TEST_SETTINGS.bucket_name)
    except ClientError as e:
        if e.response["Error"]["Code"] not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            raise
    yield


# ---------------------------------------------------------------------------
# Healthy clients (also used by tests to seed and inspect state directly)
# ---------------------------------------------------------------------------

@pytest.fixture
def s3_client(backing_services):
    return _make_s3_client()


@pytest.fixture
def storage(s3_client) -> R2Storage:
    return R2Storage(client=s3_client, bucket_name=TEST_SETTINGS.bucket_name)


@pytest.fixture
def redis_client(backing_services):
    client = redis.Redis.from_url(REDIS_URL)
    client.flushdb()  # dedicated test container, so this is safe
    yield client
    client.close()


@pytest.fixture
def rabbit_channel(backing_services):
    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    channel = connection.channel()
    channel.queue_declare(queue=TEST_SETTINGS.job_queue_name, durable=True)
    channel.queue_purge(queue=TEST_SETTINGS.job_queue_name)
    yield channel
    if connection.is_open:
        connection.close()


@pytest.fixture
def db_conn(backing_services):
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE TABLE job")
        yield conn


# ---------------------------------------------------------------------------
# Outage simulations
# ---------------------------------------------------------------------------

@pytest.fixture
def dead_redis_client():
    return redis.Redis(host="localhost", port=DEAD_PORT, socket_connect_timeout=1)


@pytest.fixture
def dead_s3_client():
    return _make_s3_client(endpoint_url=f"http://localhost:{DEAD_PORT}")


@pytest.fixture
def dead_rabbit_channel(backing_services):
    """A channel whose connection has been closed, as if the broker went away."""
    connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    channel = connection.channel()
    connection.close()
    return channel


@pytest.fixture
def dead_database_url() -> str:
    return f"postgresql://vcf:vcf@localhost:{DEAD_PORT}/vcf?connect_timeout=1"


# ---------------------------------------------------------------------------
# App wiring
# ---------------------------------------------------------------------------

@pytest.fixture
def make_client(s3_client, redis_client, rabbit_channel, db_conn):
    """Build a TestClient wired to the real services, optionally swapping one for a broken stand-in.

    Overrides the low-level client factories (not the service wrappers) so the real
    get_storage / get_job_cache / get_job_queue / get_job_repository wiring is exercised.
    """

    def _make(*, s3=None, redis_=None, channel=None, database_url=None) -> TestClient:
        s3_ = s3 if s3 is not None else s3_client
        redis__ = redis_ if redis_ is not None else redis_client
        channel_ = channel if channel is not None else rabbit_channel
        url = database_url if database_url is not None else DATABASE_URL

        def db_dependency():
            with psycopg.connect(url) as conn:
                yield conn

        app.dependency_overrides[get_settings] = lambda: TEST_SETTINGS
        app.dependency_overrides[get_r2_client] = lambda: s3_
        app.dependency_overrides[get_redis_client] = lambda: redis__
        app.dependency_overrides[get_rabbitmq_channel] = lambda: channel_
        app.dependency_overrides[get_db_connection] = db_dependency
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()
