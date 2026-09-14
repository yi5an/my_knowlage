import { render, screen, waitFor } from "@testing-library/react";
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
  it("renders the global shell and intelligence flow", () => {
    renderRoute();

    expect(screen.getByText("KnowPilot")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "情报流" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/搜索情报/)).toBeInTheDocument();
  });

  it("makes primary pages reachable by route", () => {
    const routes = [
      ["/import", "导入中心"],
      ["/library", "文档库"],
      ["/reader", "阅读"],
      ["/graph", "知识图谱"],
      ["/provenance", "事件结论溯源"],
      ["/search", "智能搜索"],
      ["/research", "深度研究"],
      ["/entity", "实体详情"],
      ["/notebooklm", "NotebookLM"],
      ["/settings", "设置"],
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

  it("keeps dashboard focused on workspace overview", async () => {
    renderRoute();

    // Dashboard fetches real stats; wait for the labels to render after
    // loading settles (the fetch will fail in the test env, showing defaults).
    await waitFor(() => {
      expect(screen.getByText("快速操作")).toBeInTheDocument();
    });
    expect(screen.getByText("已启用订阅")).toBeInTheDocument();
    expect(screen.getByText("已总结视频")).toBeInTheDocument();
    expect(screen.getByText("抽取实体")).toBeInTheDocument();
  });

  it("selects the provenance navigation item on the dedicated route", () => {
    renderRoute("/provenance");
    expect(screen.getByRole("menuitem", { name: /溯源图/ })).toHaveClass(
      "ant-menu-item-selected",
    );
  });
});
