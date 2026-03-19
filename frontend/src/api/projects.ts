import { apiClient } from "@/api/client";
import type {
  ChapterCreateRequest,
  ChapterCreateResponse,
  ChapterDeleteResponse,
  ChapterDetailResponse,
  ChapterFilesResponse,
  ChapterRenameRequest,
  ChapterRenameResponse,
  ProjectBootstrapResponse,
  ProjectChaptersResponse,
  ProjectDetailResponse,
  ProjectsListResponse,
} from "@/types/api";

export async function createProject(formData: FormData) {
  const response = await apiClient.post<ProjectBootstrapResponse>(
    "/projects/bootstrap",
    formData,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return response.data;
}

export async function getProjects(offset = 0, limit = 100) {
  const response = await apiClient.get<ProjectsListResponse>("/projects", {
    params: { offset, limit },
  });
  return response.data;
}

export async function getProjectDetail(projectId: number) {
  const response = await apiClient.get<ProjectDetailResponse>(`/projects/${projectId}`);
  return response.data;
}

export async function getProjectChapters(projectId: number) {
  const response = await apiClient.get<ProjectChaptersResponse>(`/projects/${projectId}/chapters`);
  return response.data;
}

export async function getChapterDetail(projectId: number, chapterId: number) {
  const response = await apiClient.get<ChapterDetailResponse>(
    `/projects/${projectId}/chapters/${chapterId}`,
  );
  return response.data;
}

export async function getChapterFiles(projectId: number, chapterId: number) {
  const response = await apiClient.get<ChapterFilesResponse>(
    `/projects/${projectId}/chapters/${chapterId}/files`,
  );
  return response.data;
}

export async function createChapter(projectId: number, payload: ChapterCreateRequest) {
  const response = await apiClient.post<ChapterCreateResponse>(`/projects/${projectId}/chapters`, payload);
  return response.data;
}

export async function renameChapter(
  projectId: number,
  chapterId: number,
  payload: ChapterRenameRequest,
) {
  const response = await apiClient.patch<ChapterRenameResponse>(
    `/projects/${projectId}/chapters/${chapterId}`,
    payload,
  );
  return response.data;
}

export async function deleteChapter(projectId: number, chapterId: number) {
  const response = await apiClient.delete<ChapterDeleteResponse>(
    `/projects/${projectId}/chapters/${chapterId}`,
  );
  return response.data;
}

export async function deleteProject(projectId: number) {
  const response = await apiClient.delete(`/projects/${projectId}`);
  return response.data;
}
