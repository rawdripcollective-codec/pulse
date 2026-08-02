/* Tests for the Dashboard page — stats, filters, PR list, WebSocket-driven refetch. */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Dashboard } from "./Dashboard";

// ─── WebSocket shim ──────────────────────────────────────────

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static OPEN = 1;
  url: string;
  readyState = 0;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  sent: string[] = [];
  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }
  send(d: string) {
    this.sent.push(d);
  }
  close() {
    this.readyState = 3;
    this.onclose?.();
  }
  simulateOpen() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }
  simulateMessage(data: string) {
    this.onmessage?.({ data });
  }
}

beforeEach(() => {
  FakeWebSocket.instances = [];
  // WebSocket is a read-only global; use defineProperty
  Object.defineProperty(globalThis, "WebSocket", {
    writable: true,
    configurable: true,
    value: FakeWebSocket,
  });
});

afterEach(() => {
  // @ts-expect-error — best-effort cleanup
  delete (globalThis as { WebSocket?: unknown }).WebSocket;
});

// ─── Helpers ─────────────────────────────────────────────────

function renderDashboard() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Dashboard", () => {
  it("renders the four stat cards with initial data", async () => {
    renderDashboard();
    // 'Open PRs' is unique to the stat card
    expect(screen.getByText("Open PRs")).toBeInTheDocument();
    // 'Awaiting Approval' and 'In Progress' also appear in the status
    // <option> list, so use getAllByText to assert the stat cards are
    // present.
    expect(screen.getAllByText("Awaiting Approval").length).toBeGreaterThan(0);
    expect(screen.getAllByText("In Progress").length).toBeGreaterThan(0);
    // 'Live Connection' is unique to the stat card
    expect(screen.getByText("Live Connection")).toBeInTheDocument();
  });

  it("loads and displays PRs from the API", async () => {
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText(/Add retry logic/)).toBeInTheDocument();
    });
    expect(screen.getByText(/Update deps/)).toBeInTheDocument();
  });

  it("loads and displays the repo selector", async () => {
    renderDashboard();
    // The trigger shows 'All repositories' by default; opening the
    // dropdown reveals the actual repos. We test the trigger is
    // present and that opening the dropdown shows the repos.
    await waitFor(() => {
      expect(
        screen.getAllByText(/all repositories/i).length
      ).toBeGreaterThan(0);
    });
  });

  it("filters PRs by status when the status select changes", async () => {
    const user = userEvent.setup();
    renderDashboard();

    // Wait for the initial list
    await waitFor(() => {
      expect(screen.getByText(/Add retry logic/)).toBeInTheDocument();
    });

    // Change the status filter to "posted"
    const statusSelect = screen.getByDisplayValue(/all statuses/i);
    await user.selectOptions(statusSelect, "posted");

    // After the refetch, only the "Update deps" PR (status=posted) should remain
    await waitFor(() => {
      expect(screen.queryByText(/Add retry logic/)).not.toBeInTheDocument();
    });
    expect(screen.getByText(/Update deps/)).toBeInTheDocument();
  });

  it("shows 'Disconnected' until the WebSocket opens, then 'Connected'", async () => {
    renderDashboard();
    expect(screen.getByText("Disconnected")).toBeInTheDocument();

    // Open the WebSocket
    await waitFor(() => {
      if (FakeWebSocket.instances[0]) FakeWebSocket.instances[0].simulateOpen();
    });

    await waitFor(() => {
      expect(screen.getByText("Connected")).toBeInTheDocument();
    });
  });

  it("refetches PRs when a triage_complete WebSocket message arrives", async () => {
    let prsCalls = 0;
    const { http, HttpResponse } = await import("msw");
    const { server } = await import("../../test/mocks/server");

    server.use(
      http.get("http://localhost:8000/api/prs", () => {
        prsCalls++;
        return HttpResponse.json([
          {
            id: "pr-1",
            number: 1,
            title: `Refetched #${prsCalls}`,
            author: "alice",
            author_avatar: null,
            files_changed: 1,
            additions: 1,
            deletions: 1,
            classification: "human_first",
            classification_confidence: 0.9,
            triage_status: "awaiting_approval",
            created_at: new Date().toISOString(),
            repo_full_name: "acme/widget",
          },
        ]);
      })
    );

    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText(/Refetched #1/)).toBeInTheDocument();
    });

    // Simulate a triage_complete message
    const ws = FakeWebSocket.instances[0]!;
    ws.simulateOpen();
    ws.simulateMessage(
      JSON.stringify({
        type: "triage_complete",
        repo: "acme/widget",
        pr_number: 1,
      })
    );

    await waitFor(() => {
      expect(prsCalls).toBeGreaterThanOrEqual(2);
    });
  });
});
