import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";

import { ModelManagementPage } from "./ModelManagementPage";

vi.mock("../services/modelManagementApi", () => ({
  listProviders: vi.fn().mockResolvedValue([]),
  listModels: vi.fn().mockResolvedValue([]),
  listRoutes: vi.fn().mockResolvedValue([]),
  createProvider: vi.fn(),
  createModel: vi.fn(),
  saveRoute: vi.fn(),
  testProvider: vi.fn(),
}));

it("renders secure model management controls", async () => {
  render(<ModelManagementPage />, { wrapper: MemoryRouter });

  expect(await screen.findByRole("heading", { name: "模型管理" })).toBeInTheDocument();
  expect(screen.getByLabelText("模型地址")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "测试连接" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "保存提供商" })).toBeInTheDocument();
});
