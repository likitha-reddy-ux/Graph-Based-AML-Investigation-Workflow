"""
API tests. Neo4j calls are replaced with fakes, so these run without a database.

Run:
    pytest tests/ -v
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "api"))
sys.path.insert(0, os.path.join(ROOT, "agent"))

import main  # noqa: E402

CASE = {
    "case_id": "CASE-TEST01",
    "status": "pending_review",
    "priority": "high",
    "summary": "Test case",
    "transaction": {"tx_id": 123456, "time_step": 35, "label": "unknown", "risk_score": 0.99},
}


@pytest.fixture
def client(monkeypatch):
    decisions = {}

    def fake_decide(case_id, status, analyst, note):
        if case_id != CASE["case_id"]:
            return "not_found"
        if case_id in decisions:
            return "already_decided"
        decisions[case_id] = status
        return "ok"

    monkeypatch.setattr(main.tools, "list_cases", lambda status, limit: [CASE])
    monkeypatch.setattr(main.tools, "get_case",
                        lambda case_id: CASE if case_id == CASE["case_id"] else None)
    monkeypatch.setattr(main.tools, "decide_case", fake_decide)
    monkeypatch.setattr(main.tools, "get_case_graph",
                        lambda tx_id: {"nodes": [{"data": {"id": str(tx_id)}}], "edges": []})
    return TestClient(main.app)


def test_list_cases(client):
    response = client.get("/cases?status=pending_review")
    assert response.status_code == 200
    assert response.json()[0]["case_id"] == "CASE-TEST01"


def test_invalid_status_rejected(client):
    assert client.get("/cases?status=closed").status_code == 422


def test_get_case_not_found(client):
    assert client.get("/cases/CASE-NOPE").status_code == 404


def test_case_graph(client):
    response = client.get("/cases/CASE-TEST01/graph")
    assert response.status_code == 200
    assert response.json()["nodes"][0]["data"]["id"] == "123456"


def test_approve_then_cannot_decide_again(client):
    body = {"decision": "approve", "analyst": "Likitha", "note": "Confirmed fan-in pattern"}
    first = client.post("/cases/CASE-TEST01/decision", json=body)
    assert first.status_code == 200
    assert first.json()["status"] == "approved"

    second = client.post("/cases/CASE-TEST01/decision", json={**body, "decision": "reject"})
    assert second.status_code == 409


def test_decision_requires_analyst(client):
    response = client.post("/cases/CASE-TEST01/decision", json={"decision": "approve", "analyst": ""})
    assert response.status_code == 422


def test_decision_must_be_approve_or_reject(client):
    response = client.post("/cases/CASE-TEST01/decision",
                           json={"decision": "close", "analyst": "Likitha"})
    assert response.status_code == 422
