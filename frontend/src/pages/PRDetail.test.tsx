/* Tests for the PRDetail page — header, branches, triage report, approval panel, history. */

import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { PRDetail } from "./PRDetail";

function renderPRDetail(prId = "pr-1") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/pr/${prId}`]}>
        <Routes>
          <Route path="/pr/:prId" element={<PRDetail />} />
          <Route path="/" element={<div>Dashboard Home</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("PRDetail", () => {
  it("shows a loading state initially", () => {
    renderPRDetail();
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("renders the PR title and metadata", async () => {
    renderPRDetail();
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /Add retry logic/i })).toBeInTheDocument();
    });
    expect(screen.getByText("acme/widget#1")).toBeInTheDocument();
    expect(screen.getByText("alice")).toBeInTheDocument();
  });

  it("renders the head and base branches", async () => {
    renderPRDetail();
    await waitFor(() => {
      expect(screen.getByText("feature/retry")).toBeInTheDocument();
    });
    expect(screen.getByText("main")).toBeInTheDocument();
  });

  it("renders additions, deletions, and file count", async () => {
    renderPRDetail();
    await waitFor(() => {
      expect(screen.getByText(/\+50 -10/)).toBeInTheDocument();
    });
    expect(screen.getByText(/2 files/)).toBeInTheDocument();
  });

  it("renders the triage report when present", async () => {
    renderPRDetail();
    await waitFor(() => {
      // The TriageReport component renders the rationale. Use that as
      // the 'report is loaded' signal — it's specific to the report
      // and not duplicated anywhere else.
      expect(
        screen.getByText(/clean, well-tested change/i)
      ).toBeInTheDocument();
    });
  });

  it("renders the approval panel when the report is undecided", async () => {
    renderPRDetail();
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /approve/i })
      ).toBeInTheDocument();
    });
  });

  it("renders the PR body in the description sidebar", async () => {
    renderPRDetail();
    await waitFor(() => {
      expect(screen.getByText(/Description/i)).toBeInTheDocument();
    });
    expect(
      screen.getByText(/exponential backoff to the webhook handler/i)
    ).toBeInTheDocument();
  });

  it("shows a 'not found' state for an unknown PR", async () => {
    renderPRDetail("nonexistent");
    await waitFor(() => {
      expect(screen.getByText(/pr not found/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/back to dashboard/i)).toBeInTheDocument();
  });

  it("has a link back to the dashboard", async () => {
    renderPRDetail();
    await waitFor(() => {
      expect(screen.getAllByText(/back to dashboard/i).length).toBeGreaterThan(0);
    });
  });
});
