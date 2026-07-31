import { formatDistanceToNow } from "date-fns";
import { Clock, FileText, Zap } from "lucide-react";

import type { TriageReportDetail } from "../types";

interface Props {
  report: TriageReportDetail;
}

export function TriageReport({ report }: Props) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <FileText className="w-5 h-5 text-cyan-400" />
          Triage Report
        </h2>
        <span className="text-xs text-slate-500 flex items-center gap-1">
          <Clock className="w-3 h-3" />
          {formatDistanceToNow(new Date(report.created_at), { addSuffix: true })}
        </span>
      </div>

      {/* Classification banner */}
      <div className="mb-4 p-3 rounded-lg bg-slate-800/50 border border-slate-700">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-500 uppercase tracking-wide">
              Classification
            </div>
            <div className="text-base font-medium mt-0.5">
              {report.classification.replace("_", " ")}
            </div>
          </div>
          <div className="text-right">
            <div className="text-xs text-slate-500 uppercase tracking-wide">
              Confidence
            </div>
            <div className="text-base font-medium mt-0.5">
              {(report.classification_confidence * 100).toFixed(0)}%
            </div>
          </div>
        </div>
        {report.classification_rationale && (
          <p className="text-sm text-slate-300 mt-3 leading-relaxed">
            {report.classification_rationale}
          </p>
        )}
      </div>

      {/* Blast radius score */}
      {report.blast_radius_score !== null && (
        <div className="mb-4">
          <div className="flex items-center justify-between text-sm mb-1.5">
            <span className="text-slate-400 flex items-center gap-1.5">
              <Zap className="w-3.5 h-3.5" />
              Blast Radius
            </span>
            <span className="font-medium">
              {(report.blast_radius_score * 100).toFixed(0)}%
            </span>
          </div>
          <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full ${
                report.blast_radius_score > 0.5
                  ? "bg-red-500"
                  : report.blast_radius_score > 0.2
                    ? "bg-amber-500"
                    : "bg-emerald-500"
              }`}
              style={{
                width: `${Math.min(report.blast_radius_score * 100, 100)}%`,
              }}
            />
          </div>
        </div>
      )}

      {/* Summary */}
      <div className="prose prose-invert prose-sm max-w-none">
        <div className="whitespace-pre-wrap text-slate-200 leading-relaxed">
          {report.summary}
        </div>
      </div>

      {/* Metadata footer */}
      {(report.suggested_action || report.suggested_reviewer) && (
        <div className="mt-4 pt-4 border-t border-slate-800 flex flex-wrap gap-4 text-xs">
          {report.suggested_action && (
            <div>
              <span className="text-slate-500">Suggested action: </span>
              <span className="font-medium text-slate-200">
                {report.suggested_action}
              </span>
            </div>
          )}
          {report.suggested_reviewer && (
            <div>
              <span className="text-slate-500">Suggested reviewer: </span>
              <span className="font-medium text-slate-200">
                {report.suggested_reviewer}
              </span>
            </div>
          )}
          {report.processing_time_ms !== null && (
            <div>
              <span className="text-slate-500">Generated in: </span>
              <span className="font-medium text-slate-200">
                {report.processing_time_ms}ms
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
