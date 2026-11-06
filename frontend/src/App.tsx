import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "./api";
import { CaseDetailView } from "./components/CaseDetailView";
import { CaseList, type Filter } from "./components/CaseList";
import type { CaseSummary } from "./types";

export default function App() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [filter, setFilter] = useState<Filter>("pending_review");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [investigating, setInvestigating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setCases(await api.listCases());
      setError(null);
    } catch (err) {
      setError(`Could not load cases: ${errorMessage(err)}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function investigateNext() {
    setInvestigating(true);
    setError(null);
    try {
      const result = await api.investigate(1);
      await refresh();
      const created = result.cases.find((c) => c.case_id);
      if (created?.case_id) {
        setFilter("pending_review");
        setSelectedId(created.case_id);
      } else {
        setError(result.message ?? result.cases[0]?.error ?? "No new case was created.");
      }
    } catch (err) {
      setError(`Investigation failed: ${errorMessage(err)}`);
    } finally {
      setInvestigating(false);
    }
  }

  const count = (status: CaseSummary["status"]) => cases.filter((c) => c.status === status).length;

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>AML Investigation Dashboard</h1>
          <p className="muted">Elliptic Bitcoin graph · GraphSAGE risk scores · analyst review</p>
        </div>
        <div className="stats">
          <div className="stat"><span>{count("pending_review")}</span>pending</div>
          <div className="stat"><span>{count("approved")}</span>approved</div>
          <div className="stat"><span>{count("rejected")}</span>rejected</div>
          <button className="primary" onClick={investigateNext} disabled={investigating}>
            {investigating ? "Investigating…" : "Investigate next flagged"}
          </button>
        </div>
      </header>

      {error && <div className="banner error">{error}</div>}

      <main className="layout">
        <CaseList
          cases={cases}
          filter={filter}
          onFilter={setFilter}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
        {selectedId ? (
          <CaseDetailView caseId={selectedId} onChanged={refresh} />
        ) : (
          <section className="detail empty-state">
            <p className="muted">
              {loading ? "Loading cases…" : "Select a case on the left to review it."}
            </p>
          </section>
        )}
      </main>
    </div>
  );
}
