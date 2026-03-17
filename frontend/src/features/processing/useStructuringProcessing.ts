import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getApiErrorMessage } from "@/api/client";
import { getProcessingStatus, startProcessingJob } from "@/api/processing";
import type { FileRecord, ProcessingStatusResponse } from "@/types/api";

type ProcessingTone = "pending" | "success" | "error";

interface ProcessingStatusState {
  tone: ProcessingTone;
  fileId: number;
  message: string;
  compatibilityStatus?: string;
  derivedFilename?: string | null;
}

interface UseStructuringProcessingOptions {
  projectId: number | null;
  chapterId: number | null;
}

export function useStructuringProcessing({
  projectId,
  chapterId,
}: UseStructuringProcessingOptions) {
  const queryClient = useQueryClient();
  const [activeFile, setActiveFile] = useState<{ id: number; filename: string } | null>(null);
  const [status, setStatus] = useState<ProcessingStatusState | null>(null);

  const startMutation = useMutation({
    mutationFn: (fileId: number) => startProcessingJob(fileId, "structuring", "style"),
  });

  const statusQuery = useQuery({
    queryKey: ["processing-status", activeFile?.id, "structuring"],
    queryFn: () => getProcessingStatus(activeFile!.id, "structuring"),
    enabled: activeFile !== null,
    refetchInterval: (query) =>
      query.state.data?.status === "processing" ? 2000 : false,
  });

  async function refreshReadState() {
    if (projectId === null || chapterId === null) {
      return;
    }

    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: ["chapter-detail", projectId, chapterId],
      }),
      queryClient.invalidateQueries({
        queryKey: ["chapter-files", projectId, chapterId],
      }),
      queryClient.invalidateQueries({
        queryKey: ["project-detail", projectId],
      }),
      queryClient.invalidateQueries({
        queryKey: ["project-chapters", projectId],
      }),
      queryClient.invalidateQueries({
        queryKey: ["projects"],
      }),
      queryClient.invalidateQueries({
        queryKey: ["dashboard"],
      }),
      queryClient.invalidateQueries({
        queryKey: ["notifications"],
      }),
      queryClient.invalidateQueries({
        queryKey: ["activities"],
      }),
    ]);
  }

  useEffect(() => {
    if (!activeFile || !statusQuery.data) {
      return;
    }

    if (statusQuery.data.status === "processing") {
      setStatus({
        tone: "pending",
        fileId: activeFile.id,
        message: `Structuring is running for ${activeFile.filename}.`,
        compatibilityStatus: statusQuery.data.compatibility_status,
      });
      return;
    }

    void refreshReadState();
    setStatus({
      tone: "success",
      fileId: activeFile.id,
      message: statusQuery.data.derived_filename
        ? `Structuring completed for ${activeFile.filename}. Output: ${statusQuery.data.derived_filename}.`
        : `Structuring completed for ${activeFile.filename}.`,
      compatibilityStatus: statusQuery.data.compatibility_status,
      derivedFilename: statusQuery.data.derived_filename,
    });
    setActiveFile(null);
  }, [activeFile, statusQuery.data]);

  useEffect(() => {
    if (!activeFile || !statusQuery.isError) {
      return;
    }

    setStatus({
      tone: "error",
      fileId: activeFile.id,
      message: getApiErrorMessage(
        statusQuery.error,
        `Failed to read structuring status for ${activeFile.filename}.`,
      ),
    });
    setActiveFile(null);
  }, [activeFile, statusQuery.error, statusQuery.isError]);

  function isPending(fileId: number) {
    return activeFile?.id === fileId && (startMutation.isPending || status?.tone === "pending");
  }

  async function startStructuring(file: FileRecord) {
    setStatus({
      tone: "pending",
      fileId: file.id,
      message: `Starting structuring for ${file.filename}...`,
    });

    try {
      const response = await startMutation.mutateAsync(file.id);
      await refreshReadState();
      setActiveFile({ id: file.id, filename: file.filename });
      setStatus({
        tone: "pending",
        fileId: file.id,
        message: response.message || `Structuring started for ${file.filename}.`,
      });
    } catch (error) {
      setActiveFile(null);
      setStatus({
        tone: "error",
        fileId: file.id,
        message: getApiErrorMessage(error, `Failed to start structuring for ${file.filename}.`),
      });
    }
  }

  return {
    status,
    isPending,
    startStructuring,
  };
}
