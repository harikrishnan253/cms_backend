import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ProjectDetailPage } from "@/pages/ProjectDetailPage";
import {
  createProjectChaptersResponse,
  createProjectDetailResponse,
} from "@/test/fixtures";
import { renderRoute } from "@/test/testUtils";

const getProjectDetail = vi.fn();
const getProjectChapters = vi.fn();
const createChapter = vi.fn();
const renameChapter = vi.fn();
const deleteChapter = vi.fn();

vi.mock("@/api/projects", async () => {
  const actual = await vi.importActual<typeof import("@/api/projects")>("@/api/projects");
  return {
    ...actual,
    getProjectDetail: (...args: unknown[]) => getProjectDetail(...args),
    getProjectChapters: (...args: unknown[]) => getProjectChapters(...args),
    createChapter: (...args: unknown[]) => createChapter(...args),
    renameChapter: (...args: unknown[]) => renameChapter(...args),
    deleteChapter: (...args: unknown[]) => deleteChapter(...args),
  };
});

describe("ProjectDetailPage", () => {
  it("keeps chapter navigation and package download wired to the current routes", async () => {
    getProjectDetail.mockResolvedValueOnce(createProjectDetailResponse());
    getProjectChapters.mockResolvedValueOnce(createProjectChaptersResponse());

    renderRoute({
      path: "/ui/projects/:projectId",
      initialEntry: "/ui/projects/10",
      element: <ProjectDetailPage />,
    });

    expect(await screen.findByRole("heading", { name: "Book 100" })).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Chapter 01 - Chapter One" }),
    ).toHaveAttribute("href", "/ui/projects/10/chapters/20");
    expect(screen.getByRole("link", { name: "Download ZIP" })).toHaveAttribute(
      "href",
      "/api/v2/projects/10/chapters/20/package",
    );
  });

  it("keeps chapter creation wired to the current mutation contract", async () => {
    getProjectDetail
      .mockResolvedValueOnce(createProjectDetailResponse())
      .mockResolvedValueOnce(createProjectDetailResponse());
    getProjectChapters
      .mockResolvedValueOnce(createProjectChaptersResponse())
      .mockResolvedValueOnce(createProjectChaptersResponse());
    createChapter.mockResolvedValueOnce({
      status: "ok",
      chapter: {
        id: 30,
        project_id: 10,
        number: "03",
        title: "Chapter 03",
        has_art: false,
        has_manuscript: false,
        has_indesign: false,
        has_proof: false,
        has_xml: false,
      },
      redirect_to: null,
    });

    renderRoute({
      path: "/ui/projects/:projectId",
      initialEntry: "/ui/projects/10",
      element: <ProjectDetailPage />,
    });

    fireEvent.click(await screen.findByRole("button", { name: /New/ }));
    fireEvent.change(screen.getByLabelText("Chapter Number"), {
      target: { value: "03" },
    });
    fireEvent.change(screen.getByLabelText("Chapter Title"), {
      target: { value: "Chapter 03" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create Chapter" }));

    await waitFor(() => {
      expect(createChapter).toHaveBeenCalledWith(10, {
        number: "03",
        title: "Chapter 03",
      });
    });
  });
});
