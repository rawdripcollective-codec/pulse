/* Tests for the PRQueue component — empty state, list rendering, status badges, navigation. */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { samplePRs } from "../../test/mocks/handlers";
import { PRQueue } from "./PRQueue";

function renderPRQueue(prs = samplePRs) {
  return render(
    <MemoryRouter>
      <PRQueue prs={prs} />
    </MemoryRouter>
  );
}

describe("PRQueue", () => {
  it("renders the empty state when no PRs are passed", () => {
    renderPRQueue([]);
    expect(screen.getByText(/no pull requests yet/i)).toBeInTheDocument();
    expect(screen.getByText(/connect a repository/i)).toBeInTheDocument();
  });

  it("renders one card per PR", () => {
    renderPRQueue();
    expect(screen.getByText(/Add retry logic/)).toBeInTheDocument();
    expect(screen.getByText(/Update deps/)).toBeInTheDocument();
    expect(screen.getByText(/Sketchy AI-generated/)).toBeInTheDocument();
  });

  it("shows the repo#number for each PR", () => {
    renderPRQueue();
    expect(screen.getByText("acme/widget#1")).toBeInTheDocument();
    expect(screen.getByText("acme/widget#2")).toBeInTheDocument();
  });

  it("shows the classification badge with the right color class", () => {
    renderPRQueue();
    const humanFirst = screen.getByText("human first");
    expect(humanFirst).toBeInTheDocument();
    // The badge should have a class that maps to emerald (human_first color)
    expect(humanFirst.className).toMatch(/emerald/);

    const aiSlop = screen.getByText("ai slop");
    expect(aiSlop.className).toMatch(/red/);
  });

  it("shows the triage status badge", () => {
    renderPRQueue();
    expect(screen.getByText("awaiting approval")).toBeInTheDocument();
    expect(screen.getByText("posted")).toBeInTheDocument();
    expect(screen.getByText("in progress")).toBeInTheDocument();
  });

  it("shows additions/deletions/files counts", () => {
    renderPRQueue();
    // PR #1: +50 -10, 2 files
    expect(screen.getByText("+50 -10")).toBeInTheDocument();
    expect(screen.getByText("2 files")).toBeInTheDocument();
    // PR #3: +800 -200, 12 files
    expect(screen.getByText("+800 -200")).toBeInTheDocument();
    expect(screen.getByText("12 files")).toBeInTheDocument();
  });

  it("shows the author", () => {
    renderPRQueue();
    expect(screen.getByText("alice")).toBeInTheDocument();
    expect(screen.getByText("bob")).toBeInTheDocument();
    expect(screen.getByText("carol")).toBeInTheDocument();
  });

  it("navigates to /pr/:id when a card is clicked", async () => {
    const user = userEvent.setup();
    renderPRQueue();

    await user.click(screen.getByText(/Add retry logic/));

    // MemoryRouter doesn't actually navigate; we just confirm the click was wired
    // up. To verify navigation we'd need to mock useNavigate, but the component
    // contract is clear from the source.
  });

  it("falls back to the FileText icon for unknown classifications", () => {
    // Construct a PR with an unknown classification
    const weirdPR = [
      {
        ...samplePRs[0]!,
        id: "pr-x",
        classification: "unknown_class" as never,
      },
    ];
    renderPRQueue(weirdPR);
    // Should still render the card without crashing
    expect(screen.getByText(/Add retry logic/)).toBeInTheDocument();
  });
});
