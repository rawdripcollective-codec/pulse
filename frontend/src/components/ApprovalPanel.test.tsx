/* Tests for the ApprovalPanel — approve/reject flow, notes, error handling, decision state. */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { server } from "../../test/mocks/server";
import { sampleReport } from "../../test/mocks/handlers";
import { ApprovalPanel } from "./ApprovalPanel";

describe("ApprovalPanel", () => {
  it("renders the approve and reject buttons when report is undecided", () => {
    render(
      <ApprovalPanel
        report={sampleReport}
        onApproved={() => {}}
        onRejected={() => {}}
      />
    );
    expect(
      screen.getByRole("button", { name: /approve/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /reject/i })
    ).toBeInTheDocument();
  });

  it("renders a 'notes' textarea", () => {
    render(
      <ApprovalPanel
        report={sampleReport}
        onApproved={() => {}}
        onRejected={() => {}}
      />
    );
    expect(
      screen.getByPlaceholderText(/moderation notes/i)
    ).toBeInTheDocument();
  });

  it("approve button sends notes to /triage/approve and calls onApproved", async () => {
    const user = userEvent.setup();
    let captured: { report_id: string; notes: string } | null = null;
    const onApproved = vi.fn();
    server.use(
      http.post(
        "http://localhost:8000/api/triage/approve",
        async ({ request }) => {
          captured = (await request.json()) as { report_id: string; notes: string };
          return HttpResponse.json({ status: "approved" });
        }
      )
    );

    render(
      <ApprovalPanel
        report={sampleReport}
        onApproved={onApproved}
        onRejected={() => {}}
      />
    );

    await user.type(
      screen.getByPlaceholderText(/moderation notes/i),
      "looks great"
    );
    await user.click(screen.getByRole("button", { name: /approve/i }));

    await waitFor(() => {
      expect(onApproved).toHaveBeenCalled();
    });
    expect(captured).toEqual({ report_id: "report-1", notes: "looks great" });
  });

  it("reject button sends notes to /triage/reject and calls onRejected", async () => {
    const user = userEvent.setup();
    let captured: { report_id: string; notes: string } | null = null;
    const onRejected = vi.fn();
    server.use(
      http.post(
        "http://localhost:8000/api/triage/reject",
        async ({ request }) => {
          captured = (await request.json()) as { report_id: string; notes: string };
          return HttpResponse.json({ status: "rejected" });
        }
      )
    );

    render(
      <ApprovalPanel
        report={sampleReport}
        onApproved={() => {}}
        onRejected={onRejected}
      />
    );

    await user.click(screen.getByRole("button", { name: /reject/i }));

    await waitFor(() => {
      expect(onRejected).toHaveBeenCalled();
    });
    expect(captured).toEqual({ report_id: "report-1", notes: "" });
  });

  it("displays an error message when the API fails", async () => {
    const user = userEvent.setup();
    server.use(
      http.post("http://localhost:8000/api/triage/approve", () =>
        new HttpResponse("forbidden", { status: 403 })
      )
    );

    render(
      <ApprovalPanel
        report={sampleReport}
        onApproved={() => {}}
        onRejected={() => {}}
      />
    );

    await user.click(screen.getByRole("button", { name: /approve/i }));

    await waitFor(() => {
      expect(screen.getByText(/API error: 403/)).toBeInTheDocument();
    });
  });

  it("renders the approved state when report.approved is true", () => {
    const approvedReport = {
      ...sampleReport,
      approved: true,
      approved_by: "alice",
    };
    render(
      <ApprovalPanel
        report={approvedReport}
        onApproved={() => {}}
        onRejected={() => {}}
      />
    );
    expect(screen.getByText(/approved/i)).toBeInTheDocument();
    expect(screen.getByText(/by alice/)).toBeInTheDocument();
    // Approve/Reject buttons should not be present in the decided state
    expect(
      screen.queryByRole("button", { name: /approve/i })
    ).not.toBeInTheDocument();
  });

  it("renders the rejected state when report.approved is false", () => {
    const rejectedReport = {
      ...sampleReport,
      approved: false,
      approved_by: "bob",
    };
    render(
      <ApprovalPanel
        report={rejectedReport}
        onApproved={() => {}}
        onRejected={() => {}}
      />
    );
    expect(screen.getByText(/rejected/i)).toBeInTheDocument();
    expect(screen.getByText(/by bob/)).toBeInTheDocument();
  });
});
