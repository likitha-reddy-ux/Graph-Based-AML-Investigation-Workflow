"""
Train GraphSAGE on the Elliptic transaction graph and save a risk score for every node.

Outputs:
    models/results/graphsage.json         - test metrics (illicit class)
    models/artifacts/graphsage.pt         - trained weights (git-ignored)
    data/processed/risk_scores.parquet    - node_id, tx_id, time_step, risk_score
                                            (used by graph_db/load_neo4j.py)

Usage:
    python models/train_gnn.py
    python models/train_gnn.py --epochs 300 --hidden 128
"""

import argparse
import os
import sys

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from sklearn.metrics import average_precision_score
from torch_geometric.data import Data
from torch_geometric.utils import to_undirected

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from data import (  # noqa: E402
    FEATURE_COLS, best_threshold, illicit_metrics, load_graph, save_results, split_masks,
)
from graphsage import GraphSAGE  # noqa: E402


def build_data(nodes, edges, train_mask):
    x = nodes[FEATURE_COLS].to_numpy(dtype=np.float32)

    # Standardize using training nodes only, so test data doesn't leak into scaling
    mean = x[train_mask].mean(axis=0)
    std = x[train_mask].std(axis=0) + 1e-6
    x = (x - mean) / std

    edge_index = torch.tensor(edges[["src", "dst"]].to_numpy().T, dtype=torch.long)
    edge_index = to_undirected(edge_index, num_nodes=len(nodes))  # money flow both ways

    labels = nodes["label"].to_numpy()
    y = torch.tensor(np.where(labels == -1, 0, labels), dtype=torch.long)  # unknowns are masked out

    return Data(x=torch.tensor(x), edge_index=edge_index, y=y)


def predict_probs(model, data):
    model.eval()
    with torch.no_grad():
        return F.softmax(model(data.x, data.edge_index), dim=1)[:, 1].cpu().numpy()


def main():
    parser = argparse.ArgumentParser(description="Train GraphSAGE")
    parser.add_argument("--processed-dir", default="data/processed")
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--hidden", type=int, default=64)
    parser.add_argument("--lr", type=float, default=0.01)
    parser.add_argument("--patience", type=int, default=30)
    args = parser.parse_args()

    torch.manual_seed(42)
    np.random.seed(42)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    nodes, edges = load_graph(args.processed_dir)
    train, val, test = split_masks(nodes)
    labels = nodes["label"].to_numpy()

    data = build_data(nodes, edges, train).to(device)
    train_t = torch.tensor(train, device=device)

    n_pos = int((labels[train] == 1).sum())
    n_neg = int((labels[train] == 0).sum())
    class_weights = torch.tensor([1.0, n_neg / max(n_pos, 1)], device=device)
    print(f"Graph: {data.num_nodes:,} nodes, {data.num_edges:,} edges (undirected)")
    print(f"Train: {n_pos:,} illicit / {n_neg:,} licit | device: {device}")

    model = GraphSAGE(in_dim=data.num_features, hidden_dim=args.hidden).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr, weight_decay=5e-4)

    best_ap, best_state, wait = -1.0, None, 0
    for epoch in range(1, args.epochs + 1):
        model.train()
        optimizer.zero_grad()
        out = model(data.x, data.edge_index)
        loss = F.cross_entropy(out[train_t], data.y[train_t], weight=class_weights)
        loss.backward()
        optimizer.step()

        # Early stopping on validation PR-AUC
        val_ap = average_precision_score(labels[val], predict_probs(model, data)[val])
        if val_ap > best_ap:
            best_ap, wait = val_ap, 0
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
        else:
            wait += 1

        if epoch % 10 == 0:
            print(f"Epoch {epoch:3d} | loss {loss.item():.4f} | val PR-AUC {val_ap:.4f}")
        if wait >= args.patience:
            print(f"Early stopping at epoch {epoch} (best val PR-AUC {best_ap:.4f})")
            break

    model.load_state_dict(best_state)
    probs = predict_probs(model, data)

    threshold = best_threshold(labels[val], probs[val])
    save_results("graphsage", illicit_metrics(labels[test], probs[test], threshold))

    os.makedirs("models/artifacts", exist_ok=True)
    torch.save(model.state_dict(), "models/artifacts/graphsage.pt")

    scores = pd.DataFrame({
        "node_id": nodes["node_id"],
        "tx_id": nodes["tx_id"],
        "time_step": nodes["time_step"],
        "risk_score": probs.round(4),
    })
    out_path = os.path.join(args.processed_dir, "risk_scores.parquet")
    scores.to_parquet(out_path, index=False)
    print(f"Saved risk scores for {len(scores):,} transactions to {out_path}")


if __name__ == "__main__":
    main()
