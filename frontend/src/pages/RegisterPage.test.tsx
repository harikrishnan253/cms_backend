import { fireEvent, screen, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { RegisterPage } from "@/pages/RegisterPage";
import { createApiError, createSession, createViewer } from "@/test/fixtures";
import { createTestQueryClient } from "@/test/testUtils";
import { uiPaths } from "@/utils/appPaths";

const getSession = vi.fn();
const registerSession = vi.fn();

vi.mock("@/api/session", () => ({
  getSession: (...args: unknown[]) => getSession(...args),
  registerSession: (...args: unknown[]) => registerSession(...args),
}));

describe("RegisterPage", () => {
  it("redirects to the dashboard when the current session is already authenticated", async () => {
    getSession.mockResolvedValueOnce(createSession());

    const queryClient = createTestQueryClient();
    const router = createMemoryRouter(
      [
        { path: uiPaths.register, element: <RegisterPage /> },
        { path: uiPaths.dashboard, element: <div>Dashboard route</div> },
      ],
      { initialEntries: [uiPaths.register] },
    );

    const { render } = await import("@testing-library/react");
    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Dashboard route")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe(uiPaths.dashboard);
  });

  it("shows the current duplicate-user error state when registration fails", async () => {
    getSession.mockResolvedValueOnce(
      createSession({ authenticated: false, viewer: null, auth: { mode: null, expires_at: null } }),
    );
    registerSession.mockRejectedValueOnce(
      createApiError("Username or email already exists", { status: 400, code: "DUPLICATE_USER" }),
    );

    const queryClient = createTestQueryClient();
    const router = createMemoryRouter([{ path: uiPaths.register, element: <RegisterPage /> }], {
      initialEntries: [uiPaths.register],
    });

    const { render } = await import("@testing-library/react");
    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    fireEvent.change(await screen.findByLabelText("Username"), {
      target: { value: "existing" },
    });
    fireEvent.change(screen.getByLabelText("Email address"), {
      target: { value: "existing@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "Password123!" },
    });
    fireEvent.change(screen.getByLabelText("Confirm Password"), {
      target: { value: "Password123!" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create Account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Username or email already exists");
  });

  it("registers with the current backend contract and redirects to the frontend login page", async () => {
    getSession.mockResolvedValueOnce(
      createSession({ authenticated: false, viewer: null, auth: { mode: null, expires_at: null } }),
    );
    registerSession.mockResolvedValueOnce({
      status: "ok",
      user: createViewer({
        username: "new-user",
        email: "new-user@example.com",
        roles: ["Viewer"],
      }),
      redirect_to: uiPaths.login,
    });

    const queryClient = createTestQueryClient();
    const router = createMemoryRouter(
      [
        { path: uiPaths.register, element: <RegisterPage /> },
        { path: uiPaths.login, element: <div>Login route</div> },
      ],
      { initialEntries: [uiPaths.register] },
    );

    const { render } = await import("@testing-library/react");
    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    fireEvent.change(await screen.findByLabelText("Username"), {
      target: { value: "new-user" },
    });
    fireEvent.change(screen.getByLabelText("Email address"), {
      target: { value: "new-user@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "Password123!" },
    });
    fireEvent.change(screen.getByLabelText("Confirm Password"), {
      target: { value: "Password123!" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create Account" }));

    await waitFor(() => {
      expect(registerSession).toHaveBeenCalledWith({
        username: "new-user",
        email: "new-user@example.com",
        password: "Password123!",
        confirm_password: "Password123!",
        redirect_to: uiPaths.login,
      });
    });
    expect(await screen.findByText("Login route")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe(uiPaths.login);
  });
});
