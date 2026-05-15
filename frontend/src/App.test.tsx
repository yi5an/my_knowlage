import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { App } from "./App";

function renderRoute(path = "/") {
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe("App shell", () => {
  it("renders the global shell and dashboard", () => {
    renderRoute();

    expect(screen.getByText("KnowPilot")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Search documents/)).toBeInTheDocument();
  });

  it("makes primary pages reachable by route", () => {
    const routes = [
      ["/import", "Import center"],
      ["/library", "Library"],
      ["/reader", "Reader"],
      ["/graph", "Knowledge graph"],
      ["/search", "Smart search"],
      ["/research", "Deep research"],
      ["/entity", "Entity detail"],
      ["/notebooklm", "NotebookLM"],
      ["/settings", "Settings"],
    ] as const;

    for (const [path, heading] of routes) {
      const { unmount } = render(
        <MemoryRouter initialEntries={[path]}>
          <App />
        </MemoryRouter>,
      );

      expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
      unmount();
    }
  });

  it("keeps dashboard focused on workspace overview", () => {
    renderRoute();

    expect(screen.getByText("Continue last work")).toBeInTheDocument();
    expect(screen.getByText("Needs attention")).toBeInTheDocument();
    expect(screen.getByText("Quick start")).toBeInTheDocument();
  });
});
