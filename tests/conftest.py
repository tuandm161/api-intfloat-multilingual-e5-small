from collections.abc import Iterator
import os

import pytest
from fastapi.testclient import TestClient

os.environ["EMBEDDING_PROVIDER"] = "mock_deterministic"
os.environ["GENERATION_API_KEY"] = ""

from app.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        reset_response = test_client.post("/demo/reset")
        assert reset_response.status_code == 200
        yield test_client
