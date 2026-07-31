/* API client for Pulse backend. */

const API_BASE =
  import.meta.env.VITE_API_BASE || "http://localhost:8000/api";

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API error: ${res.status} ${res.statusText} ${text}`);
  }
  return res.json();
}

export const api = {
  // Repos
  listRepos: () =>
    fetchJSON<import("../types").RepoSummary[]>("/repos"),
  reindexRepo: (fullName: string) =>
    fetchJSON<{ status: string; repo: string }>(
      `/repos/${encodeURIComponent(fullName)}/reindex`,
      { method: "POST" }
    ),

  // PRs
  listPRs: (repo?: string, status?: string) => {
    const params = new URLSearchParams();
    if (repo) params.set("repo_full_name", repo);
    if (status) params.set("triage_status", status);
    return fetchJSON<import("../types").PRSummary[]>(`/prs?${params}`);
  },
  getPR: (prId: string) =>
    fetchJSON<import("../types").PRDetail>(`/prs/${prId}`),

  // Triage approval
  approveReport: (reportId: string, notes: string = "") =>
    fetchJSON<{ status: string }>("/triage/approve", {
      method: "POST",
      body: JSON.stringify({ report_id: reportId, notes }),
    }),
  rejectReport: (reportId: string, notes: string = "") =>
    fetchJSON<{ status: string }>("/triage/reject", {
      method: "POST",
      body: JSON.stringify({ report_id: reportId, notes }),
    }),

  // Dashboard
  getStats: () =>
    fetchJSON<{
      total_repos: number;
      open_prs: number;
      awaiting_approval: number;
      in_progress: number;
      posted_today: number;
      avg_processing_time_ms: number | null;
    }>("/dashboard/stats"),
  semanticSearch: (repo: string, q: string, topK: number = 10) => {
    const params = new URLSearchParams({ repo, q, top_k: String(topK) });
    return fetchJSON<{ query: string; results: any[] }>(
      `/dashboard/search?${params}`
    );
  },
  getBlastRadius: (repo: string, file: string) => {
    const params = new URLSearchParams({ repo, file });
    return fetchJSON<{ file: string; affected: any[]; count: number }>(
      `/dashboard/blast-radius?${params}`
    );
  },
};
