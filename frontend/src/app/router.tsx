import { Navigate, createBrowserRouter } from "react-router-dom";

import { AppLayout } from "@/components/layout/AppLayout";
import { AdminGate } from "@/features/session/AdminGate";
import { SessionGate } from "@/features/session/SessionGate";
import { AdminDashboardPage } from "@/pages/AdminDashboardPage";
import { AdminUsersPage } from "@/pages/AdminUsersPage";
import { ChapterDetailPage } from "@/pages/ChapterDetailPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { LoginPage } from "@/pages/LoginPage";
import { EditorPage } from "@/pages/EditorPage";
import { FileEditorPage } from "@/pages/FileEditorPage";
import { ProjectCreatePage } from "@/pages/ProjectCreatePage";
import { ProjectDetailPage } from "@/pages/ProjectDetailPage";
import { ProjectsPage } from "@/pages/ProjectsPage";
import { RegisterPage } from "@/pages/RegisterPage";
import { StructuringReviewPage } from "@/pages/StructuringReviewPage";
import { TechnicalReviewPage } from "@/pages/TechnicalReviewPage";
import { ComingSoonPage } from "@/pages/ComingSoonPage";
import { ActivitiesPage } from "@/pages/ActivitiesPage";
import { uiPaths } from "@/utils/appPaths";

function UiRouteLayout() {
  return (
    <SessionGate>
      <AppLayout />
    </SessionGate>
  );
}

export const router = createBrowserRouter([
  {
    path: uiPaths.login,
    element: <LoginPage />,
  },
  {
    path: uiPaths.register,
    element: <RegisterPage />,
  },
  {
    path: uiPaths.root,
    element: <UiRouteLayout />,
    children: [
      {
        index: true,
        element: <Navigate replace to={uiPaths.dashboard} />,
      },
      {
        path: "dashboard",
        element: <DashboardPage />,
      },
      {
        path: "admin",
        element: <AdminGate><AdminDashboardPage /></AdminGate>,
      },
      {
        path: "admin/users",
        element: <AdminGate><AdminUsersPage /></AdminGate>,
      },
      {
        path: "projects",
        element: <ProjectsPage />,
      },
      {
        path: "editor/:projectId",
        element: <EditorPage />,
      },
      {
        path: "projects/create",
        element: <ProjectCreatePage />,
      },
      {
        path: "projects/:projectId",
        element: <ProjectDetailPage />,
      },
      {
        path: "projects/:projectId/chapters/:chapterId",
        element: <ChapterDetailPage />,
      },
      {
        path: "projects/:projectId/chapters/:chapterId/files/:fileId/technical-review",
        element: <TechnicalReviewPage />,
      },
      {
        path: "projects/:projectId/chapters/:chapterId/files/:fileId/structuring-review",
        element: <StructuringReviewPage />,
      },
      {
        path: "projects/:projectId/chapters/:chapterId/files/:fileId/edit",
        element: <FileEditorPage />,
      },
      { path: "workflow", element: <ComingSoonPage /> },
      { path: "files", element: <ComingSoonPage /> },
      { path: "quality-control", element: <ComingSoonPage /> },
      { path: "reports", element: <ComingSoonPage /> },
      { path: "activities", element: <ActivitiesPage /> },
    ],
  },
  {
    path: "*",
    element: <Navigate replace to={uiPaths.root} />,
  },
]);
