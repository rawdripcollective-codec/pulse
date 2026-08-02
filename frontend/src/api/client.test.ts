/* Tests for the API client — verify each method constructs the right URL
   and handles the response. Uses MSW to intercept HTTP calls. */

import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";

import { api } from "./client";
import { server } from "../../test/mocks/server";

describe("api client", () => {
  beforeEach(() => {
    // Default: all requests succeed with empty bodies
  });

  afterEach(() => {
    server.resetHandlers();
  });

  describe("listRepos", () => {
    it("hits /repos and returns the list", async () => {
      const result = await api.listRepos();
      expect(Array.isArray(result)).toBe(true);
      expect(result[0]!.full_name).toBe("acme/widget");
    });
  });

  describe("listPRs", () => {
    it("hits /prs with no params when called with no args", async () => {
      let calledUrl = "";
      server.use(
        http.get("http://localhost:8000/api/prs", ({ request }) => {
          calledUrl = request.url;
          return HttpResponse.json([]);
        })
      );
      await api.listPRs();
      expect(calledUrl).toMatch(/\/api\/prs\?/);
    });

    it("passes repo_full_name and triage_status as query params", async () => {
      let calledUrl = "";
      server.use(
        http.get("http://localhost:8000/api/prs", ({ request }) => {
          calledUrl = request.url;
          return HttpResponse.json([]);
        })
      );
      await api.listPRs("acme/widget", "awaiting_approval");
      expect(calledUrl).toContain("repo_full_name=acme%2Fwidget");
      expect(calledUrl).toContain("triage_status=awaiting_approval");
    });

    it("URL-encodes the repo name (slashes etc.)", async () => {
      let calledUrl = "";
      server.use(
        http.get("http://localhost:8000/api/prs", ({ request }) => {
          calledUrl = request.url;
          return HttpResponse.json([]);
        })
      );
      await api.listPRs("org/with/slashes");
      expect(calledUrl).toContain("org%2Fwith%2Fslashes");
    });
  });

  describe("reindexRepo", () => {
    it("URL-encodes the repo name in the path", async () => {
      let calledUrl = "";
      server.use(
        http.post(
          "http://localhost:8000/api/repos/:fullName/reindex",
          ({ request }) => {
            calledUrl = request.url;
            return HttpResponse.json({ status: "queued", repo: "acme/widget" });
          }
        )
      );
      const result = await api.reindexRepo("acme/widget");
      expect(calledUrl).toContain("acme%2Fwidget");
      expect(result).toEqual({ status: "queued", repo: "acme/widget" });
    });

    it("uses POST method", async () => {
      let method = "";
      server.use(
        http.post(
          "http://localhost:8000/api/repos/:fullName/reindex",
          ({ request }) => {
            method = request.method;
            return HttpResponse.json({ status: "queued", repo: "x" });
          }
        )
      );
      await api.reindexRepo("x/y");
      expect(method).toBe("POST");
    });
  });

  describe("approveReport / rejectReport", () => {
    it("approveReport sends a JSON body with report_id and notes", async () => {
      let captured: any = null;
      server.use(
        http.post("http://localhost:8000/api/triage/approve", async ({ request }) => {
          captured = await request.json();
          return HttpResponse.json({ status: "approved" });
        })
      );
      const result = await api.approveReport("r-1", "ok");
      expect(captured).toEqual({ report_id: "r-1", notes: "ok" });
      expect(result).toEqual({ status: "approved" });
    });

    it("approveReport defaults notes to empty string", async () => {
      let captured: any = null;
      server.use(
        http.post("http://localhost:8000/api/triage/approve", async ({ request }) => {
          captured = await request.json();
          return HttpResponse.json({ status: "approved" });
        })
      );
      await api.approveReport("r-1");
      expect(captured.notes).toBe("");
    });

    it("rejectReport sends a JSON body", async () => {
      let captured: any = null;
      server.use(
        http.post("http://localhost:8000/api/triage/reject", async ({ request }) => {
          captured = await request.json();
          return HttpResponse.json({ status: "rejected" });
        })
      );
      await api.rejectReport("r-1", "nope");
      expect(captured).toEqual({ report_id: "r-1", notes: "nope" });
    });
  });

  describe("error handling", () => {
    it("throws a descriptive error on non-2xx responses", async () => {
      server.use(
        http.get("http://localhost:8000/api/repos", () =>
          new HttpResponse("boom", { status: 500, statusText: "Server Error" })
        )
      );
      await expect(api.listRepos()).rejects.toThrow(/API error: 500/);
    });

    it("includes the response text in the error", async () => {
      server.use(
        http.get("http://localhost:8000/api/repos", () =>
          new HttpResponse("disk full", { status: 500 })
        )
      );
      await expect(api.listRepos()).rejects.toThrow(/disk full/);
    });
  });

  describe("dashboard endpoints", () => {
    it("getStats hits /dashboard/stats", async () => {
      const stats = await api.getStats();
      expect(stats).toHaveProperty("open_prs");
      expect(stats).toHaveProperty("awaiting_approval");
    });

    it("semanticSearch passes repo, q, top_k", async () => {
      let calledUrl = "";
      server.use(
        http.get(
          "http://localhost:8000/api/dashboard/search",
          ({ request }) => {
            calledUrl = request.url;
            return HttpResponse.json({ query: "auth", results: [] });
          }
        )
      );
      await api.semanticSearch("acme/widget", "auth", 5);
      expect(calledUrl).toContain("repo=acme%2Fwidget");
      expect(calledUrl).toContain("q=auth");
      expect(calledUrl).toContain("top_k=5");
    });

    it("getBlastRadius passes repo and file", async () => {
      let calledUrl = "";
      server.use(
        http.get(
          "http://localhost:8000/api/dashboard/blast-radius",
          ({ request }) => {
            calledUrl = request.url;
            return HttpResponse.json({ file: "auth.py", affected: [], count: 0 });
          }
        )
      );
      await api.getBlastRadius("acme/widget", "src/auth.py");
      expect(calledUrl).toContain("repo=acme%2Fwidget");
      expect(calledUrl).toContain("file=src%2Fauth.py");
    });
  });
});
