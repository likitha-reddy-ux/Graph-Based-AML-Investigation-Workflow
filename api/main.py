"""
FastAPI backend for the AML investigation dashboard.

Endpoints:
    GET  /health                          - API and Neo4j status
    GET  /transactions/flagged            - highest-risk flagged transactions
    POST /investigate                     - run the LangGraph workflow, create cases
    GET  /cases                           - list cases (filter by status)
    GET  /cases/{case_id}                 - one case with its narrative and transaction
    GET  /cases/{case_id}/graph           - the case's 2-hop graph for Cytoscape.js
    POST /cases/{case_id}/decision        - analyst approves or rejects a case

Cases are created as "pending_review". Only POST /cases/{case_id}/decision
changes that, and a case can be decided only once.

Run:
    uvicorn api.main:app --reload
Interactive docs at http://localhost:8000/docs
"""

import os
import sys
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent"))
import tools  # noqa: E402

app = FastAPI(
    title="AML Investigation API",
    description="Flagged transactions, investigation cases, and analyst decisions.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # React dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

CaseStatus = Literal["pending_review", "approved", "rejected"]


class InvestigateRequest(BaseModel):
    tx_id: int | None = Field(None, description="Investigate this transaction")
    top: int = Field(1, ge=1, le=20, description="Or the N riskiest open flagged transactions")


class DecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    analyst: str = Field(..., min_length=1, max_length=100)
    note: str | None = Field(None, max_length=1000)


@app.get("/health")
def health():
    try:
        tools.get_driver()
        return {"status": "ok", "neo4j": "connected"}
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Neo4j unavailable: {err}")


@app.get("/transactions/flagged")
def flagged_transactions(limit: int = Query(50, ge=1, le=500)):
    return tools.list_flagged(limit)


@app.post("/investigate")
def investigate(req: InvestigateRequest):
    from workflow import build_workflow  # imported here so the API starts even without an LLM set up

    tx_ids = [req.tx_id] if req.tx_id else tools.get_open_flagged(req.top)
    if not tx_ids:
        return {"cases": [], "message": "No open flagged transactions"}

    workflow = build_workflow()
    results = []
    for tx_id in tx_ids:
        state = workflow.invoke({"tx_id": tx_id})
        if state.get("error"):
            results.append({"tx_id": tx_id, "error": state["error"]})
        else:
            results.append({
                "tx_id": tx_id,
                "case_id": state["case_id"],
                "priority": state["signals"]["priority"],
                "summary": state["draft"]["summary"],
                "evidence_check_passed": state["validation"]["passed"],
            })
    return {"cases": results}


@app.get("/cases")
def list_cases(
    status: CaseStatus | None = None,
    limit: int = Query(50, ge=1, le=500),
):
    return tools.list_cases(status, limit)


@app.get("/cases/{case_id}")
def get_case(case_id: str):
    case = tools.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@app.get("/cases/{case_id}/graph")
def get_case_graph(case_id: str):
    case = tools.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return tools.get_case_graph(case["transaction"]["tx_id"])


@app.post("/cases/{case_id}/decision")
def decide_case(case_id: str, req: DecisionRequest):
    status = "approved" if req.decision == "approve" else "rejected"
    result = tools.decide_case(case_id, status, req.analyst, req.note)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Case not found")
    if result == "already_decided":
        raise HTTPException(status_code=409, detail="Case has already been decided")
    return {"case_id": case_id, "status": status, "decided_by": req.analyst}
