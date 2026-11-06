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
