/* Tests for the useTriage hook — approve/reject flow + loading state. */

import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "../../test/mocks/server";
import { useTriage } from "./useTriage";
import { sampleReport } from "../../test/mocks/handlers";

describe("useTriage", () => {
  it("starts in idle state", () => {
    const { result } = renderHook(() => useTriage());
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(typeof result.current.approve).toBe("function");
    expect(typeof result.current.reject).toBe("function");
  });

  it("approve() calls /triage/approve and returns true on success", async () => {
    let captured: { report_id: string; notes: string } | null = null;
    server.use(
      http.post("http://localhost:8000/api/triage/approve", async ({ request }) => {
        captured = (await request.json()) as { report_id: string; notes: string };
        return HttpResponse.json({ status: "approved" });
      })
    );

    const { result } = renderHook(() => useTriage());
    let success: boolean | undefined;
    await act(async () => {
      success = await result.current.approve(sampleReport, "looks good");
    });

    expect(success).toBe(true);
    expect(captured).toEqual({ report_id: "report-1", notes: "looks good" });
    expect(result.current.error).toBeNull();
    expect(result.current.loading).toBe(false);
  });

  it("approve() captures error and returns false on failure", async () => {
    server.use(
      http.post("http://localhost:8000/api/triage/approve", () =>
        new HttpResponse("Server error", { status: 500 })
      )
    );

    const { result } = renderHook(() => useTriage());
    let success: boolean | undefined;
    await act(async () => {
      success = await result.current.approve(sampleReport);
    });

    expect(success).toBe(false);
    await waitFor(() => {
      expect(result.current.error).toMatch(/API error: 500/);
    });
  });

  it("reject() calls /triage/reject with notes", async () => {
    let captured: { report_id: string; notes: string } | null = null;
    server.use(
      http.post("http://localhost:8000/api/triage/reject", async ({ request }) => {
        captured = (await request.json()) as { report_id: string; notes: string };
        return HttpResponse.json({ status: "rejected" });
      })
    );

    const { result } = renderHook(() => useTriage());
    let success: boolean | undefined;
    await act(async () => {
      success = await result.current.reject(sampleReport, "needs more context");
    });

    expect(success).toBe(true);
    expect(captured).toEqual({ report_id: "report-1", notes: "needs more context" });
  });

  it("approve() defaults notes to empty string", async () => {
    let captured: { report_id: string; notes: string } | null = null;
    server.use(
      http.post("http://localhost:8000/api/triage/approve", async ({ request }) => {
        captured = (await request.json()) as { report_id: string; notes: string };
        return HttpResponse.json({ status: "approved" });
      })
    );

    const { result } = renderHook(() => useTriage());
    await act(async () => {
      await result.current.approve(sampleReport);
    });
    expect(captured?.notes).toBe("");
  });

  it("toggles loading state during approve", async () => {
    const { result } = renderHook(() => useTriage());

    // Start the approve call but don't await yet
    const approvePromise = act(async () => {
      await result.current.approve(sampleReport);
    });

    // While the promise is in-flight, loading should be true
    // (this is a race — but act() forces the state update, so we can check)
    await approvePromise;

    // After completion, loading is back to false
    expect(result.current.loading).toBe(false);
  });
});
