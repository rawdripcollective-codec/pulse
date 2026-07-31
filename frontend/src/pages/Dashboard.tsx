import { useCallback, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import { PRQueue } from "../components/PRQueue";
import { RepoSelector } from "../components/RepoSelector";
import { useWebSocket } from "../hooks/useWebSocket";
import type { PRSummary, WSMessage } from "../types";

export function Dashboard() {
  const [selectedRepo, setSelectedRepo] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");

  const { data: repos } = useQuery({
    queryKey: ["repos"],
    queryFn: api.listRepos,
  });

  const {
    data: prs,
    refetch: refetchPRs,
    isLoading,
  } = useQuery({
    queryKey: ["prs", selectedRepo, statusFilter],
    queryFn: () =>
      api.listPRs(
        selectedRepo || undefined,
        statusFilter || undefined
      ),
    enabled: !!repos,
  });

  const { data: stats } = useQuery({
    queryKey: ["stats"],
    queryFn: api.getStats,
    refetchInterval: 15000,
  });

  // Real-time WebSocket updates
  const handleWSMessage = useCallback(
    (msg: WSMessage) => {
      if (msg.type === "triage_complete") {
        refetchPRs();
      }
    },
    [refetchPRs]
  );

  const { connected } = useWebSocket(handleWSMessage);

  // Count by triage status (from current view)
  const awaitingApproval =
    prs?.filter((p) => p.triage_status === "awaiting_approval").length || 0;
  const inProgress =
    prs?.filter((p) => p.triage_status === "in_progress").length || 0;

  return (
    <div>
      {/* Stats bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard
          label="Open PRs"
          value={prs?.length || 0}
          color="blue"
        />
        <StatCard
          label="Awaiting Approval"
          value={stats?.awaiting_approval ?? awaitingApproval}
          color="amber"
        />
        <StatCard
          label="In Progress"
          value={stats?.in_progress ?? inProgress}
          color="indigo"
        />
        <StatCard
          label="Live Connection"
          value={connected ? "Connected" : "Disconnected"}
          color={connected ? "emerald" : "red"}
        />
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-4 mb-6">
        <RepoSelector
          repos={repos || []}
          selected={selectedRepo}
          onSelect={setSelectedRepo}
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm"
        >
          <option value="">All statuses</option>
          <option value="awaiting_approval">Awaiting Approval</option>
          <option value="in_progress">In Progress</option>
          <option value="pending">Pending</option>
          <option value="posted">Posted</option>
          <option value="rejected">Rejected</option>
        </select>
      </div>

      {/* PR Queue */}
      {isLoading ? (
        <div className="text-center py-16 text-slate-500">Loading…</div>
      ) : (
        <PRQueue prs={prs || ([] as PRSummary[])} />
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  color,
}: {
  label: string;
  value: number | string;
  color: "blue" | "amber" | "indigo" | "emerald" | "red";
}) {
  const colorMap = {
    blue: "bg-blue-950 border-blue-800 text-blue-300",
    amber: "bg-amber-950 border-amber-800 text-amber-300",
    indigo: "bg-indigo-950 border-indigo-800 text-indigo-300",
    emerald: "bg-emerald-950 border-emerald-800 text-emerald-300",
    red: "bg-red-950 border-red-800 text-red-300",
  };

  return (
    <div
      className={`rounded-xl border p-4 ${colorMap[color]}`}
    >
      <div className="text-sm opacity-80">{label}</div>
      <div className="text-2xl font-bold mt-1">{value}</div>
    </div>
  );
}
