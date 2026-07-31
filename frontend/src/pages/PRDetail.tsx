import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, GitBranch, GitMerge, User } from "lucide-react";

import { api } from "../api/client";
import { ApprovalPanel } from "../components/ApprovalPanel";
import { BlastRadiusGraph } from "../components/BlastRadiusGraph";
import { TriageReport } from "../components/TriageReport";

export function PRDetail() {
  const { prId } = useParams<{ prId: string }>();

  const { data: pr, isLoading, refetch } = useQuery({
    queryKey: ["pr", prId],
    queryFn: () => api.getPR(prId!),
    enabled: !!prId,
  });

  if (isLoading) {
    return <div className="text-center py-16 text-slate-500">Loading…</div>;
  }

  if (!pr) {
    return (
      <div className="text-center py-16 text-slate-500">
        <p>PR not found</p>
        <Link to="/" className="text-cyan-400 hover:underline mt-2 inline-block">
          ← Back to dashboard
        </Link>
      </div>
    );
  }

  const latestReport = pr.triage_reports[0];
  const affectedModules = latestReport?.affected_modules || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <Link
          to="/"
          className="text-sm text-slate-400 hover:text-slate-200 inline-flex items-center gap-1 mb-3"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to dashboard
        </Link>

        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 text-sm text-slate-500 mb-2">
              <span className="font-mono">
                {pr.repo_full_name}#{pr.number}
              </span>
              <span>·</span>
              <span className="flex items-center gap-1">
                <User className="w-3 h-3" />
                {pr.author}
              </span>
            </div>
            <h1 className="text-2xl font-semibold text-slate-100">
              {pr.title}
            </h1>
          </div>
        </div>

        {/* Branches */}
        <div className="flex items-center gap-3 mt-3 text-sm text-slate-400">
          <span className="flex items-center gap-1">
            <GitBranch className="w-3.5 h-3.5" />
            {pr.head_branch}
          </span>
          <GitMerge className="w-3.5 h-3.5" />
          <span className="flex items-center gap-1">
            <GitBranch className="w-3.5 h-3.5" />
            {pr.base_branch}
          </span>
          <span className="ml-auto text-xs text-slate-500">
            +{pr.additions} -{pr.deletions} · {pr.files_changed} files
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main column */}
        <div className="lg:col-span-2 space-y-6">
          {latestReport ? (
            <>
              <TriageReport report={latestReport} />
              <ApprovalPanel
                report={latestReport}
                onApproved={() => refetch()}
                onRejected={() => refetch()}
              />
            </>
          ) : (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center text-slate-500">
              <p>No triage report yet for this PR</p>
              <p className="text-sm mt-1">
                Triage status: {pr.triage_status.replace("_", " ")}
              </p>
            </div>
          )}

          {/* Blast radius */}
          {affectedModules.length > 0 && (
            <BlastRadiusGraph
              modules={affectedModules}
              changedFiles={[]}
            />
          )}
        </div>

        {/* Sidebar */}
        <aside className="space-y-4">
          {pr.body && (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
              <h3 className="font-medium mb-2">Description</h3>
              <div className="text-sm text-slate-300 whitespace-pre-wrap">
                {pr.body}
              </div>
            </div>
          )}

          {/* Report history */}
          {pr.triage_reports.length > 1 && (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
              <h3 className="font-medium mb-3">Report History</h3>
              <ul className="space-y-2 text-sm">
                {pr.triage_reports.map((r) => (
                  <li
                    key={r.id}
                    className="flex items-center justify-between"
                  >
                    <span>{r.classification.replace("_", " ")}</span>
                    <span className="text-xs text-slate-500">
                      {(r.classification_confidence * 100).toFixed(0)}%
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
