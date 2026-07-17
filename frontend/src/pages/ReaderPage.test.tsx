import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReaderPage } from "./ReaderPage";


describe("ReaderPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows a document picker when no document is selected", () => {
    render(<MemoryRouter><ReaderPage /></MemoryRouter>);

    expect(screen.getByRole("heading", { name: "阅读" })).toBeInTheDocument();
    expect(screen.getByText("请从文档库打开一篇文档开始陪读。")).toBeInTheDocument();
  });

  it("starts analysis automatically when a loaded document has none", async () => {
    const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
      if (url.includes("/documents/doc_1/reader")) {
        return Response.json({ document_id: "doc_1", workspace_id: "ws", version_id: "ver_1", title: "测试文档", content_md: "正文", chunks: [{ id: "chunk_1", heading: "概览", content: "原文内容" }], analysis: null });
      }
      if (url.includes("/documents/doc_1/reading-analyses") && options?.method === "POST") {
        return Response.json({ analysis_id: "ra_1", task_job_id: "job_1", status: "pending" });
      }
      if (url.includes("/reading-analyses/ra_1")) {
        return Response.json({ id: "ra_1", workspace_id: "ws", document_id: "doc_1", version_id: "ver_1", status: "running", task_job_id: "job_1", error_message: null, insights: [] });
      }
      throw new Error(`unexpected ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<MemoryRouter initialEntries={["/reader/doc_1"]}><Routes><Route path="/reader/:documentId" element={<ReaderPage />} /></Routes></MemoryRouter>);

    expect(await screen.findByText("测试文档")).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/documents/doc_1/reading-analyses",
      expect.objectContaining({ method: "POST" }),
    ));
  });
});
