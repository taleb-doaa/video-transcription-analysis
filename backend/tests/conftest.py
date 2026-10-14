from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app


@pytest.fixture
def mock_db():
    """
    A MagicMock standing in for a SQLAlchemy Session.
    Tests configure db.get / db.query(...).filter(...)... return
    values as needed; no real database connection is made.
    """
    return MagicMock()


@pytest.fixture
def client(mock_db):
    """
    FastAPI TestClient with the real Postgres session replaced by
    mock_db, so route tests never touch an actual database.
    """

    def _override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()