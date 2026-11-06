import type { CaseDetail, CaseSummary, GraphElements, InvestigateResult } from "./types";

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body?.detail) {
        message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      // response had no JSON body
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export const api = {
  listCases: () => request<CaseSummary[]>("/cases?limit=500"),

  getCase: (caseId: string) => request<CaseDetail>(`/cases/${encodeURIComponent(caseId)}`),

  getGraph: (caseId: string) =>
    request<GraphElements>(`/cases/${encodeURIComponent(caseId)}/graph`),

  decide: (caseId: string, decision: "approve" | "reject", analyst: string, note: string) =>
    request<{ case_id: string; status: string }>(
      `/cases/${encodeURIComponent(caseId)}/decision`,
      { method: "POST", body: JSON.stringify({ decision, analyst, note: note || null }) }
    ),

  investigate: (top = 1) =>
    request<{ cases: InvestigateResult[]; message?: string }>("/investigate", {
      method: "POST",
      body: JSON.stringify({ top }),
    }),
};

export function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
