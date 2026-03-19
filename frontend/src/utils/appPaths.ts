export const uiPaths = {
  root: "/",
  login: "/login",
  register: "/register",
  dashboard: "/dashboard",
  adminDashboard: "/admin",
  adminUsers: "/admin/users",
  projects: "/projects",
  projectCreate: "/projects/create",
  projectDetail: (projectId: number | string) => `/projects/${projectId}`,
  projectEditor: (projectId: number | string) => `/editor/${projectId}`,
  chapterDetail: (projectId: number | string, chapterId: number | string) =>
    `/projects/${projectId}/chapters/${chapterId}`,
  technicalReview: (
    projectId: number | string,
    chapterId: number | string,
    fileId: number | string,
  ) => `/projects/${projectId}/chapters/${chapterId}/files/${fileId}/technical-review`,
  structuringReview: (
    projectId: number | string,
    chapterId: number | string,
    fileId: number | string,
  ) => `/projects/${projectId}/chapters/${chapterId}/files/${fileId}/structuring-review`,
  fileEditor: (
    projectId: number | string,
    chapterId: number | string,
    fileId: number | string,
  ) => `/projects/${projectId}/chapters/${chapterId}/files/${fileId}/edit`,
} as const;

export const ssrPaths = {
  login: "/login",
  adminDashboard: "/admin",
  adminUsers: "/admin/users",
  dashboard: "/dashboard",
  projects: "/projects",
  projectCreate: "/projects/create",
  projectDetail: (projectId: number | string) => `/projects/${projectId}`,
  chapterDetail: (projectId: number | string, chapterId: number | string) =>
    `/projects/${projectId}/chapter/${chapterId}`,
  logout: "/logout",
} as const;

function trimTrailingSlash(value: string) {
  return value.replace(/\/+$/, "");
}

function getConfiguredSsrOrigin() {
  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
  if (apiBaseUrl && /^https?:\/\//i.test(apiBaseUrl)) {
    return trimTrailingSlash(new URL(apiBaseUrl).origin);
  }

  const devProxyTarget = import.meta.env.VITE_DEV_PROXY_TARGET?.trim();
  if (devProxyTarget && /^https?:\/\//i.test(devProxyTarget)) {
    return trimTrailingSlash(devProxyTarget);
  }

  if (import.meta.env.DEV) {
    return "http://localhost:8000";
  }

  if (typeof window !== "undefined") {
    return trimTrailingSlash(window.location.origin);
  }

  return "";
}

export function getSsrUrl(path: string) {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const origin = getConfiguredSsrOrigin();
  if (!origin) {
    return normalizedPath;
  }

  return new URL(normalizedPath, `${origin}/`).toString();
}
