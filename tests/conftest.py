"""pytest 公共配置：在导入应用之前指向临时数据目录。"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("SEMIREL_DATA_DIR", tempfile.mkdtemp(prefix="semirel-test-"))
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only-32bytes")
os.environ.setdefault("FREE_DAILY_QUOTA", "20")
os.environ.setdefault("ANONYMOUS_DAILY_QUOTA", "5")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def auth_headers(client):
    response = client.post(
        "/api/auth/register",
        json={"email": "tester@example.com", "username": "测试员", "password": "reliability-2026"},
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
