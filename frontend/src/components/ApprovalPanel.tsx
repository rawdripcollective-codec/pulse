import { useState } from "react";
import { Check, MessageSquare, X } from "lucide-react";

import { api } from "../api/client";
import type { TriageReportDetail } from "../types";

interface Props {
  report: TriageReportDetail;
  onApproved: () => void;
  onRejected: () => void;
}

export function ApprovalPanel({ report, onApproved, onRejected }: Props) {
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleApprove = async () => {
    setLoading(true);
    setError(null);
    try {
      await api.approveReport(report.id, notes);
      onApproved();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleReject = async () => {
    setLoading(true);
    setError(null);
    try {
      await api.rejectReport(report.id, notes);
      onRejected();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  if (report.approved !== null && report.approved !== undefined) {
    return (
      <div
        className={`p-4 rounded-xl border ${
          report.approved
            ? "bg-emerald-950 border-emerald-800"
            : "bg-red-950 border-red-800"
        }`}
      >
        <div className="flex items-center gap-2">
          {report.approved ? (
            <Check className="w-5 h-5 text-emerald-400" />
          ) : (
            <X className="w-5 h-5 text-red-400" />
          )}
          <span className="font-medium">
            {report.approved ? "Approved" : "Rejected"}
          </span>
          {report.approved_by && <span>by {report.approved_by}</span>}
        </div>
        {report.moderation_notes && (
          <p className="mt-2 text-sm opacity-80">{report.moderation_notes}</p>
        )}
      </div>
    );
  }

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
      <h3 className="font-medium mb-3 flex items-center gap-2">
        <MessageSquare className="w-4 h-4 text-slate-400" />
        Approve or Reject this Report
      </h3>

      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="Moderation notes (optional)..."
        className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm mb-3 resize-none h-20"
      />

      {error && (
        <p className="text-sm text-red-400 mb-3">{error}</p>
      )}

      <div className="flex gap-3">
        <button
          onClick={handleApprove}
          disabled={loading}
          className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          <Check className="w-4 h-4" />
          Approve &amp; Post to GitHub
        </button>
        <button
          onClick={handleReject}
          disabled={loading}
          className="flex items-center gap-2 bg-red-600 hover:bg-red-700 disabled:opacity-50 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          <X className="w-4 h-4" />
          Reject
        </button>
      </div>
    </div>
  );
}
