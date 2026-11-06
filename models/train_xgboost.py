"""
XGBoost baseline: classifies each transaction from its own features only (no graph).

Usage:
    python models/train_xgboost.py
"""

import argparse
import os
import sys

from xgboost import XGBClassifier

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from data import (  # noqa: E402
    FEATURE_COLS, best_threshold, illicit_metrics, load_graph, save_results, split_masks,
)


def main():
    parser = argparse.ArgumentParser(description="Train XGBoost baseline")
    parser.add_argument("--processed-dir", default="data/processed")
    args = parser.parse_args()

    nodes, _ = load_graph(args.processed_dir)
    X = nodes[FEATURE_COLS].to_numpy()
    y = nodes["label"].to_numpy()
    train, val, test = split_masks(nodes)

    # Illicit transactions are rare, so give them more weight
    n_pos = int((y[train] == 1).sum())
    n_neg = int((y[train] == 0).sum())
    print(f"Train: {n_pos:,} illicit / {n_neg:,} licit")

    model = XGBClassifier(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=n_neg / max(n_pos, 1),
        eval_metric="aucpr",
        early_stopping_rounds=30,
        random_state=42,
    )
    model.fit(X[train], y[train], eval_set=[(X[val], y[val])], verbose=False)
    print(f"Best iteration: {model.best_iteration}")

    threshold = best_threshold(y[val], model.predict_proba(X[val])[:, 1])
    test_probs = model.predict_proba(X[test])[:, 1]
    save_results("xgboost", illicit_metrics(y[test], test_probs, threshold))


if __name__ == "__main__":
    main()
