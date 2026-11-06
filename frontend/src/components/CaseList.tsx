import type { CaseStatus, CaseSummary } from "../types";

export type Filter = CaseStatus | "all";

const FILTERS: { value: Filter; label: string }[] = [
  { value: "pending_review", label: "Pending" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
  { value: "all", label: "All" },
];

interface Props {
  cases: CaseSummary[];
  filter: Filter;
  onFilter: (filter: Filter) => void;
  selectedId: string | null;
  onSelect: (caseId: string) => void;
}

export function CaseList({ cases, filter, onFilter, selectedId, onSelect }: Props) {
  const visible = filter === "all" ? cases : cases.filter((c) => c.status === filter);

  return (
    <aside className="case-list">
      <div className="tabs">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            className={filter === f.value ? "tab active" : "tab"}
            onClick={() => onFilter(f.value)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {visible.length === 0 && <p className="empty">No cases here.</p>}

      <ul>
        {visible.map((c) => (
          <li key={c.case_id}>
            <button
              className={c.case_id === selectedId ? "case-item selected" : "case-item"}
              onClick={() => onSelect(c.case_id)}
            >
              <div className="case-item-top">
                <span className="case-id">{c.case_id}</span>
                <span className={`badge ${c.priority}`}>{c.priority}</span>
              </div>
              <div className="case-item-meta">
                tx {c.transaction.tx_id} · step {c.transaction.time_step} · risk{" "}
                {c.transaction.risk_score.toFixed(3)}
              </div>
              {c.status !== "pending_review" && (
                <div className={`status ${c.status}`}>{c.status}</div>
              )}
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
