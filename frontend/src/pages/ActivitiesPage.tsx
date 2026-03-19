import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { PageHeader } from "@/components/ui/PageHeader";
import { SkeletonTable } from "@/components/ui/SkeletonLoader";
import type { ActivitiesResponse } from "@/types/api";

async function getActivities() {
  const response = await apiClient.get<ActivitiesResponse>("/activities", { params: { limit: 100 } });
  return response.data;
}

export function ActivitiesPage() {
  useDocumentTitle("Activities — S4 Carlisle CMS");
  const query = useQuery({ queryKey: ["activities"], queryFn: getActivities });
  const activities = query.data?.activities ?? [];

  return (
    <main className="page-enter page px-6 py-6 max-w-7xl mx-auto">
      <PageHeader
        title="Activities"
        subtitle={query.data ? `${query.data.summary.total} recent activities` : ""}
      />
      <div className="bg-white rounded-lg shadow-card overflow-hidden mt-6">
        {query.isPending ? (
          <SkeletonTable rows={8} cols={5} />
        ) : query.isError ? (
          <div className="p-8 text-center text-sm text-navy-500">
            Failed to load activities.{" "}
            <button className="text-gold-700 underline" onClick={() => void query.refetch()}>Retry</button>
          </div>
        ) : activities.length === 0 ? (
          <div className="p-8 text-center text-sm text-navy-500">No activities yet.</div>
        ) : (
          <table className="w-full border-collapse">
            <thead className="bg-surface-100 border-b border-surface-300">
              <tr>
                <th className="text-xs font-semibold text-navy-500 uppercase tracking-wide px-4 py-3 text-left">Type</th>
                <th className="text-xs font-semibold text-navy-500 uppercase tracking-wide px-4 py-3 text-left">Title</th>
                <th className="text-xs font-semibold text-navy-500 uppercase tracking-wide px-4 py-3 text-left">Project</th>
                <th className="text-xs font-semibold text-navy-500 uppercase tracking-wide px-4 py-3 text-left">Chapter</th>
                <th className="text-xs font-semibold text-navy-500 uppercase tracking-wide px-4 py-3 text-left">Time</th>
              </tr>
            </thead>
            <tbody>
              {activities.map((a) => (
                <tr key={a.id} className="border-b border-surface-200 hover:bg-surface-50 transition-colors">
                  <td className="px-4 py-3 text-sm">
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gold-100 text-gold-800 capitalize">
                      {a.type}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-navy-800 font-medium">{a.title}</td>
                  <td className="px-4 py-3 text-sm text-navy-600">{a.project?.title ?? "—"}</td>
                  <td className="px-4 py-3 text-sm text-navy-600">{a.chapter?.title ?? "—"}</td>
                  <td className="px-4 py-3 text-sm text-navy-500">{new Date(a.timestamp).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </main>
  );
}
