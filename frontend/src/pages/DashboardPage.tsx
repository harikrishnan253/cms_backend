import { AlertCircle, BookOpen, FolderOpen, FolderPlus, Upload } from "lucide-react";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/ui/EmptyState";
import { SkeletonCard, SkeletonTable } from "@/components/ui/SkeletonLoader";
import { DashboardAdminShortcuts } from "@/features/dashboard/components/DashboardAdminShortcuts";
import { DashboardProjectGrid } from "@/features/dashboard/components/DashboardProjectGrid";
import { DashboardStatsGrid } from "@/features/dashboard/components/DashboardStatsGrid";
import { useDashboardQuery } from "@/features/dashboard/useDashboardQuery";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { uiPaths } from "@/utils/appPaths";

/* ─── Loading skeleton ─────────────────────────────────────────────────────── */
function DashboardSkeleton() {
  return (
    <main className="page-enter px-6 py-8 max-w-7xl mx-auto w-full">
      {/* Greeting skeleton */}
      <div className="mb-6">
        <div className="skeleton-shimmer rounded h-7 w-56 mb-2" />
        <div className="skeleton-shimmer rounded h-4 w-40" />
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>

      {/* Table skeleton */}
      <div className="bg-white rounded-lg shadow-card overflow-hidden">
        <div className="px-5 py-4 border-b border-surface-300">
          <div className="skeleton-shimmer rounded h-5 w-32" />
        </div>
        <SkeletonTable rows={5} cols={6} />
      </div>
    </main>
  );
}

/* ─── Error card ───────────────────────────────────────────────────────────── */
function DashboardError({ onRetry }: { onRetry: () => void }) {
  return (
    <main className="page-enter flex items-center justify-center min-h-[60vh] px-6">
      <div className="bg-white rounded-lg shadow-card p-8 max-w-md w-full text-center">
        <div className="w-12 h-12 bg-error-100 rounded-full flex items-center justify-center mx-auto mb-4">
          <AlertCircle className="w-6 h-6 text-error-600" />
        </div>
        <h2 className="font-serif text-xl font-semibold text-navy-900 mb-2">
          Dashboard unavailable
        </h2>
        <p className="text-sm text-navy-500 mb-6">
          The frontend shell could not load the dashboard. Please retry or open
          the server-rendered version.
        </p>
        <div className="flex items-center justify-center gap-3">
          <button
            className="bg-gold-600 hover:bg-gold-700 text-white font-semibold px-4 py-2 rounded-md text-sm transition-colors"
            onClick={onRetry}
            type="button"
          >
            Retry
          </button>
        </div>
      </div>
    </main>
  );
}

/* ─── Quick actions panel ─────────────────────────────────────────────────── */
function QuickActions() {
  return (
    <section className="mb-6">
      <h2 className="text-xs font-medium text-navy-500 uppercase tracking-wide mb-3">
        Quick Actions
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Link
          className="bg-white rounded-md border border-surface-300 p-4 flex flex-col items-center gap-2 hover:shadow-card transition-all cursor-pointer text-center"
          to={uiPaths.projectCreate}
        >
          <FolderPlus className="w-6 h-6 text-gold-600" />
          <span className="text-sm font-medium text-navy-800">New Project</span>
          <span className="text-xs text-navy-400">Create a manuscript project</span>
        </Link>

        <Link
          className="bg-white rounded-md border border-surface-300 p-4 flex flex-col items-center gap-2 hover:shadow-card transition-all cursor-pointer text-center"
          to={uiPaths.projectCreate}
        >
          <Upload className="w-6 h-6 text-gold-600" />
          <span className="text-sm font-medium text-navy-800">Upload Manuscript</span>
          <span className="text-xs text-navy-400">Add files to a project</span>
        </Link>

        <Link
          className="bg-white rounded-md border border-surface-300 p-4 flex flex-col items-center gap-2 hover:shadow-card transition-all cursor-pointer text-center"
          to={uiPaths.projects}
        >
          <FolderOpen className="w-6 h-6 text-gold-600" />
          <span className="text-sm font-medium text-navy-800">View All Projects</span>
          <span className="text-xs text-navy-400">Browse the project list</span>
        </Link>
      </div>
    </section>
  );
}

/* ─── Dashboard Page ──────────────────────────────────────────────────────── */
export function DashboardPage() {
  useDocumentTitle("Dashboard — S4 Carlisle CMS");
  const dashboardQuery = useDashboardQuery();

  if (dashboardQuery.isPending) {
    return <DashboardSkeleton />;
  }

  if (dashboardQuery.isError) {
    return <DashboardError onRetry={() => dashboardQuery.refetch()} />;
  }

  const { projects, stats, viewer } = dashboardQuery.data;
  const isAdmin = viewer.roles.includes("Admin");

  /* Greeting */
  const hour = new Date().getHours();
  const greeting =
    hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";

  /* Current date formatted as "Monday, 17 March 2026" */
  const formattedDate = new Date().toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  return (
    <main className="page-enter px-6 py-8 max-w-7xl mx-auto w-full">
      {/* Greeting header */}
      <header className="mb-6">
        <h1 className="font-serif text-2xl font-semibold text-navy-900">
          {greeting}, {viewer.username}
        </h1>
        <p className="text-sm text-navy-600 mt-1">{formattedDate}</p>
      </header>

      {/* Stats */}
      <DashboardStatsGrid stats={stats} />

      {/* Admin shortcuts */}
      {isAdmin ? <DashboardAdminShortcuts userId={viewer.id} /> : null}

      {/* Quick actions */}
      <QuickActions />

      {/* Recent projects */}
      <section className="bg-white rounded-lg shadow-card overflow-hidden">
        <div className="px-5 py-4 border-b border-surface-200 flex items-center justify-between">
          <div>
            <h2 className="font-semibold text-navy-900">Recent Projects</h2>
            <p className="text-xs text-navy-500 mt-0.5">
              {projects.length} project{projects.length !== 1 ? "s" : ""} loaded
            </p>
          </div>
          <Link
            className="text-xs font-medium text-gold-600 hover:text-gold-700 transition-colors"
            to={uiPaths.projects}
          >
            View all
          </Link>
        </div>

        {projects.length === 0 ? (
          <div className="p-8">
            <EmptyState
              icon={BookOpen}
              title="No projects yet"
              description="Project summaries will appear here once books are created through the backend."
              action={
                <Link
                  className="bg-gold-600 hover:bg-gold-700 text-white font-semibold px-4 py-2 rounded-md text-sm transition-colors inline-flex items-center gap-2"
                  to={uiPaths.projectCreate}
                >
                  Create first project
                </Link>
              }
            />
          </div>
        ) : (
          <DashboardProjectGrid projects={projects} />
        )}
      </section>
    </main>
  );
}
