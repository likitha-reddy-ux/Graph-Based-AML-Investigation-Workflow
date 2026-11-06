import { useState } from "react";
import { api, errorMessage } from "../api";
import type { CaseDetail } from "../types";

const NAME_KEY = "aml-analyst-name";

function loadName(): string {
  try {
    return localStorage.getItem(NAME_KEY) ?? "";
  } catch {
    return "";
  }
}

function saveName(name: string) {
  try {
    localStorage.setItem(NAME_KEY, name);
  } catch {
    // storage not available; the name just won't be remembered
  }
}

interface Props {
  detail: CaseDetail;
  onDecided: () => void;
}

export function DecisionPanel({ detail, onDecided }: Props) {
  const [analyst, setAnalyst] = useState(loadName);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (detail.status !== "pending_review") {
    return (
      <div className={`decision decided ${detail.status}`}>
        <strong>{detail.status === "approved" ? "Approved" : "Rejected"}</strong> by{" "}
        {detail.decided_by ?? "unknown"}
        {detail.decided_at && <> on {new Date(detail.decided_at).toLocaleString()}</>}
        {detail.decision_note && <p className="note">“{detail.decision_note}”</p>}
      </div>
    );
  }

  async function submit(decision: "approve" | "reject") {
    if (!analyst.trim()) {
      setError("Enter your name before deciding.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      saveName(analyst.trim());
      await api.decide(detail.case_id, decision, analyst.trim(), note.trim());
      setNote("");
      onDecided();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="decision">
      <h3>Analyst decision</h3>
      <label>
        Analyst name
        <input value={analyst} onChange={(e) => setAnalyst(e.target.value)} placeholder="Your name" />
      </label>
      <label>
        Note (optional)
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={3}
          placeholder="Why are you approving or rejecting this case?"
        />
      </label>
      {error && <p className="error">{error}</p>}
      <div className="decision-buttons">
        <button className="approve" disabled={busy} onClick={() => submit("approve")}>
          Approve (escalate)
        </button>
        <button className="reject" disabled={busy} onClick={() => submit("reject")}>
          Reject (false positive)
        </button>
      </div>
    </div>
  );
}
