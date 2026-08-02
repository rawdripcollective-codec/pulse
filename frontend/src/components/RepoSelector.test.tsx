/* Tests for the RepoSelector component — render, open/close, selection. */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { sampleRepos } from "../../test/mocks/handlers";
import { RepoSelector } from "./RepoSelector";

describe("RepoSelector", () => {
  it("shows the current repo name when one is selected", () => {
    render(
      <RepoSelector
        repos={sampleRepos}
        selected="acme/widget"
        onSelect={() => {}}
      />
    );
    expect(screen.getByText("acme/widget")).toBeInTheDocument();
  });

  it("shows 'All repositories' when no repo is selected", () => {
    render(
      <RepoSelector
        repos={sampleRepos}
        selected=""
        onSelect={() => {}}
      />
    );
    const buttons = screen.getAllByText("All repositories");
    expect(buttons.length).toBeGreaterThan(0);
  });

  it("opens the dropdown and shows all repos + 'All repositories'", async () => {
    const user = userEvent.setup();
    render(
      <RepoSelector
        repos={sampleRepos}
        selected=""
        onSelect={() => {}}
      />
    );

    // The dropdown is closed — no repo list items visible yet (besides the trigger).
    expect(screen.queryByText("acme/gizmo")).not.toBeInTheDocument();

    // Click the trigger to open
    await user.click(screen.getByRole("button"));

    // Now all repos are listed
    expect(screen.getByText("acme/widget")).toBeInTheDocument();
    expect(screen.getByText("acme/gizmo")).toBeInTheDocument();
  });

  it("calls onSelect with the chosen repo full_name", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(
      <RepoSelector
        repos={sampleRepos}
        selected=""
        onSelect={onSelect}
      />
    );

    await user.click(screen.getByRole("button"));
    await user.click(screen.getByText("acme/gizmo"));

    expect(onSelect).toHaveBeenCalledWith("acme/gizmo");
  });

  it("calls onSelect with empty string when 'All repositories' is clicked", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(
      <RepoSelector
        repos={sampleRepos}
        selected="acme/widget"
        onSelect={onSelect}
      />
    );

    await user.click(screen.getByRole("button"));
    // The dropdown has its own "All repositories" entry
    const allButtons = screen.getAllByText("All repositories");
    await user.click(allButtons[allButtons.length - 1]!);

    expect(onSelect).toHaveBeenCalledWith("");
  });

  it("displays the open_prs count next to each repo", async () => {
    const user = userEvent.setup();
    render(
      <RepoSelector
        repos={sampleRepos}
        selected=""
        onSelect={() => {}}
      />
    );

    await user.click(screen.getByRole("button"));
    // acme/widget has 3 open PRs, acme/gizmo has 0
    expect(screen.getByText("3 PR")).toBeInTheDocument();
    expect(screen.getByText("0 PR")).toBeInTheDocument();
  });

  it("closes the dropdown when clicking the backdrop", async () => {
    const user = userEvent.setup();
    render(
      <RepoSelector
        repos={sampleRepos}
        selected=""
        onSelect={() => {}}
      />
    );

    await user.click(screen.getByRole("button"));
    expect(screen.getByText("acme/gizmo")).toBeInTheDocument();

    // The backdrop is a fixed-positioned div; clicking it should close.
    const backdrop = document.querySelector(".fixed.inset-0");
    if (backdrop) await user.click(backdrop);
    expect(screen.queryByText("acme/gizmo")).not.toBeInTheDocument();
  });
});
