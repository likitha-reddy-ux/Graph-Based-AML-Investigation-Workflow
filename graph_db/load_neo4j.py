"""
Load the transaction graph and GraphSAGE risk scores into Neo4j.

Graph model:
    (:Transaction {tx_id, time_step, label, risk_score, flagged})
    (:Transaction)-[:PAYS_TO]->(:Transaction)

    label    : "illicit", "licit" or "unknown"
    flagged  : true when risk_score >= the threshold chosen on validation data
               (read from models/results/graphsage.json)

By default only the test period (time steps 35-49) is loaded. That is the period
analysts would investigate, and it fits within the Neo4j AuraDB Free limits
(200K nodes / 400K relationships). Use --min-time-step 1 to load everything
into a local Neo4j instance.

Needs (run these first):
    python pipeline/build_graph.py
    python models/train_gnn.py

Connection settings come from environment variables (or a .env file):
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

Usage:
    python graph_db/load_neo4j.py
    python graph_db/load_neo4j.py --clear
    python graph_db/load_neo4j.py --min-time-step 1
"""

import argparse
import json
import os

import pandas as pd
from dotenv import load_dotenv
from neo4j import GraphDatabase

BATCH_SIZE = 5000
LABEL_NAMES = {1: "illicit", 0: "licit", -1: "unknown"}

CREATE_CONSTRAINT = """
CREATE CONSTRAINT transaction_id IF NOT EXISTS
FOR (t:Transaction) REQUIRE t.tx_id IS UNIQUE
"""

CREATE_RISK_INDEX = """
CREATE INDEX transaction_risk IF NOT EXISTS
FOR (t:Transaction) ON (t.risk_score)
"""

LOAD_NODES = """
UNWIND $rows AS row
MERGE (t:Transaction {tx_id: row.tx_id})
SET t.time_step  = row.time_step,
    t.label      = row.label,
    t.risk_score = row.risk_score,
    t.flagged    = row.flagged
"""

LOAD_EDGES = """
UNWIND $rows AS row
MATCH (a:Transaction {tx_id: row.src})
MATCH (b:Transaction {tx_id: row.dst})
MERGE (a)-[:PAYS_TO]->(b)
"""

DELETE_BATCH = """
MATCH (t:Transaction)
WITH t LIMIT 10000
DETACH DELETE t
RETURN count(*) AS deleted
"""

TOP_FLAGGED = """
MATCH (t:Transaction {flagged: true})
OPTIONAL MATCH (t)-[r:PAYS_TO]-()
RETURN t.tx_id AS tx_id, t.time_step AS time_step, t.label AS label,
       t.risk_score AS risk_score, count(r) AS connections
ORDER BY risk_score DESC
LIMIT 10
"""


def read_threshold(path: str = "models/results/graphsage.json") -> float:
    try:
        with open(path) as f:
            return float(json.load(f)["threshold"])
    except (OSError, KeyError, ValueError):
        print(f"Could not read threshold from {path}; using 0.5")
        return 0.5


def prepare_data(processed_dir: str, min_time_step: int, threshold: float):
    nodes = pd.read_parquet(
        os.path.join(processed_dir, "nodes.parquet"),
        columns=["node_id", "tx_id", "time_step", "label"],
    )
    scores = pd.read_parquet(
        os.path.join(processed_dir, "risk_scores.parquet"),
        columns=["node_id", "risk_score"],
    )
    nodes = nodes.merge(scores, on="node_id", how="inner")
    nodes = nodes[nodes["time_step"] >= min_time_step]

    edges = pd.read_parquet(os.path.join(processed_dir, "edges.parquet"))
    id_to_tx = dict(zip(nodes["node_id"].tolist(), nodes["tx_id"].tolist()))
    edges = edges[edges["src"].isin(id_to_tx) & edges["dst"].isin(id_to_tx)]

    # Plain Python types, so the Neo4j driver can send them
    node_rows = [
        {
            "tx_id": int(tx),
            "time_step": int(ts),
            "label": LABEL_NAMES[int(lbl)],
            "risk_score": float(score),
            "flagged": bool(score >= threshold),
        }
        for tx, ts, lbl, score in zip(
            nodes["tx_id"].tolist(), nodes["time_step"].tolist(),
            nodes["label"].tolist(), nodes["risk_score"].tolist(),
        )
    ]
    edge_rows = [
        {"src": int(id_to_tx[s]), "dst": int(id_to_tx[d])}
        for s, d in zip(edges["src"].tolist(), edges["dst"].tolist())
    ]
    return node_rows, edge_rows


def write_in_batches(session, query: str, rows: list, name: str):
    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start:start + BATCH_SIZE]
        session.execute_write(lambda tx, b=batch: tx.run(query, rows=b).consume())
        done = min(start + BATCH_SIZE, len(rows))
        print(f"  {name}: {done:,} / {len(rows):,}", end="\r")
    print()


def clear_graph(session):
    total = 0
    while True:
        deleted = session.run(DELETE_BATCH).single()["deleted"]
        total += deleted
        if deleted == 0:
            break
    print(f"Cleared {total:,} existing transactions")


def main():
    parser = argparse.ArgumentParser(description="Load the transaction graph into Neo4j")
    parser.add_argument("--processed-dir", default="data/processed")
    parser.add_argument("--min-time-step", type=int, default=35)
    parser.add_argument("--clear", action="store_true", help="Delete existing transactions first")
    args = parser.parse_args()

    load_dotenv()
    uri = os.environ["NEO4J_URI"]
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ["NEO4J_PASSWORD"]

    threshold = read_threshold()
    node_rows, edge_rows = prepare_data(args.processed_dir, args.min_time_step, threshold)
    n_flagged = sum(r["flagged"] for r in node_rows)
    print(f"Prepared {len(node_rows):,} transactions and {len(edge_rows):,} payment flows "
          f"(time steps >= {args.min_time_step})")
    print(f"Flagged as high risk (score >= {threshold}): {n_flagged:,}")

    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    print(f"Connected to {uri}")

    with driver.session() as session:
        if args.clear:
            clear_graph(session)
        session.run(CREATE_CONSTRAINT).consume()
        session.run(CREATE_RISK_INDEX).consume()

        write_in_batches(session, LOAD_NODES, node_rows, "Transactions")
        write_in_batches(session, LOAD_EDGES, edge_rows, "Payment flows")

        print("\nTop 10 flagged transactions:")
        print(f"  {'tx_id':>12} {'step':>5} {'label':>8} {'risk':>6} {'links':>6}")
        for r in session.run(TOP_FLAGGED):
            print(f"  {r['tx_id']:>12} {r['time_step']:>5} {r['label']:>8} "
                  f"{r['risk_score']:>6.3f} {r['connections']:>6}")

    driver.close()
    print("\nDone. Open Neo4j Browser or the Aura console to explore the graph.")


if __name__ == "__main__":
    main()
