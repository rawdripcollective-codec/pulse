/* Default MSW request handlers — the happy-path fixtures for tests.

Tests can extend or override these via `server.use(...)` in their
specific cases. */

import { http, HttpResponse } from "msw";

import type {
  PRDetail,
  PRSummary,
  RepoSummary,
  TriageReportDetail,
  WSMessage,
} from "../../src/types";

const BASE = "http://localhost:8000/api";

// ─── Fixtures ────────────────────────────────────────────────

export const sampleRepos: RepoSummary[] = [
  {
    id: "repo-1",
    full_name: "acme/widget",
    description: "Sample widget service",
    language: "Python",
    stars: 42,
    status: "ready",
    indexed_at: "2025-01-01T00:00:00Z",
    open_prs: 3,
    pending_triages: 1,
  },
  {
    id: "repo-2",
    full_name: "acme/gizmo",
    description: null,
    language: "TypeScript",
    stars: 7,
    status: "indexing",
    indexed_at: null,
    open_prs: 0,
    pending_triages: 0,
  },
];

export const samplePRs: PRSummary[] = [
  {
    id: "pr-1",
    number: 1,
    title: "Add retry logic to webhook handler",
    author: "alice",
    author_avatar: "https://avatars.githubusercontent.com/u/1",
    files_changed: 2,
    additions: 50,
    deletions: 10,
    classification: "human_first",
    classification_confidence: 0.91,
    triage_status: "awaiting_approval",
    created_at: new Date(Date.now() - 1000 * 60 * 60 * 2).toISOString(),
    repo_full_name: "acme/widget",
  },
  {
    id: "pr-2",
    number: 2,
    title: "Update deps",
    author: "bob",
    author_avatar: null,
    files_changed: 1,
    additions: 3,
    deletions: 3,
    classification: "trivial",
    classification_confidence: 0.99,
    triage_status: "posted",
    created_at: new Date(Date.now() - 1000 * 60 * 30).toISOString(),
    repo_full_name: "acme/widget",
  },
  {
    id: "pr-3",
    number: 9,
    title: "Sketchy AI-generated refactor",
    author: "carol",
    author_avatar: null,
    files_changed: 12,
    additions: 800,
    deletions: 200,
    classification: "ai_slop",
    classification_confidence: 0.78,
    triage_status: "in_progress",
    created_at: new Date(Date.now() - 1000 * 60 * 5).toISOString(),
    repo_full_name: "acme/widget",
  },
];

export const sampleReport: TriageReportDetail = {
  id: "report-1",
  classification: "human_first",
  classification_rationale:
    "Clean, well-tested change with clear separation of concerns.",
  classification_confidence: 0.92,
  blast_radius_score: 0.12,
  affected_modules: [
    {
      caller: "main.py:run",
      caller_file: "main.py",
      called: "retry(fn)",
      called_file: "webhooks.py",
    },
  ],
  summary:
    "# Triage Report\n\n**One-line summary:** Adds retry logic to the webhook handler.\n\n**Risk:** Low.",
  suggested_action: "approve",
  suggested_reviewer: "Backend platform",
  approved: null,
  approved_by: null,
  approved_at: null,
  posted_to_github: false,
  processing_time_ms: 1240,
  created_at: new Date(Date.now() - 1000 * 60 * 5).toISOString(),
};

export const samplePRDetail: PRDetail = {
  ...samplePRs[0]!,
  body: "This PR adds exponential backoff to the webhook handler.",
  base_branch: "main",
  head_branch: "feature/retry",
  state: "open",
  updated_at: new Date().toISOString(),
  triage_reports: [sampleReport],
};

export const sampleStats = {
  total_repos: 2,
  open_prs: 3,
  awaiting_approval: 1,
  in_progress: 1,
  posted_today: 5,
  avg_processing_time_ms: 1234,
};

// ─── Handlers ────────────────────────────────────────────────

export const handlers = [
  http.get(`${BASE}/repos`, () => HttpResponse.json(sampleRepos)),

  http.post(
    `${BASE}/repos/:fullName/reindex`,
    ({ params }) => {
      const { fullName } = params as { fullName: string };
      return HttpResponse.json({ status: "queued", repo: fullName });
    }
  ),

  http.get(`${BASE}/prs`, ({ request }) => {
    const url = new URL(request.url);
    const repo = url.searchParams.get("repo_full_name");
    const status = url.searchParams.get("triage_status");
    let filtered = samplePRs;
    if (repo) filtered = filtered.filter((p) => p.repo_full_name === repo);
    if (status)
      filtered = filtered.filter((p) => p.triage_status === status);
    return HttpResponse.json(filtered);
  }),

  http.get(`${BASE}/prs/:prId`, ({ params }) => {
    const { prId } = params as { prId: string };
    if (prId === samplePRDetail.id) return HttpResponse.json(samplePRDetail);
    return new HttpResponse(null, { status: 404 });
  }),

  http.post(`${BASE}/triage/approve`, () =>
    HttpResponse.json({ status: "approved" })
  ),

  http.post(`${BASE}/triage/reject`, () =>
    HttpResponse.json({ status: "rejected" })
  ),

  http.get(`${BASE}/dashboard/stats`, () => HttpResponse.json(sampleStats)),

  http.get(`${BASE}/dashboard/search`, () =>
    HttpResponse.json({ query: "auth", results: [] })
  ),

  http.get(`${BASE}/dashboard/blast-radius`, () =>
    HttpResponse.json({ file: "auth.py", affected: [], count: 0 })
  ),
];

// Re-export the WSMessage type so tests can import it here
export type { WSMessage };
