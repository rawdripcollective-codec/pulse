/* Hook for managing triage state in the PR detail view. */

import { useCallback, useState } from "react";

import { api } from "../api/client";
import type { TriageReportDetail } from "../types";

export function useTriage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const approve = useCallback(
    async (report: TriageReportDetail, notes: string = "") => {
      setLoading(true);
      setError(null);
      try {
        await api.approveReport(report.id, notes);
        return true;
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        return false;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const reject = useCallback(
    async (report: TriageReportDetail, notes: string = "") => {
      setLoading(true);
      setError(null);
      try {
        await api.rejectReport(report.id, notes);
        return true;
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        return false;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  return { approve, reject, loading, error };
}
