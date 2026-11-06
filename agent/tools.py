"""
Neo4j tools used by the investigation workflow.

All tools are read-only except save_case(), which creates a (:Case) node
linked to the transaction it is about. Cases start as "pending_review";
only an analyst can approve or reject them.
"""

import os
from functools import lru_cache

from dotenv import load_dotenv
from neo4j import GraphDatabase

NEIGHBOURHOOD_QUERY = """
MATCH (t:Transaction {tx_id: $tx_id})
OPTIONAL MATCH (src:Transaction)-[:PAYS_TO]->(t)
WITH t, collect(DISTINCT src {.tx_id, .label, .risk_score, .flagged}) AS senders
OPTIONAL MATCH (t)-[:PAYS_TO]->(dst:Transaction)
WITH t, senders, collect(DISTINCT dst {.tx_id, .label, .risk_score, .flagged}) AS receivers
OPTIONAL MATCH (t)-[:PAYS_TO*2]-(hop2:Transaction)
WHERE hop2 <> t
WITH t, senders, receivers,
     collect(DISTINCT hop2 {.tx_id, .label, .risk_score, .flagged}) AS second_hop
RETURN t {.tx_id, .time_step, .label, .risk_score, .flagged} AS tx,
       senders, receivers, second_hop
"""

OPEN_FLAGGED_QUERY = """
MATCH (t:Transaction {flagged: true})
WHERE NOT EXISTS { (t)<-[:ABOUT]-(:Case) }
RETURN t.tx_id AS tx_id
ORDER BY t.risk_score DESC, t.tx_id
LIMIT $limit
"""

SAVE_CASE_QUERY = """
MATCH (t:Transaction {tx_id: $tx_id})
CREATE (c:Case {
    case_id: $case_id,
    status: 'pending_review',
    created_at: datetime(),
    priority: $priority,
    summary: $summary,
    key_indicators: $key_indicators,
    recommended_action: $recommended_action,
    narrative: $narrative,
    unsupported_ids: $unsupported_ids,
    drafted_by: $drafted_by
})
CREATE (c)-[:ABOUT]->(t)
RETURN c.case_id AS case_id
"""


LIST_CASES_QUERY = """
MATCH (c:Case)-[:ABOUT]->(t:Transaction)
WHERE $status IS NULL OR c.status = $status
RETURN c {.case_id, .status, .priority, .summary, .recommended_action,
          created_at: toString(c.created_at), decided_at: toString(c.decided_at)} AS case,
       t {.tx_id, .time_step, .label, .risk_score} AS tx
ORDER BY CASE c.priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
         t.risk_score DESC
LIMIT $limit
"""

GET_CASE_QUERY = """
MATCH (c:Case {case_id: $case_id})-[:ABOUT]->(t:Transaction)
RETURN c {.case_id, .status, .priority, .summary, .key_indicators, .recommended_action,
          .narrative, .unsupported_ids, .drafted_by, .decided_by, .decision_note,
          created_at: toString(c.created_at), decided_at: toString(c.decided_at)} AS case,
       t {.tx_id, .time_step, .label, .risk_score, .flagged} AS tx
"""

DECIDE_CASE_QUERY = """
MATCH (c:Case {case_id: $case_id})
WHERE c.status = 'pending_review'
SET c.status = $status,
    c.decided_by = $analyst,
    c.decision_note = $note,
    c.decided_at = datetime()
RETURN c.case_id AS case_id
"""

CASE_EXISTS_QUERY = "MATCH (c:Case {case_id: $case_id}) RETURN c.status AS status"

GRAPH_NODES_QUERY = """
MATCH (t:Transaction {tx_id: $tx_id})
OPTIONAL MATCH (t)-[:PAYS_TO*1..2]-(n:Transaction)
WITH t, collect(DISTINCT n) AS others
RETURN [x IN others + [t] | x {.tx_id, .label, .risk_score, .flagged}] AS nodes
"""

