import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AdminUsersPage } from "@/pages/AdminUsersPage";
import { createAdminRole, createAdminUser } from "@/test/fixtures";
import { renderRoute } from "@/test/testUtils";

const mockUseAdminUsersQuery = vi.fn();
const mockUseAdminMutations = vi.fn();

vi.mock("@/features/admin/useAdminUsersQuery", () => ({
  useAdminUsersQuery: () => mockUseAdminUsersQuery(),
}));

vi.mock("@/features/admin/useAdminMutations", () => ({
  useAdminMutations: () => mockUseAdminMutations(),
}));

describe("AdminUsersPage", () => {
  it("surfaces the current admin mutation error banner without changing backend behavior", async () => {
    mockUseAdminUsersQuery.mockReturnValue({
      isPending: false,
      isError: false,
      data: {
        users: [createAdminUser()],
        roles: [createAdminRole()],
        pagination: {
          offset: 0,
          limit: 100,
          total: 1,
        },
      },
    });
    mockUseAdminMutations.mockReturnValue({
      status: {
        tone: "error",
        message: "User already exists.",
      },
      isPending: () => false,
      createUser: vi.fn(),
      updateRole: vi.fn(),
      toggleStatus: vi.fn(),
      editUser: vi.fn(),
      updatePassword: vi.fn(),
      deleteUser: vi.fn(),
    });

    renderRoute({
      path: "/ui/admin/users",
      initialEntry: "/ui/admin/users",
      element: <AdminUsersPage />,
    });

    expect(await screen.findByRole("heading", { name: "User Management" })).toBeInTheDocument();
    expect(screen.getByText("User already exists.")).toBeInTheDocument();
  });

  it("keeps create user wired to the current admin mutation contract", async () => {
    const createUser = vi.fn().mockResolvedValue({
      status: "ok",
      redirect_to: null,
      user: createAdminUser({ id: 2, username: "new_user", email: "new@example.com" }),
    });

    mockUseAdminUsersQuery.mockReturnValue({
      isPending: false,
      isError: false,
      data: {
        users: [createAdminUser()],
        roles: [createAdminRole(), createAdminRole({ id: 2, name: "Viewer" })],
        pagination: {
          offset: 0,
          limit: 100,
          total: 1,
        },
      },
    });
    mockUseAdminMutations.mockReturnValue({
      status: null,
      isPending: () => false,
      createUser,
      updateRole: vi.fn(),
      toggleStatus: vi.fn(),
      editUser: vi.fn(),
      updatePassword: vi.fn(),
      deleteUser: vi.fn(),
    });

    renderRoute({
      path: "/ui/admin/users",
      initialEntry: "/ui/admin/users",
      element: <AdminUsersPage />,
    });

    await userEvent.click(await screen.findByRole("button", { name: "Create New User" }));
    await userEvent.type(screen.getByLabelText("Username"), "new_user");
    await userEvent.type(screen.getByLabelText("Email"), "new@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "secret123");
    await userEvent.click(screen.getByRole("button", { name: "Create User" }));

    expect(createUser).toHaveBeenCalledWith({
      username: "new_user",
      email: "new@example.com",
      password: "secret123",
      role_id: 1,
    });
  });
});
