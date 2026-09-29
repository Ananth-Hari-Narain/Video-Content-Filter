from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.api.routes import (
    get_storage,
    get_job_cache,
    get_job_queue,
    get_job_repository,
)
from backend.api.services.storage import R2Storage
from backend.api.services.job_cache import JobCache
from backend.api.services.job_queue import JobQueue
from backend.api.services.job_repository import JobRepository


@pytest.fixture
def mock_storage() -> MagicMock:
    return MagicMock(spec=R2Storage)


@pytest.fixture
def mock_job_cache() -> MagicMock:
    return MagicMock(spec=JobCache)


@pytest.fixture
def mock_job_queue() -> MagicMock:
    return MagicMock(spec=JobQueue)


@pytest.fixture
def mock_job_repository() -> MagicMock:
    return MagicMock(spec=JobRepository)


@pytest.fixture
def client(mock_storage, mock_job_cache, mock_job_queue, mock_job_repository) -> TestClient:
    app.dependency_overrides[get_storage] = lambda: mock_storage
    app.dependency_overrides[get_job_cache] = lambda: mock_job_cache
    app.dependency_overrides[get_job_queue] = lambda: mock_job_queue
    app.dependency_overrides[get_job_repository] = lambda: mock_job_repository

    yield TestClient(app)

    app.dependency_overrides.clear()
