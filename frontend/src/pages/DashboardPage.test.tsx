import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DashboardPage } from "@/pages/DashboardPage";
import { createDashboardResponse, createViewer } from "@/test/fixtures";
import { renderRoute } from "@/test/testUtils";
import { uiPaths } from "@/utils/appPaths";

const getDashboard = vi.fn();

vi.mock("@/api/dashboard", () => ({
  getDashboard: (...args: unknown[]) => getDashboard(...args),
}));

describe("DashboardPage", () => {
  it("points the SSR project creation action at the backend origin in the empty state", async () => {
    getDashboard.mockResolvedValueOnce(
      createDashboardResponse({
        projects: [],
      }),
    );

    renderRoute({
      path: uiPaths.dashboard,
      initialEntry: uiPaths.dashboard,
      element: <DashboardPage />,
    });

    const link = await screen.findByRole("link", { name: "Open SSR project creation" });
    expect(link).toHaveAttribute("href", "http://localhost:8000/projects/create");
  });

  it("renders the current error state when the dashboard contract fails", async () => {
    getDashboard.mockRejectedValueOnce(new Error("dashboard failed"));

    renderRoute({
      path: uiPaths.dashboard,
      initialEntry: uiPaths.dashboard,
      element: <DashboardPage />,
    });

    expect(await screen.findByText("Dashboard unavailable")).toBeInTheDocument();
    expect(
      screen.getByText("The frontend shell could not load the dashboard contract."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open SSR dashboard" })).toBeInTheDocument();
  });

  it("shows admin shortcuts only when the dashboard viewer has the Admin role", async () => {
    getDashboard.mockResolvedValueOnce(
      createDashboardResponse({
        viewer: createViewer({ roles: ["Viewer"] }),
      }),
    );

    renderRoute({
      path: uiPaths.dashboard,
      initialEntry: uiPaths.dashboard,
      element: <DashboardPage />,
    });

    expect(await screen.findByText("S4carlisle Production Dashboard")).toBeInTheDocument();
    expect(screen.queryByText("Admin Shortcuts")).not.toBeInTheDocument();
  });
});
