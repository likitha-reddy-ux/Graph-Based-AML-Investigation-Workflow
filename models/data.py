"""
Shared helpers for loading the graph, splitting it by time, and scoring models.

Temporal split (same for every model, so results are comparable):
    train : time steps 1-29
    val   : time steps 30-34  (early stopping + picking the decision threshold)
    test  : time steps 35-49  (final reported numbers)

Only labeled nodes (illicit = 1, licit = 0) are used for training and scoring.
Unknown nodes (-1) still take part in the graph as neighbours.
"""

import json
import os

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, precision_recall_fscore_support

FEATURE_COLS = [f"f{i}" for i in range(1, 166)]
TRAIN_END = 29
VAL_END = 34


def load_graph(processed_dir: str = "data/processed"):
    """Load nodes and edges written by pipeline/build_graph.py."""
    nodes = pd.read_parquet(os.path.join(processed_dir, "nodes.parquet"))
    nodes = nodes.sort_values("node_id").reset_index(drop=True)  # row i == node_id i
    edges = pd.read_parquet(os.path.join(processed_dir, "edges.parquet"))
    return nodes, edges


def split_masks(nodes: pd.DataFrame):
    """Boolean masks for labeled train / val / test nodes."""
    labeled = nodes["label"].to_numpy() != -1
    ts = nodes["time_step"].to_numpy()
    train = labeled & (ts <= TRAIN_END)
    val = labeled & (ts > TRAIN_END) & (ts <= VAL_END)
    test = labeled & (ts > VAL_END)
    return train, val, test


def best_threshold(y_true: np.ndarray, probs: np.ndarray) -> float:
    """Pick the probability cut-off that gives the best illicit-class F1 on validation."""
    best_t, best_f1 = 0.5, -1.0
    for t in np.arange(0.05, 0.96, 0.01):
        _, _, f1, _ = precision_recall_fscore_support(
            y_true, (probs >= t).astype(int), average="binary", pos_label=1, zero_division=0
        )
        if f1 > best_f1:
            best_t, best_f1 = float(t), f1
    return best_t


def illicit_metrics(y_true: np.ndarray, probs: np.ndarray, threshold: float) -> dict:
    """Precision, recall, F1 and PR-AUC for the illicit class."""
    preds = (probs >= threshold).astype(int)
    p, r, f1, _ = precision_recall_fscore_support(
        y_true, preds, average="binary", pos_label=1, zero_division=0
    )
    return {
        "precision": round(float(p), 4),
        "recall": round(float(r), 4),
        "f1": round(float(f1), 4),
        "pr_auc": round(float(average_precision_score(y_true, probs)), 4),
        "threshold": round(threshold, 2),
        "n_test": int(len(y_true)),
        "n_illicit": int(y_true.sum()),
    }


def save_results(name: str, metrics: dict, out_dir: str = "models/results"):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{name}.json")
    with open(path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\n{name} test results (illicit class):")
    for k, v in metrics.items():
        print(f"  {k:>10}: {v}")
    print(f"Saved to {path}")
