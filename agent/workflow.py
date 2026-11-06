"""
LangGraph investigation workflow for flagged transactions.

    retrieve -> score -> draft -> validate -> save (pending_review)

retrieve : pull the transaction and its 2-hop neighbourhood from Neo4j
score    : compute simple, explainable pattern signals and a case priority
draft    : write a SAR-style narrative (LLM or rule-based template)
validate : check the draft only mentions transaction IDs found in the evidence
save     : store a (:Case) node with status "pending_review" for an analyst

Nothing is approved automatically. An analyst approves or rejects each case
(through the API and dashboard).

Usage:
    python agent/workflow.py                     # investigate the top 3 open flagged transactions
    python agent/workflow.py --top 10
    python agent/workflow.py --tx-id 20627423
    python agent/workflow.py --tx-id 20627423 --dry-run   # don't save the case
"""

import argparse
import os
import re
import sys
import uuid
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from llm import draft_case, provider_name  # noqa: E402
from tools import get_neighbourhood, get_open_flagged, save_case  # noqa: E402

HIGH_RISK = 0.95


class CaseState(TypedDict, total=False):
    tx_id: int
    dry_run: bool
    evidence: dict
    signals: dict
    draft: dict
    validation: dict
    case_id: str
    error: str


# ---------- nodes ----------

def retrieve(state: CaseState) -> CaseState:
    evidence = get_neighbourhood(state["tx_id"])
    if evidence is None:
        return {"error": f"Transaction {state['tx_id']} not found in Neo4j"}
    return {"evidence": evidence}


def score(state: CaseState) -> CaseState:
    ev = state["evidence"]
    tx = ev["transaction"]
    direct = ev["senders"] + ev["receivers"]

    in_degree = len(ev["senders"])
    out_degree = len(ev["receivers"])
    flagged = sum(1 for n in direct if n.get("flagged"))
    illicit = sum(1 for n in direct if n.get("label") == "illicit")
    hop2_flagged = sum(1 for n in ev["second_hop"] if n.get("flagged"))
    flagged_ratio = flagged / len(direct) if direct else 0.0

    patterns = []
    if in_degree >= 3:
        patterns.append(f"fan-in: funds received from {in_degree} transactions")
    if out_degree >= 3:
        patterns.append(f"fan-out: funds sent to {out_degree} transactions")
    if illicit:
        patterns.append(f"direct link to {illicit} known illicit transaction(s)")
    if len(direct) >= 2 and flagged_ratio >= 0.5:
        patterns.append("most direct counterparties are also flagged")
    if hop2_flagged >= 3:
        patterns.append(f"{hop2_flagged} flagged transactions within two hops")
    if not direct:
        patterns.append("isolated transaction: no counterparties in the loaded graph")

    if tx["risk_score"] >= HIGH_RISK and (illicit or flagged_ratio >= 0.5):
        priority = "high"
    elif tx["risk_score"] >= HIGH_RISK or flagged:
        priority = "medium"
    else:
        priority = "low"

    return {"signals": {
        "in_degree": in_degree,
        "out_degree": out_degree,
        "direct_neighbours": len(direct),
        "flagged_neighbours": flagged,
        "illicit_neighbours": illicit,
        "second_hop_flagged": hop2_flagged,
        "patterns": patterns,
        "priority": priority,
    }}


def draft(state: CaseState) -> CaseState:
    result = draft_case(state["evidence"], state["signals"])
    return {"draft": result.model_dump()}


def validate(state: CaseState) -> CaseState:
    """Flag any transaction ID in the draft that is not part of the evidence."""
    ev = state["evidence"]
    known = {ev["transaction"]["tx_id"]}
    for group in ("senders", "receivers", "second_hop"):
        known.update(n["tx_id"] for n in ev[group])

    d = state["draft"]
    text = " ".join([d["summary"], d["narrative"], *d["key_indicators"]])
    mentioned = {int(m) for m in re.findall(r"\b\d{6,}\b", text)}
    unsupported = sorted(mentioned - known)

    return {"validation": {"passed": not unsupported, "unsupported_ids": unsupported}}


def save(state: CaseState) -> CaseState:
    if state.get("dry_run"):
        return {"case_id": "(dry run - not saved)"}

    d = state["draft"]
    case_id = f"CASE-{uuid.uuid4().hex[:8].upper()}"
    save_case({
        "tx_id": state["tx_id"],
        "case_id": case_id,
        "priority": state["signals"]["priority"],
        "summary": d["summary"],
        "key_indicators": d["key_indicators"],
        "recommended_action": d["recommended_action"],
        "narrative": d["narrative"],
        "unsupported_ids": state["validation"]["unsupported_ids"],
        "drafted_by": provider_name(),
    })
    return {"case_id": case_id}


def after_retrieve(state: CaseState) -> str:
    return "error" if state.get("error") else "ok"


# ---------- graph ----------

def build_workflow():
    graph = StateGraph(CaseState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("score", score)
    graph.add_node("draft", draft)
    graph.add_node("validate", validate)
    graph.add_node("save", save)

    graph.add_edge(START, "retrieve")
    graph.add_conditional_edges("retrieve", after_retrieve, {"ok": "score", "error": END})
    graph.add_edge("score", "draft")
    graph.add_edge("draft", "validate")
    graph.add_edge("validate", "save")
    graph.add_edge("save", END)
    return graph.compile()


def print_case(result: CaseState):
    if result.get("error"):
        print(f"\n[!] {result['error']}")
        return

    tx = result["evidence"]["transaction"]
    s, d, v = result["signals"], result["draft"], result["validation"]
    print("\n" + "=" * 70)
    print(f"Case {result['case_id']}  |  tx {tx['tx_id']}  |  step {tx['time_step']}  |  "
          f"risk {tx['risk_score']:.3f}  |  priority {s['priority'].upper()}")
    print("=" * 70)
    print(f"Summary: {d['summary']}")
    print("Indicators:")
    for item in d["key_indicators"]:
        print(f"  - {item}")
    print(f"Recommended action: {d['recommended_action']}")
    print(f"\nNarrative:\n{d['narrative']}")
    check = "passed" if v["passed"] else f"FAILED - unsupported IDs: {v['unsupported_ids']}"
    print(f"\nEvidence check: {check}")
    print("Status: pending analyst review")


def main():
    parser = argparse.ArgumentParser(description="Run the AML investigation workflow")
    parser.add_argument("--tx-id", type=int, help="Investigate one specific transaction")
    parser.add_argument("--top", type=int, default=3, help="Number of open flagged transactions")
    parser.add_argument("--dry-run", action="store_true", help="Do not save cases to Neo4j")
    args = parser.parse_args()

    tx_ids = [args.tx_id] if args.tx_id else get_open_flagged(args.top)
    if not tx_ids:
        print("No open flagged transactions found.")
        return

    print(f"Drafting with: {provider_name()}")
    workflow = build_workflow()
    for tx_id in tx_ids:
        print_case(workflow.invoke({"tx_id": tx_id, "dry_run": args.dry_run}))


if __name__ == "__main__":
    main()
