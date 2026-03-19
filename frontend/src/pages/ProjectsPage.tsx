import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { FolderPlus, FolderOpen, ExternalLink, BookOpen, Trash2 } from "lucide-react";

import { PageHeader } from "@/components/ui/PageHeader";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { SkeletonTable } from "@/components/ui/SkeletonLoader";
import { EmptyState } from "@/components/ui/EmptyState";
import { SearchInput } from "@/components/ui/SearchInput";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteProject } from "@/api/projects";
import { useProjectsQuery } from "@/features/projects/useProjectsQuery";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { uiPaths } from "@/utils/appPaths";
import { useSessionStore } from "@/stores/sessionStore";

export function ProjectsPage() {
  useDocumentTitle("Projects — S4 Carlisle CMS");
  const navigate = useNavigate();
  const projectsQuery = useProjectsQuery(0, 100);
  const queryClient = useQueryClient();
  const viewer = useSessionStore((s) => s.viewer);
  const canDelete = viewer?.roles?.some((r) => ["Admin", "ProjectManager"].includes(r)) ?? false;

  const deleteMutation = useMutation({
    mutationFn: (projectId: number) => deleteProject(projectId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["projects"] }),
    onError: () => alert("Failed to delete project."),
  });

  const handleDelete = (e: React.MouseEvent, projectId: number, title: string) => {
    e.stopPropagation();
    setDeleteTarget({ id: projectId, title });
  };
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<{ id: number; title: string } | null>(null);

  const projects = projectsQuery.data?.projects ?? [];
  const total = projectsQuery.data?.pagination.total ?? 0;

  const filteredProjects = projects.filter((project) => {
    const matchesSearch =
      !searchQuery ||
      project.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      project.code.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = !statusFilter || project.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const uniqueStatuses = Array.from(new Set(projects.map((p) => p.status))).sort();

  return (
    <main className="page-enter page px-6 py-6 max-w-7xl mx-auto">
      <PageHeader
        title="Projects"
        subtitle={`${total} project${total === 1 ? "" : "s"}`}
        primaryAction={
          <Link
            to={uiPaths.projectCreate}
            className="inline-flex items-center gap-2 h-9 px-4 text-sm font-medium rounded-md bg-gold-600 text-white hover:bg-gold-700 active:bg-gold-800 border border-gold-600 shadow-subtle transition-all duration-150"
          >
            <FolderPlus className="w-4 h-4" aria-hidden="true" />
            New Project
          </Link>
        }
      />

      {/* Filter bar */}
      <div className="flex flex-wrap gap-3 mb-6 mt-6">
        <SearchInput
          value={searchQuery}
          onChange={setSearchQuery}
          placeholder="Search by title or code…"
          className="w-64"
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="border border-surface-400 rounded-md px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-gold-600 focus:outline-none text-navy-800"
        >
          <option value="">All statuses</option>
          {uniqueStatuses.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {/* Table card */}
      <div className="bg-white rounded-lg shadow-card overflow-hidden">
        {projectsQuery.isPending ? (
          <SkeletonTable rows={8} cols={7} />
        ) : projectsQuery.isError ? (
          <div className="p-8 text-center text-sm text-navy-500">
            Failed to load projects.{" "}
            <button
              className="text-gold-700 underline hover:text-gold-800"
              onClick={() => void projectsQuery.refetch()}
              type="button"
            >
              Retry
            </button>
          </div>
        ) : filteredProjects.length === 0 ? (
          <EmptyState
            icon={FolderOpen}
            title="No projects yet"
            description="Create your first project to get started"
            action={
              <Link
                to={uiPaths.projectCreate}
                className="inline-flex items-center gap-2 h-9 px-4 text-sm font-medium rounded-md bg-gold-600 text-white hover:bg-gold-700 border border-gold-600 shadow-subtle transition-all duration-150"
              >
                <FolderPlus className="w-4 h-4" aria-hidden="true" />
                New Project
              </Link>
            }
          />
        ) : (
          <table className="w-full border-collapse">
            <thead className="bg-surface-100 border-b border-surface-300">
              <tr>
                <th className="text-xs font-semibold text-navy-500 uppercase tracking-wide px-4 py-3 text-left">
                  Project Title / Code
                </th>
                <th className="text-xs font-semibold text-navy-500 uppercase tracking-wide px-4 py-3 text-left">
                  Publisher
                </th>
                <th className="text-xs font-semibold text-navy-500 uppercase tracking-wide px-4 py-3 text-left">
                  XML Standard
                </th>
                <th className="text-xs font-semibold text-navy-500 uppercase tracking-wide px-4 py-3 text-left">
                  Chapters
                </th>
                <th className="text-xs font-semibold text-navy-500 uppercase tracking-wide px-4 py-3 text-left">
                  Files
                </th>
                <th className="text-xs font-semibold text-navy-500 uppercase tracking-wide px-4 py-3 text-left">
                  Status
                </th>
                <th className="text-xs font-semibold text-navy-500 uppercase tracking-wide px-4 py-3 text-left">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {filteredProjects.map((project) => (
                <tr
                  key={project.id}
                  className="group border-b border-surface-200 hover:bg-surface-50 transition-colors duration-120 cursor-pointer"
                  onClick={() => navigate(uiPaths.projectDetail(project.id))}
                >
                  {/* Title / Code */}
                  <td className="px-4 py-3.5 text-sm">
                    <div className="text-[14px] font-semibold text-navy-900 group-hover:text-gold-600 transition-colors duration-120">
                      {project.title}
                    </div>
                    <div style={{ color: '#6B6560' }} className="text-[12px] mt-0.5 font-mono">
                      {project.code}
                    </div>
                  </td>

                  {/* Publisher */}
                  <td className="px-4 py-3.5 text-sm text-navy-700">
                    {project.client_name ?? "—"}
                  </td>

                  {/* XML Standard */}
                  <td className="px-4 py-3.5 text-sm text-navy-700">
                    {project.xml_standard}
                  </td>

                  {/* Chapters */}
                  <td className="px-4 py-3.5 text-sm text-navy-700 tabular-nums">
                    {project.chapter_count}
                  </td>

                  {/* Files */}
                  <td className="px-4 py-3.5 text-sm text-navy-700 tabular-nums">
                    {project.file_count}
                  </td>

                  {/* Status */}
                  <td className="px-4 py-3.5 text-sm">
                    <StatusBadge status={project.status} size="sm" />
                  </td>

                  {/* Actions — stopPropagation so row onClick doesn't fire */}
                  <td
                    className="px-4 py-3.5 text-sm"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        title="View project"
                        className="w-7 h-7 rounded flex items-center justify-center text-navy-500 hover:bg-surface-200 hover:text-navy-900 transition-colors"
                        onClick={() => navigate(uiPaths.projectDetail(project.id))}
                      >
                        <ExternalLink className="w-3.5 h-3.5" aria-hidden="true" />
                        <span className="sr-only">View {project.title}</span>
                      </button>
                      <button
                        type="button"
                        title="Open in editor"
                        className="w-7 h-7 rounded flex items-center justify-center text-navy-500 hover:bg-surface-200 hover:text-navy-900 transition-colors"
                        onClick={() => navigate(uiPaths.projectEditor(project.id))}
                      >
                        <BookOpen className="w-3.5 h-3.5" aria-hidden="true" />
                        <span className="sr-only">Open {project.title} in editor</span>
                      </button>
                      {canDelete && (
                        <button
                          type="button"
                          title="Delete project"
                          className="w-7 h-7 rounded flex items-center justify-center text-navy-500 hover:bg-red-50 hover:text-red-600 transition-colors"
                          onClick={(e) => handleDelete(e, project.id, project.title)}
                          disabled={deleteMutation.isPending}
                        >
                          <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
                          <span className="sr-only">Delete {project.title}</span>
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
          <ConfirmDialog
        isOpen={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) deleteMutation.mutate(deleteTarget.id);
          setDeleteTarget(null);
        }}
        title="Delete Project"
        description={`Are you sure you want to delete "${deleteTarget?.title}"? This will permanently remove all chapters and files.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteMutation.isPending}
      />
    </main>
  );
}
