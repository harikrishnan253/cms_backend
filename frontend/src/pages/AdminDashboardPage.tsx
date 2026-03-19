import { ExternalLink, Users } from "lucide-react";
import { Link } from "react-router-dom";

import { getApiErrorMessage } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { SkeletonCard } from "@/components/ui/SkeletonLoader";
import { AdminStatsGrid } from "@/features/admin/components/AdminStatsGrid";
import { useAdminDashboardQuery } from "@/features/admin/useAdminDashboardQuery";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { uiPaths } from "@/utils/appPaths";

export function AdminDashboardPage() {
  useDocumentTitle("Admin — S4 Carlisle CMS");
  const dashboardQuery = useAdminDashboardQuery();

  if (dashboardQuery.isPending) {
    return (
      <main className="page-enter min-h-screen bg-surface-100 p-6">
        <div className="max-w-6xl mx-auto space-y-6">
          <div className="h-14 skeleton-shimmer rounded-md" aria-hidden="true" />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            {Array.from({ length: 4 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <SkeletonCard />
            <SkeletonCard />
          </div>
        </div>
      </main>
    );
  }

  if (dashboardQuery.isError) {
    return (
      <main className="page-enter min-h-screen bg-surface-100 p-6 flex items-center justify-center">
        <div className="bg-white rounded-lg shadow-card p-10 max-w-md w-full text-center space-y-4">
          <EmptyState
            title="Admin dashboard unavailable"
            description={getApiErrorMessage(
              dashboardQuery.error,
              "The frontend shell could not load the admin dashboard contract.",
            )}
          />
          <div className="flex items-center justify-center gap-3 pt-2">
            <Button variant="primary" onClick={() => void dashboardQuery.refetch()}>
              Retry
            </Button>
          </div>
        </div>
      </main>
    );
  }

  const dashboard = dashboardQuery.data;

  return (
    <main className="page-enter min-h-screen bg-surface-100 p-6">
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Page Header */}
        <PageHeader
          title="Admin Dashboard"
          subtitle="System overview and management"
          primaryAction={
            <Link to={uiPaths.adminUsers}>
              <Button variant="secondary" leftIcon={<Users />}>
                Users
              </Button>
            </Link>
          }
        />

        {/* Stats Grid */}
        <AdminStatsGrid stats={dashboard.stats} />

        {/* Quick Links */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* User Management */}
          <div className="bg-white rounded-lg shadow-card p-6 flex items-start gap-4 hover:shadow-hover transition-all">
            <div className="w-10 h-10 rounded-md flex items-center justify-center bg-navy-100 shrink-0">
              <Users className="w-5 h-5 text-navy-700" />
            </div>
            <div className="flex-1 min-w-0">
              <h2 className="font-semibold text-navy-900 text-sm leading-snug">User Management</h2>
              <p className="text-sm text-navy-500 mt-1 leading-relaxed">
                Create and manage user accounts and roles
              </p>
              <div className="mt-4">
                <Link to={uiPaths.adminUsers}>
                  <Button variant="primary" size="sm">
                    Manage Users
                  </Button>
                </Link>
              </div>
            </div>
          </div>

          
        </div>

        {/* Footer note */}
        <p className="text-xs text-navy-400">
          Viewer: <span className="font-medium">{dashboard.viewer.username}</span>
        </p>
      </div>
    </main>
  );
}
