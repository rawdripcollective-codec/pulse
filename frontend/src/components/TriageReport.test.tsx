/* Tests for the TriageReport component — classification, blast radius, metadata. */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { sampleReport } from "../../test/mocks/handlers";
import { TriageReport } from "./TriageReport";

describe("TriageReport", () => {
  it("renders the classification label", () => {
    render(<TriageReport report={sampleReport} />);
    // The classification is rendered as "human first" (underscore replaced)
    const labels = screen.getAllByText("human first");
    expect(labels.length).toBeGreaterThan(0);
  });

  it("renders the confidence as a percentage", () => {
    render(<TriageReport report={sampleReport} />);
    expect(screen.getByText("92%")).toBeInTheDocument();
  });

  it("renders the rationale when present", () => {
    render(<TriageReport report={sampleReport} />);
    expect(
      screen.getByText(/clean, well-tested change/i)
    ).toBeInTheDocument();
  });

  it("renders the summary body", () => {
    render(<TriageReport report={sampleReport} />);
    expect(
      screen.getByText(/adds retry logic to the webhook handler/i)
    ).toBeInTheDocument();
  });

  it("renders the blast radius bar when score is set", () => {
    render(<TriageReport report={sampleReport} />);
    expect(screen.getByText(/blast radius/i)).toBeInTheDocument();
    // 0.12 * 100 = 12%
    expect(screen.getByText("12%")).toBeInTheDocument();
  });

  it("uses red bar for blast radius > 0.5", () => {
    const report = { ...sampleReport, blast_radius_score: 0.8 };
    render(<TriageReport report={report} />);
    const bar = document.querySelector(".h-full.rounded-full");
    expect(bar?.className).toMatch(/red/);
  });

  it("uses amber bar for blast radius between 0.2 and 0.5", () => {
    const report = { ...sampleReport, blast_radius_score: 0.3 };
    render(<TriageReport report={report} />);
    const bar = document.querySelector(".h-full.rounded-full");
    expect(bar?.className).toMatch(/amber/);
  });

  it("uses emerald bar for blast radius <= 0.2", () => {
    render(<TriageReport report={sampleReport} />); // score 0.12
    const bar = document.querySelector(".h-full.rounded-full");
    expect(bar?.className).toMatch(/emerald/);
  });

  it("omits the blast radius block when score is null", () => {
    const report = { ...sampleReport, blast_radius_score: null };
    render(<TriageReport report={report} />);
    expect(screen.queryByText(/blast radius/i)).not.toBeInTheDocument();
  });

  it("renders the suggested action and reviewer when present", () => {
    render(<TriageReport report={sampleReport} />);
    expect(screen.getByText(/suggested action/i)).toBeInTheDocument();
    expect(screen.getByText("approve")).toBeInTheDocument();
    expect(screen.getByText(/suggested reviewer/i)).toBeInTheDocument();
    expect(screen.getByText("Backend platform")).toBeInTheDocument();
  });

  it("renders the processing time when present", () => {
    render(<TriageReport report={sampleReport} />);
    expect(screen.getByText(/generated in/i)).toBeInTheDocument();
    expect(screen.getByText("1240ms")).toBeInTheDocument();
  });
});
