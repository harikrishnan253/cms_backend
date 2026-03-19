import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Loader2, AlertCircle } from "lucide-react";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { apiClient } from "@/api/client";
import { uiPaths } from "@/utils/appPaths";

interface EditorPageState {
  collabora_url: string;
  filename: string;
}

async function getEditorState(fileId: string) {
  const response = await apiClient.get<EditorPageState>(`/files/${fileId}/editor`);
  return response.data;
}

export function FileEditorPage() {
  const { projectId, chapterId, fileId } = useParams();
  const query = useQuery({
    queryKey: ["editor", fileId],
    queryFn: () => getEditorState(fileId!),
    enabled: !!fileId,
  });
  useDocumentTitle(query.data ? `${query.data.filename} — Editor` : "Editor — S4 Carlisle CMS");

  return (
    <div className="flex flex-col h-screen bg-surface-50">
      {/* Topbar */}
      <div className="flex items-center gap-3 px-4 h-12 bg-white border-b border-surface-200 flex-shrink-0">
        {projectId && chapterId && (
          <Link
            to={uiPaths.chapterDetail(projectId, chapterId)}
            className="flex items-center gap-1.5 text-sm text-navy-500 hover:text-navy-900 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back
          </Link>
        )}
        <span className="text-sm font-medium text-navy-800 truncate">
          {query.data?.filename ?? "Loading…"}
        </span>
      </div>

      {/* Editor area */}
      <div className="flex-1 overflow-hidden">
        {query.isPending && (
          <div className="flex items-center justify-center h-full gap-2 text-navy-500 text-sm">
            <Loader2 className="w-5 h-5 animate-spin text-gold-600" />
            Loading editor…
          </div>
        )}
        {query.isError && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-sm">
            <AlertCircle className="w-8 h-8 text-red-400" />
            <p className="text-navy-600">Failed to load editor.</p>
            <button
              className="px-4 py-2 rounded-md bg-gold-600 text-white text-sm hover:bg-gold-700"
              onClick={() => void query.refetch()}
            >
              Retry
            </button>
          </div>
        )}
        {query.data?.collabora_url && (
          <iframe
            src={query.data.collabora_url}
            className="w-full h-full border-0"
            allow="clipboard-read; clipboard-write"
            allowFullScreen
            title="Document Editor"
          />
        )}
      </div>
    </div>
  );
}
