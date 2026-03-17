import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ProjectsPage } from "@/pages/ProjectsPage";
import { createProjectsListResponse } from "@/test/fixtures";
import { renderRoute } from "@/test/testUtils";
import { uiPaths } from "@/utils/appPaths";

const getProjects = vi.fn();

vi.mock("@/api/projects", async () => {
  const actual = await vi.importActual<typeof import("@/api/projects")>("@/api/projects");
  return {
    ...actual,
    getProjects: (...args: unknown[]) => getProjects(...args),
  };
});

describe("ProjectsPage", () => {
  it("renders the current error state when the projects contract fails", async () => {
    getProjects.mockRejectedValueOnce(new Error("projects failed"));

    renderRoute({
      path: uiPaths.projects,
      initialEntry: uiPaths.projects,
      element: <ProjectsPage />,
    });

    expect(await screen.findByText("Projects unavailable")).toBeInTheDocument();
    expect(
      screen.getByText("The frontend shell could not load the projects list contract."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open SSR projects" })).toBeInTheDocument();
  });

  it("keeps project navigation wired to the current frontend project-detail route", async () => {
    getProjects.mockResolvedValueOnce(createProjectsListResponse());

    renderRoute({
      path: uiPaths.projects,
      initialEntry: uiPaths.projects,
      element: <ProjectsPage />,
    });

    const projectTitle = await screen.findByText("Book 100");
    const projectLink = projectTitle.closest("a");
    expect(projectLink).not.toBeNull();
    expect(projectLink).toHaveAttribute("href", uiPaths.projectDetail(10));
    expect(screen.getByRole("link", { name: "New Project" })).toHaveAttribute(
      "href",
      "http://localhost:8000/projects/create",
    );
  });
});
