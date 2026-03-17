import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { TechnicalReviewPage } from "@/pages/TechnicalReviewPage";
import { createApiError, createTechnicalScanResponse } from "@/test/fixtures";
import { renderRoute } from "@/test/testUtils";

const getTechnicalReview = vi.fn();
const applyTechnicalReview = vi.fn();

vi.mock("@/api/technicalReview", () => ({
  getTechnicalReview: (...args: unknown[]) => getTechnicalReview(...args),
  applyTechnicalReview: (...args: unknown[]) => applyTechnicalReview(...args),
}));

describe("TechnicalReviewPage", () => {
  it("renders the current error state when the technical review contract fails", async () => {
    getTechnicalReview.mockRejectedValueOnce(
      createApiError("Technical scan unavailable.", {
        status: 500,
        code: "TECHNICAL_SCAN_FAILED",
      }),
    );

    renderRoute({
      path: "/ui/projects/:projectId/chapters/:chapterId/files/:fileId/technical-review",
      initialEntry: "/ui/projects/10/chapters/20/files/100/technical-review",
      element: <TechnicalReviewPage />,
    });

    expect(await screen.findByText("Technical review unavailable")).toBeInTheDocument();
    expect(screen.getByText("Technical scan unavailable.")).toBeInTheDocument();
  });

  it("keeps apply wired to the current technical review mutation flow", async () => {
    getTechnicalReview.mockResolvedValueOnce(
      createTechnicalScanResponse({
        issues: [
          {
            key: "issue-1",
            label: "Issue 1",
            category: "Formatting",
            count: 2,
            found: ["teh", "teh"],
            options: ["the", "The"],
          },
        ],
      }),
    );
    applyTechnicalReview.mockResolvedValueOnce({
      status: "completed",
      source_file_id: 100,
      new_file_id: 101,
      new_file: {
        ...createTechnicalScanResponse().file,
        id: 101,
        filename: "chapter01_TechEdited.docx",
      },
    });

    renderRoute({
      path: "/ui/projects/:projectId/chapters/:chapterId/files/:fileId/technical-review",
      initialEntry: "/ui/projects/10/chapters/20/files/100/technical-review",
      element: <TechnicalReviewPage />,
    });

    expect(await screen.findByRole("heading", { name: "Technical Editing" })).toBeInTheDocument();

    await userEvent.click(screen.getAllByRole("button", { name: "Apply Changes" })[0]);

    await waitFor(() => {
      expect(applyTechnicalReview).toHaveBeenCalledWith(100, {
        "issue-1": "the",
      });
    });
  });
});
