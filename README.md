# Graph-Based AML Investigation Workflow

An end-to-end **anti-money laundering (AML)** system that turns raw Bitcoin transactions into a transaction graph, flags likely illicit activity with a **Graph Neural Network (GraphSAGE)**, and supports analysts with an **LLM-powered investigation workflow** that drafts SAR-style narratives, with **human-in-the-loop review** before any case is closed.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![PySpark](https://img.shields.io/badge/PySpark-3.x-orange)
![PyTorch Geometric](https://img.shields.io/badge/PyTorch%20Geometric-GNN-red)
![Neo4j](https://img.shields.io/badge/Neo4j-Graph%20DB-008CC1)
![LangGraph](https://img.shields.io/badge/LangGraph-Agents-green)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688)
![React](https://img.shields.io/badge/React-TypeScript-61DAFB)

---

## Table of Contents
- [Overview](#overview)
- [Architecture](#architecture)
- [Dataset](#dataset)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Usage](#usage)
- [Model Results](#model-results)
- [Investigation Workflow](#investigation-workflow)
- [Limitations](#limitations)
- [Future Work](#future-work)
- [Acknowledgements](#acknowledgements)
- [License](#license)

---

## Overview

Traditional rule-based AML systems look at transactions one at a time and miss patterns that only appear across **connected** transactions (layering, fan-in / fan-out, peel chains). This project treats transactions as a **graph** and combines three things:

1. **Data pipeline** – PySpark processes ~200K Bitcoin transactions from the public Elliptic dataset and builds a transaction graph.
2. **Graph ML** – A GraphSAGE model learns from each transaction's features *and* its neighbours to flag likely illicit transactions, benchmarked against an XGBoost baseline.
3. **Investigation workflow** – A LangGraph agent pulls the suspicious subgraph, scores risk, and drafts a SAR-style narrative. An analyst reviews it in a React dashboard and approves or rejects the case.

> ⚠️ This is a research / portfolio project built on a public dataset. It is not a production compliance system and its outputs are not legal or regulatory findings.

---

## Architecture

```
            ┌──────────────────────┐
            │  Elliptic Dataset    │  (features, edges, labels)
            └──────────┬───────────┘
                       │
            ┌──────────▼───────────┐
            │  PySpark Pipeline    │  clean → join → build graph
            └──────────┬───────────┘
                       │
        ┌──────────────┼────────────────┐
        │                               │
┌───────▼─────────┐            ┌────────▼────────┐
│  GraphSAGE      │            │     Neo4j       │
│ (PyTorch Geo)   │──scores──▶ │ Transaction     │
│ vs XGBoost      │            │ Graph + Risk    │
└─────────────────┘            └────────┬────────┘
                                        │
                              ┌─────────▼──────────┐
                              │ LangGraph Workflow │
                              │ retrieve → score → │
                              │ summarize → review │
                              └─────────┬──────────┘
                                        │
                              ┌─────────▼──────────┐
                              │   FastAPI Backend  │
                              └─────────┬──────────┘
                                        │
                              ┌─────────▼──────────┐
                              │ React + TypeScript │
                              │ Cytoscape.js UI    │
                              │ (Analyst Review)   │
                              └────────────────────┘
```

---

## Dataset

**Elliptic Bitcoin Dataset** (public, Kaggle)

| Item | Details |
|------|---------|
| Nodes | ~200K Bitcoin transactions |
| Edges | ~234K payment flows between transactions |
| Features | 166 per transaction (local + aggregated neighbourhood features) |
| Time steps | 49 |
| Labels | Illicit, Licit, Unknown (most nodes are unlabeled) |

Download it from Kaggle and place the CSV files in `data/raw/`:

```
data/raw/elliptic_txs_features.csv
data/raw/elliptic_txs_edgelist.csv
data/raw/elliptic_txs_classes.csv
```

> The dataset is not included in this repo. Please follow its license terms.

---

## Features

- **Scalable data processing** with PySpark – cleaning, label mapping, and graph construction.
- **Graph Neural Network** (GraphSAGE) that uses neighbourhood patterns, not just single-transaction features.
- **Baseline comparison** against XGBoost using precision, recall, and F1 on the illicit class.
- **Temporal train/test split** by time step to avoid data leakage.
- **Neo4j graph store** for fast multi-hop transaction tracing.
- **LangGraph investigation agent**: graph retrieval → risk scoring → LLM summary → SAR-style narrative draft.
- **Human-in-the-loop**: no case is closed without analyst approval or rejection.
- **Interactive dashboard** with Cytoscape.js for graph visualization, transaction tracing, and case review.

---

## Tech Stack

| Layer | Tools |
|-------|-------|
| Data Processing | Python, PySpark, Pandas |
| Graph ML | PyTorch, PyTorch Geometric (GraphSAGE) |
| Baseline | XGBoost, Scikit-learn |
| Graph Database | Neo4j (Cypher) |
| Agent Workflow | LangGraph, LLM API |
| Backend | FastAPI |
| Frontend | React, TypeScript, Cytoscape.js |

---

## Project Structure

```
graph-aml-investigation/
├── data/
│   ├── raw/                  # Elliptic CSVs (not committed)
│   └── processed/            # Cleaned graph data
├── pipeline/
│   └── build_graph.py        # PySpark: clean data, build edges/nodes
├── models/
│   ├── graphsage.py          # GraphSAGE model definition
│   ├── train_gnn.py          # GNN training + evaluation
│   └── train_xgboost.py      # XGBoost baseline
├── graph_db/
│   └── load_neo4j.py         # Load nodes, edges, risk scores into Neo4j
├── agent/
│   ├── workflow.py           # LangGraph investigation graph
│   ├── tools.py              # Graph retrieval & risk scoring tools
│   └── prompts.py            # SAR narrative prompts
├── api/
│   └── main.py               # FastAPI endpoints
├── frontend/                 # React + TypeScript + Cytoscape.js dashboard
├── notebooks/                # EDA and experiments
├── requirements.txt
├── .env.example
└── README.md
```

---

## Getting Started

### Prerequisites
- Python 3.10+
- Java 8/11 (for PySpark)
- Node.js 18+
- Neo4j (Desktop or Docker)
- An LLM API key

### 1. Clone the repo
```bash
git clone https://github.com/<your-username>/graph-aml-investigation.git
cd graph-aml-investigation
```

### 2. Set up Python environment
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure environment variables
```bash
cp .env.example .env
```
Fill in `.env`:
```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
LLM_API_KEY=your_api_key
```

### 4. Start Neo4j (Docker option)
```bash
docker run -d --name neo4j -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your_password neo4j:5
```

### 5. Install frontend dependencies
```bash
cd frontend
npm install
```

---

## Usage

```bash
# 1. Build the transaction graph
python pipeline/build_graph.py

# 2. Train models
python models/train_xgboost.py
python models/train_gnn.py

# 3. Load graph + risk scores into Neo4j
python graph_db/load_neo4j.py

# 4. Start the API
uvicorn api.main:app --reload

# 5. Start the dashboard (new terminal)
cd frontend && npm run dev
```

Open the dashboard at `http://localhost:5173` (or the port shown in your terminal).

---

## Model Results

Evaluated on the **illicit class** using a temporal split (train on earlier time steps, test on later ones).

| Model | Precision | Recall | F1 |
|-------|-----------|--------|----|
| XGBoost (baseline) | _add_ | _add_ | _add_ |
| GraphSAGE | _add_ | _add_ | _add_ |

> Replace the placeholders with the numbers from your own runs.

**Note:** The Elliptic dataset is highly imbalanced, and model performance is known to drop after a dark-market shutdown event in later time steps. Results should be read with that in mind.

---

## Investigation Workflow

The LangGraph agent runs these steps for each flagged transaction:

1. **Retrieve** – Query Neo4j for the transaction's multi-hop neighbourhood.
2. **Score** – Attach GNN risk scores and simple pattern signals (fan-in, fan-out, chain length).
3. **Summarize** – The LLM explains why the cluster looks suspicious, using only retrieved evidence.
4. **Draft** – Generate a SAR-style narrative for the analyst.
5. **Human Review** – The analyst approves or rejects the case in the dashboard. Nothing is closed automatically.

---

## Limitations

- Elliptic features are anonymized, so narratives describe graph patterns, not real entities.
- Most nodes are unlabeled, which limits supervised learning.
- LLM summaries can contain errors; human review is required by design.
- Not a certified compliance tool.

---

## Future Work

- Try GAT / temporal GNNs (e.g., EvolveGCN).
- Add explainability (GNNExplainer) to highlight the most influential neighbours.
- Add evaluation for narrative quality (faithfulness to retrieved evidence).
- Containerize the full stack with Docker Compose.

---

## Acknowledgements

- [Elliptic Data Set](https://www.kaggle.com/datasets/ellipticco/elliptic-data-set) – Elliptic, MIT-IBM Watson AI Lab
- Weber et al., *"Anti-Money Laundering in Bitcoin: Experimenting with Graph Convolutional Networks for Financial Forensics"* (2019)
- [PyTorch Geometric](https://pytorch-geometric.readthedocs.io/), [LangGraph](https://langchain-ai.github.io/langgraph/), [Neo4j](https://neo4j.com/)

---

## License

This project is licensed under the MIT License. See `LICENSE` for details.
