/* TypeScript types mirroring the Pulse API schemas. */

export interface RepoSummary {
  id: string;
  full_name: string;
  description: string | null;
  language: string | null;
  stars: number;
  status: "indexing" | "ready" | "error";
  indexed_at: string | null;
  open_prs: number;
  pending_triages: number;
}

export type PRClassification =
  | "human_first"
  | "ai_assisted"
  | "ai_slop"
  | "trivial"
  | "high_risk";

export type TriageStatus =
  | "pending"
  | "in_progress"
  | "awaiting_approval"
  | "approved"
  | "rejected"
  | "posted";

export interface PRSummary {
  id: string;
  number: number;
  title: string;
  author: string;
  author_avatar: string | null;
  files_changed: number;
  additions: number;
  deletions: number;
  classification: PRClassification | null;
  classification_confidence: number | null;
  triage_status: TriageStatus;
  created_at: string;
  repo_full_name: string;
}

export interface TriageReportDetail {
  id: string;
  classification: PRClassification;
  classification_rationale: string | null;
  classification_confidence: number;
  blast_radius_score: number | null;
  affected_modules: Array<{
    caller: string;
    caller_file: string;
    called: string;
    called_file: string;
  }>;
  summary: string;
  suggested_action: string | null;
  suggested_reviewer: string | null;
  approved: boolean | null;
  approved_by: string | null;
  approved_at: string | null;
  posted_to_github: boolean;
  processing_time_ms: number | null;
  created_at: string;
}

export interface PRDetail extends PRSummary {
  body: string | null;
  base_branch: string;
  head_branch: string;
  state: string;
  updated_at: string;
  triage_reports: TriageReportDetail[];
}

export interface WSMessage {
  type: "triage_complete" | "triage_progress" | "pong";
  repo: string;
  pr_number: number;
  classification?: string;
  status?: string;
}

// ─── Dashboard response types ────────────────────────────────

/** A single semantic search result — flexible shape, intentional. */
export interface SearchResult {
  file: string;
  score: number;
  snippet?: string;
  [key: string]: unknown;
}

/** A single blast-radius entry (a function that calls a target). */
export interface BlastRadiusEntry {
  caller: string;
  caller_file: string;
  called: string;
  called_file: string;
  [key: string]: unknown;
}

export interface SemanticSearchResponse {
  query: string;
  results: SearchResult[];
}

export interface BlastRadiusResponse {
  file: string;
  affected: BlastRadiusEntry[];
  count: number;
}
