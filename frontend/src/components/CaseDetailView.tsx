import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "../api";
import type { CaseDetail, GraphElements, GraphNodeData } from "../types";
import { DecisionPanel } from "./DecisionPanel";
import { GraphView } from "./GraphView";

interface Props {
  caseId: string;
  onChanged: () => void;
}

export function CaseDetailView({ caseId, onChanged }: Props) {
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [graph, setGraph] = useState<GraphElements | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNodeData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setSelectedNode(null);
    Promise.all([api.getCase(caseId), api.getGraph(caseId)])
      .then(([d, g]) => {
        if (cancelled) return;
        setDetail(d);
        setGraph(g);
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, [caseId, reloadKey]);

  const handleDecided = useCallback(() => {
    setReloadKey((k) => k + 1);
    onChanged();
  }, [onChanged]);

  if (error) return <section className="detail"><p className="error">{error}</p></section>;
  if (!detail || detail.case_id !== caseId) {
    return <section className="detail"><p className="muted">Loading case…</p></section>;
  }

  const tx = detail.transaction;
  const unsupported = detail.unsupported_ids ?? [];

  return (
    <section className="detail">
      <header className="detail-header">
        <div>
          <h2>{detail.case_id}</h2>
          <p className="muted">
            Transaction {tx.tx_id} · time step {tx.time_step} · dataset label “{tx.label}”
          </p>
        </div>
        <div className="detail-badges">
          <span className={`badge ${detail.priority}`}>{detail.priority} priority</span>
          <span className="risk">risk {tx.risk_score.toFixed(3)}</span>
        </div>
      </header>

      <div className="detail-grid">
        <div className="panel">
          <h3>Transaction graph (2 hops)</h3>
          {graph && <GraphView elements={graph} onSelect={setSelectedNode} />}
          {selectedNode && (
            <div className="node-info">
              <strong>tx {selectedNode.id}</strong> · risk {selectedNode.risk_score.toFixed(3)} ·{" "}
              {selectedNode.flagged ? "flagged" : "not flagged"} · label “{selectedNode.dataset_label}”
            </div>
          )}
        </div>

        <div className="panel">
          <h3>Summary</h3>
          <p>{detail.summary}</p>

          <h3>Key indicators</h3>
          <ul className="indicators">
            {(detail.key_indicators ?? []).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>

          <h3>Draft SAR narrative</h3>
          <p className="narrative">{detail.narrative}</p>
          <p className="muted small">
            Drafted by: {detail.drafted_by} · Recommended: {detail.recommended_action}
          </p>

          <div className={unsupported.length ? "check fail" : "check pass"}>
            {unsupported.length
              ? `Evidence check failed: mentions unknown transactions ${unsupported.join(", ")}`
              : "Evidence check passed: every transaction mentioned is in the graph"}
          </div>

          <DecisionPanel detail={detail} onDecided={handleDecided} />
        </div>
      </div>
    </section>
  );
}
