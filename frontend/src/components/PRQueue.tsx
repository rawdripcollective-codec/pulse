import { useNavigate } from "react-router-dom";
import { formatDistanceToNow } from "date-fns";
import {
  AlertTriangle,
  Bot,
  Clock,
  FileText,
  Shield,
  User,
} from "lucide-react";

import type { PRSummary } from "../types";

const classificationIcons: Record<string, typeof AlertTriangle> = {
  human_first: User,
  ai_assisted: Bot,
  ai_slop: AlertTriangle,
  trivial: FileText,
  high_risk: Shield,
};

const classificationColors: Record<string, string> = {
  human_first: "text-emerald-400 bg-emerald-950 border-emerald-900",
  ai_assisted: "text-blue-400 bg-blue-950 border-blue-900",
  ai_slop: "text-red-400 bg-red-950 border-red-900",
  trivial: "text-slate-400 bg-slate-800 border-slate-700",
  high_risk: "text-amber-400 bg-amber-950 border-amber-900",
};

export function PRQueue({ prs }: { prs: PRSummary[] }) {
  const navigate = useNavigate();

  if (prs.length === 0) {
    return (
      <div className="text-center py-16 text-slate-500">
        <Clock className="w-12 h-12 mx-auto mb-4 opacity-50" />
        <p className="text-lg">No pull requests yet</p>
        <p className="text-sm mt-1">Connect a repository to get started</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {prs.map((pr) => {
        const Icon = pr.classification
          ? classificationIcons[pr.classification] || FileText
          : Clock;

        return (
          <div
            key={pr.id}
            onClick={() => navigate(`/pr/${pr.id}`)}
            className="bg-slate-900 border border-slate-800 rounded-xl p-4 hover:border-slate-700 cursor-pointer transition-colors"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm text-slate-500 font-mono">
                    {pr.repo_full_name}#{pr.number}
                  </span>
                  {pr.classification && (
                    <span
                      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border ${classificationColors[pr.classification]}`}
                    >
                      <Icon className="w-3 h-3" />
                      {pr.classification.replace("_", " ")}
                    </span>
                  )}
                </div>
                <h3 className="font-medium text-slate-100 truncate">
                  {pr.title}
                </h3>
                <div className="flex items-center gap-3 mt-2 text-xs text-slate-500">
                  <span>{pr.author}</span>
                  <span>
                    +{pr.additions} -{pr.deletions}
                  </span>
                  <span>{pr.files_changed} files</span>
                  <span>
                    {formatDistanceToNow(new Date(pr.created_at), {
                      addSuffix: true,
                    })}
                  </span>
                </div>
              </div>

              <div className="flex-shrink-0">
                <TriageStatusBadge status={pr.triage_status} />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function TriageStatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    pending: "bg-slate-800 text-slate-400 border-slate-700",
    in_progress:
      "bg-indigo-950 text-indigo-400 border-indigo-800",
    awaiting_approval:
      "bg-amber-950 text-amber-400 border-amber-800",
    approved: "bg-emerald-950 text-emerald-400 border-emerald-800",
    rejected: "bg-red-950 text-red-400 border-red-800",
    posted: "bg-emerald-950 text-emerald-400 border-emerald-800",
  };

  return (
    <span
      className={`px-2.5 py-1 rounded-full text-xs font-medium border ${styles[status] || styles.pending}`}
    >
      {status.replace("_", " ")}
    </span>
  );
}