GRAPH_EDGES_QUERY = """
MATCH (a:Transaction)-[:PAYS_TO]->(b:Transaction)
WHERE a.tx_id IN $ids AND b.tx_id IN $ids
RETURN a.tx_id AS src, b.tx_id AS dst
"""

FLAGGED_QUERY = """
MATCH (t:Transaction {flagged: true})
OPTIONAL MATCH (c:Case)-[:ABOUT]->(t)
RETURN t {.tx_id, .time_step, .label, .risk_score} AS tx, c.case_id AS case_id
ORDER BY t.risk_score DESC, t.tx_id
LIMIT $limit
"""


@lru_cache(maxsize=1)
def get_driver():
    load_dotenv()
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ.get("NEO4J_USER", "neo4j"), os.environ["NEO4J_PASSWORD"]),
    )
    driver.verify_connectivity()
    return driver


def get_neighbourhood(tx_id: int) -> dict | None:
    """The transaction, who paid into it, who it paid, and transactions two hops away."""
    with get_driver().session() as session:
        record = session.run(NEIGHBOURHOOD_QUERY, tx_id=tx_id).single()
    if record is None:
        return None

    senders = record["senders"]
    receivers = record["receivers"]
    direct_ids = {n["tx_id"] for n in senders + receivers}
    second_hop = [n for n in record["second_hop"] if n["tx_id"] not in direct_ids]

    return {
        "transaction": record["tx"],
        "senders": senders,
        "receivers": receivers,
        "second_hop": second_hop,
    }


def get_open_flagged(limit: int = 3) -> list[int]:
    """Highest-risk flagged transactions that do not have a case yet."""
    with get_driver().session() as session:
        return [r["tx_id"] for r in session.run(OPEN_FLAGGED_QUERY, limit=limit)]


def save_case(case: dict) -> str:
    with get_driver().session() as session:
        record = session.execute_write(
            lambda tx: tx.run(SAVE_CASE_QUERY, **case).single()
        )
    return record["case_id"]


def list_cases(status: str | None = None, limit: int = 50) -> list[dict]:
    with get_driver().session() as session:
        return [
            {**r["case"], "transaction": r["tx"]}
            for r in session.run(LIST_CASES_QUERY, status=status, limit=limit)
        ]


def get_case(case_id: str) -> dict | None:
    with get_driver().session() as session:
        record = session.run(GET_CASE_QUERY, case_id=case_id).single()
    return {**record["case"], "transaction": record["tx"]} if record else None


def decide_case(case_id: str, status: str, analyst: str, note: str | None) -> str:
    """Record an analyst decision. Returns 'ok', 'not_found' or 'already_decided'."""
    with get_driver().session() as session:
        record = session.execute_write(
            lambda tx: tx.run(DECIDE_CASE_QUERY, case_id=case_id, status=status,
                              analyst=analyst, note=note).single()
        )
        if record:
            return "ok"
        exists = session.run(CASE_EXISTS_QUERY, case_id=case_id).single()
    return "already_decided" if exists else "not_found"


def get_case_graph(tx_id: int) -> dict | None:
    """Transaction plus everything within two hops, in Cytoscape.js format."""
    with get_driver().session() as session:
        record = session.run(GRAPH_NODES_QUERY, tx_id=tx_id).single()
        if record is None:
            return None
        nodes = {n["tx_id"]: n for n in record["nodes"]}
        edges = session.run(GRAPH_EDGES_QUERY, ids=list(nodes)).data()

    return {
        "nodes": [
            {"data": {
                "id": str(tx),
                "label": str(tx),
                "risk_score": n["risk_score"],
                "flagged": n["flagged"],
                "dataset_label": n["label"],
                "is_case": tx == tx_id,
            }}
            for tx, n in nodes.items()
        ],
        "edges": [
            {"data": {"id": f"{e['src']}-{e['dst']}", "source": str(e["src"]), "target": str(e["dst"])}}
            for e in edges
        ],
    }


def list_flagged(limit: int = 50) -> list[dict]:
    with get_driver().session() as session:
        return [
            {**r["tx"], "case_id": r["case_id"]}
            for r in session.run(FLAGGED_QUERY, limit=limit)
        ]
