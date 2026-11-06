"""
Build the Bitcoin transaction graph from the Elliptic dataset using PySpark.

Inputs (place in data/raw/):
    elliptic_txs_features.csv  - no header; col 0 = txId, col 1 = time step,
                                 cols 2-166 = 165 transaction features
    elliptic_txs_classes.csv   - txId, class ("1" = illicit, "2" = licit, "unknown")
    elliptic_txs_edgelist.csv  - txId1, txId2 (payment flow between transactions)

Outputs (written to data/processed/):
    nodes.parquet  - node_id, tx_id, time_step, label, f1..f165
    edges.parquet  - src, dst (as node_ids)

Labels:
    1  = illicit
    0  = licit
    -1 = unknown (unlabeled)

Usage:
    python pipeline/build_graph.py
    python pipeline/build_graph.py --raw-dir data/raw --out-dir data/processed
"""

import argparse
import os

from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F

NUM_FEATURES = 165


def create_spark() -> SparkSession:
    return (
        SparkSession.builder.appName("elliptic-graph-builder")
        .config("spark.sql.shuffle.partitions", "8")
        .getOrCreate()
    )


def load_features(spark: SparkSession, path: str):
    """Load the features file and give the columns readable names."""
    df = spark.read.csv(path, header=False, inferSchema=True)
    new_names = ["tx_id", "time_step"] + [f"f{i}" for i in range(1, NUM_FEATURES + 1)]
    return df.toDF(*new_names)


def load_labels(spark: SparkSession, path: str):
    """Load labels and map them to 1 (illicit), 0 (licit), -1 (unknown)."""
    df = spark.read.csv(path, header=True, inferSchema=False)
    df = df.withColumnRenamed("txId", "tx_id").withColumnRenamed("class", "raw_class")
    df = df.withColumn("tx_id", F.col("tx_id").cast("long"))
    return df.withColumn(
        "label",
        F.when(F.col("raw_class") == "1", 1)
        .when(F.col("raw_class") == "2", 0)
        .otherwise(-1),
    ).drop("raw_class")


def load_edges(spark: SparkSession, path: str):
    df = spark.read.csv(path, header=True, inferSchema=True)
    return df.toDF("src_tx", "dst_tx")


def build_nodes(features, labels):
    """Join features with labels and assign a 0-based node_id to every transaction."""
    nodes = features.join(labels, on="tx_id", how="left").fillna({"label": -1})

    # Stable 0..N-1 index, needed later by PyTorch Geometric
    window = Window.orderBy("time_step", "tx_id")
    nodes = nodes.withColumn("node_id", F.row_number().over(window) - 1)

    ordered_cols = ["node_id", "tx_id", "time_step", "label"] + [
        f"f{i}" for i in range(1, NUM_FEATURES + 1)
    ]
    return nodes.select(*ordered_cols)


def build_edges(edges, nodes):
    """Replace transaction IDs with node_ids and drop edges to unknown transactions."""
    id_map = nodes.select("tx_id", "node_id")

    edges = (
        edges.join(id_map.withColumnRenamed("tx_id", "src_tx").withColumnRenamed("node_id", "src"),
                   on="src_tx", how="inner")
        .join(id_map.withColumnRenamed("tx_id", "dst_tx").withColumnRenamed("node_id", "dst"),
              on="dst_tx", how="inner")
        .select("src", "dst")
        .dropDuplicates()
    )
    return edges


def print_summary(nodes, edges):
    total = nodes.count()
    print("\n=== Graph summary ===")
    print(f"Nodes (transactions): {total:,}")
    print(f"Edges (payment flows): {edges.count():,}")
    print(f"Time steps: {nodes.select('time_step').distinct().count()}")

    print("\nLabel distribution:")
    names = {1: "illicit", 0: "licit", -1: "unknown"}
    for row in nodes.groupBy("label").count().orderBy("label").collect():
        pct = 100 * row["count"] / total
        print(f"  {names[row['label']]:>8}: {row['count']:>7,}  ({pct:.1f}%)")


def main():
    parser = argparse.ArgumentParser(description="Build Elliptic transaction graph")
    parser.add_argument("--raw-dir", default="data/raw")
    parser.add_argument("--out-dir", default="data/processed")
    args = parser.parse_args()

    spark = create_spark()

    features = load_features(spark, os.path.join(args.raw_dir, "elliptic_txs_features.csv"))
    labels = load_labels(spark, os.path.join(args.raw_dir, "elliptic_txs_classes.csv"))
    raw_edges = load_edges(spark, os.path.join(args.raw_dir, "elliptic_txs_edgelist.csv"))

    nodes = build_nodes(features, labels).cache()
    edges = build_edges(raw_edges, nodes).cache()

    os.makedirs(args.out_dir, exist_ok=True)
    nodes.write.mode("overwrite").parquet(os.path.join(args.out_dir, "nodes.parquet"))
    edges.write.mode("overwrite").parquet(os.path.join(args.out_dir, "edges.parquet"))

    print_summary(nodes, edges)
    print(f"\nSaved graph to {args.out_dir}/")

    spark.stop()


if __name__ == "__main__":
    main()
