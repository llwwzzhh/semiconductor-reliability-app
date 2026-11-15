"""接口层测试：认证、配额、计算、导出与历史记录。"""

from __future__ import annotations


MTBF_INPUTS = {
    "data_mode": "test_data",
    "num_failures": 2,
    "total_test_time": 200000,
    "termination": "time_terminated",
    "confidence_level": "90",
    "mission_time": 10000,
}


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_index_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "半导体可靠性计算平台" in response.text


def test_calculator_catalog(client):
    response = client.get("/api/calculators")
    assert response.status_code == 200
    catalog = response.json()["calculators"]
    assert {item["id"] for item in catalog} == {"mtbf", "duane", "sample_size"}
    for item in catalog:
        assert item["input_fields"], f"{item['id']} 缺少表单定义"


def test_calculator_example(client):
    response = client.get("/api/calculators/duane/example")
    assert response.status_code == 200
    assert response.json()["inputs"]["failure_times"]


def test_calculate_anonymous(client):
    response = client.post("/api/calculators/mtbf/calculate", json={"inputs": MTBF_INPUTS})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["result"]["headline"][0]["value"] == 100000
    assert payload["record_id"] is None  # 匿名计算不入库
    quota = payload["quota"]
    assert quota["tier"] == "anonymous"
    assert quota["used"] >= 1


def test_calculate_validation_error(client):
    response = client.post(
        "/api/calculators/mtbf/calculate",
        json={"inputs": {"data_mode": "test_data", "num_failures": -1, "total_test_time": 100}},
    )
    assert response.status_code == 400
    assert "不得小于" in response.json()["detail"]


def test_unknown_calculator(client):
    response = client.post("/api/calculators/nope/calculate", json={"inputs": {}})
    assert response.status_code == 404


def test_register_and_login(client):
    registration = client.post(
        "/api/auth/register",
        json={"email": "second@example.com", "username": "", "password": "semiconductor-2026"},
    )
    assert registration.status_code == 201
    user = registration.json()["user"]
    assert user["username"] == "second"

    login = client.post(
        "/api/auth/login", json={"email": "second@example.com", "password": "semiconductor-2026"}
    )
    assert login.status_code == 200
    assert login.json()["access_token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
    assert me.status_code == 200
    assert me.json()["authenticated"] is True
    assert me.json()["quota"]["daily_limit"] == 20


def test_duplicate_registration_and_bad_password(client, auth_headers):
    duplicate = client.post(
        "/api/auth/register", json={"email": "tester@example.com", "password": "another-pass-2026"}
    )
    assert duplicate.status_code == 409

    wrong = client.post("/api/auth/login", json={"email": "tester@example.com", "password": "wrong-password"})
    assert wrong.status_code == 401


def test_authenticated_calculation_is_saved(client, auth_headers):
    response = client.post(
        "/api/calculators/duane/calculate",
        headers=auth_headers,
        json={"inputs": {"failure_times": "100, 220, 400, 700, 1100", "confidence_level": "90"}},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["record_id"] is not None

    history = client.get("/api/history", headers=auth_headers)
    assert history.status_code == 200
    records = history.json()["records"]
    assert any(record["id"] == payload["record_id"] for record in records)
    assert records[0]["result"]["headline"]


def test_history_requires_login(client):
    assert client.get("/api/history").status_code == 401
    assert client.get("/api/history/export?format=csv").status_code == 401


def test_export_formats(client, auth_headers):
    for fmt, prefix in (("csv", b"\xef\xbb\xbf"), ("xlsx", b"PK"), ("json", b"[")):
        response = client.get(f"/api/history/export?format={fmt}", headers=auth_headers)
        assert response.status_code == 200, response.text
        assert response.content.startswith(prefix), fmt
        assert "attachment" in response.headers["content-disposition"]


def test_export_current_result(client):
    calculation = client.post("/api/calculators/sample_size/calculate", json={"inputs": {"test_type": "success_run", "target_reliability": 0.9}})
    assert calculation.status_code == 200

    for fmt in ("csv", "xlsx", "json"):
        response = client.post(
            "/api/export/calculation",
            json={
                "format": fmt,
                "calculator_id": calculation.json()["calculator_id"],
                "calculator_name": calculation.json()["calculator_name"],
                "inputs": calculation.json()["inputs"],
                "result": calculation.json()["result"],
            },
        )
        assert response.status_code == 200, response.text
        assert response.content


def test_delete_record(client, auth_headers):
    created = client.post(
        "/api/calculators/mtbf/calculate", headers=auth_headers, json={"inputs": MTBF_INPUTS}
    ).json()
    record_id = created["record_id"]
    response = client.delete(f"/api/history/{record_id}", headers=auth_headers)
    assert response.status_code == 200
    assert client.get(f"/api/history/{record_id}", headers=auth_headers).status_code == 404
