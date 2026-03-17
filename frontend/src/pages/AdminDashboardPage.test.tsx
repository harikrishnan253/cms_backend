import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AdminDashboardPage } from "@/pages/AdminDashboardPage";
import { createAdminDashboardResponse, createApiError } from "@/test/fixtures";
import { renderRoute } from "@/test/testUtils";

const getAdminDashboard = vi.fn();

vi.mock("@/api/admin", async () => {
  const actual = await vi.importActual<typeof import("@/api/admin")>("@/api/admin");
  return {
    ...actual,
    getAdminDashboard: (...args: unknown[]) => getAdminDashboard(...args),
  };
});

describe("AdminDashboardPage", () => {
  it("renders the current admin dashboard contract and preserved navigation links", async () => {
    getAdminDashboard.mockResolvedValueOnce(createAdminDashboardResponse());

    renderRoute({
      path: "/ui/admin",
      initialEntry: "/ui/admin",
      element: <AdminDashboardPage />,
    });

    expect(await screen.findByRole("heading", { name: "Admin Dashboard" })).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Manage Users Create, edit, delete users" })).toHaveAttribute(
      "href",
      "/ui/admin/users",
    );
    expect(screen.getByRole("link", { name: "Back to User Dashboard" })).toHaveAttribute(
      "href",
      "/ui/dashboard",
    );
  });

  it("keeps the current error fallback path for admin dashboard load failures", async () => {
    getAdminDashboard.mockRejectedValueOnce(
      createApiError("Admin dashboard failed.", {
        status: 500,
        code: "ADMIN_DASHBOARD_FAILED",
      }),
    );

    renderRoute({
      path: "/ui/admin",
      initialEntry: "/ui/admin",
      element: <AdminDashboardPage />,
    });

    expect(await screen.findByText("Admin dashboard failed.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open SSR admin dashboard" })).toHaveAttribute(
      "href",
      "http://localhost:8000/admin",
    );
  });
});
