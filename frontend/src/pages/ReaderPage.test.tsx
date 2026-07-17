import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { ReaderPage } from "./ReaderPage";


describe("ReaderPage", () => {
  it("shows a document picker when no document is selected", () => {
    render(<MemoryRouter><ReaderPage /></MemoryRouter>);

    expect(screen.getByRole("heading", { name: "阅读" })).toBeInTheDocument();
    expect(screen.getByText("请从文档库打开一篇文档开始陪读。")).toBeInTheDocument();
  });
});
