import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { StructuringReviewPage } from "@/pages/StructuringReviewPage";
import { createApiError, createStructuringReviewResponse } from "@/test/fixtures";
import { renderRoute } from "@/test/testUtils";

const getStructuringReview = vi.fn();
const saveStructuringReview = vi.fn();

vi.mock("@/api/structuringReview", () => ({
  getStructuringReview: (...args: unknown[]) => getStructuringReview(...args),
  saveStructuringReview: (...args: unknown[]) => saveStructuringReview(...args),
}));

describe("StructuringReviewPage", () => {
  it("surfaces the missing processed-file backend error state", async () => {
    getStructuringReview.mockRejectedValueOnce(
      createApiError("Processed file not found.", {
        status: 404,
        code: "PROCESSED_FILE_MISSING",
      }),
    );

    renderRoute({
      path: "/ui/projects/:projectId/chapters/:chapterId/files/:fileId/structuring-review",
      initialEntry: "/ui/projects/10/chapters/20/files/100/structuring-review",
      element: <StructuringReviewPage />,
    });

    expect(await screen.findByText("Structuring review unavailable")).toBeInTheDocument();
    expect(screen.getByText("Processed file not found.")).toBeInTheDocument();
  });

  it("keeps save, export, return, and editor handoff wired to the current contract", async () => {
    getStructuringReview.mockResolvedValueOnce(createStructuringReviewResponse());
    saveStructuringReview.mockResolvedValueOnce({
      status: "ok",
      file_id: 100,
      saved_change_count: 0,
      target_filename: "chapter01_Processed.docx",
    });

    renderRoute({
      path: "/ui/projects/:projectId/chapters/:chapterId/files/:fileId/structuring-review",
      initialEntry: "/ui/projects/10/chapters/20/files/100/structuring-review",
      element: <StructuringReviewPage />,
    });

    expect(await screen.findByRole("heading", { name: "chapter01.docx" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Save & Exit" })).toHaveAttribute(
      "href",
      "/ui/projects/10/chapters/20",
    );
    expect(screen.getByRole("link", { name: "Export Word" })).toHaveAttribute(
      "href",
      "/api/v2/files/100/structuring-review/export",
    );
    expect(screen.getByRole("link", { name: "Open provided editor URL" })).toHaveAttribute(
      "href",
      "http://localhost/cool.html?WOPISrc=http://localhost/wopi/files/100/structuring",
    );

    await userEvent.click(screen.getByRole("button", { name: "Save Changes" }));

    await waitFor(() => {
      expect(saveStructuringReview).toHaveBeenCalledWith(
        "/api/v2/files/100/structuring-review/save",
        {},
      );
    });
  });
});
