/* Tests for the Header component — branding and navigation links. */

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { Header } from "./Header";

describe("Header", () => {
  function renderHeader() {
    return render(
      <MemoryRouter>
        <Header />
      </MemoryRouter>
    );
  }

  it("renders the Pulse brand and tagline", () => {
    renderHeader();
    expect(
      screen.getByRole("heading", { name: /pulse/i })
    ).toBeInTheDocument();
    expect(screen.getByText(/agentic pr triage/i)).toBeInTheDocument();
  });

  it("renders a link to the dashboard home", () => {
    renderHeader();
    const homeLink = screen.getByRole("link", { name: /pulse/i });
    expect(homeLink).toHaveAttribute("href", "/");
  });

  it("renders a link to the GitHub repository", () => {
    renderHeader();
    const ghLink = screen.getByRole("link", { name: /github repository/i });
    expect(ghLink).toHaveAttribute("href", expect.stringContaining("github.com"));
    expect(ghLink).toHaveAttribute("target", "_blank");
    expect(ghLink).toHaveAttribute("rel", "noreferrer");
  });
});
