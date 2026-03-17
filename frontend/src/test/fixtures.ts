import { AxiosError, AxiosHeaders, type InternalAxiosRequestConfig } from "axios";

import type {
  AdminRole,
  AdminUser,
  AdminDashboardResponse,
  ChapterSummary,
  ChapterDetailResponse,
  ChapterFilesResponse,
  DashboardResponse,
  ErrorResponse,
  FileRecord,
  LockState,
  NotificationItem,
  NotificationsResponse,
  ProjectChaptersResponse,
  ProjectDetailResponse,
  ProjectSummary,
  ProjectsListResponse,
  SessionGetResponse,
  StructuringReviewResponse,
  TechnicalScanResponse,
  Viewer,
} from "@/types/api";

export function createViewer(overrides: Partial<Viewer> = {}): Viewer {
  return {
    id: 1,
    username: "admin",
    email: "admin@example.com",
    roles: ["Admin"],
    is_active: true,
    ...overrides,
  };
}

export function createSession(
  overrides: Partial<SessionGetResponse> = {},
): SessionGetResponse {
  return {
    authenticated: true,
    viewer: createViewer(),
    auth: {
      mode: "cookie",
      expires_at: "2026-03-17T00:00:00",
    },
    ...overrides,
  };
}

export function createProjectSummary(overrides: Partial<ProjectSummary> = {}): ProjectSummary {
  return {
    id: 10,
    code: "BOOK100",
    title: "Book 100",
    client_name: "Client A",
    xml_standard: "NLM",
    status: "In Progress",
    team_id: null,
    chapter_count: 2,
    file_count: 3,
    ...overrides,
  };
}

export function createChapterSummary(overrides: Partial<ChapterSummary> = {}): ChapterSummary {
  return {
    id: 20,
    project_id: 10,
    number: "01",
    title: "Chapter One",
    has_art: false,
    has_manuscript: true,
    has_indesign: false,
    has_proof: false,
    has_xml: false,
    ...overrides,
  };
}

export function createDashboardResponse(
  overrides: Partial<DashboardResponse> = {},
): DashboardResponse {
  return {
    viewer: createViewer(),
    stats: {
      total_projects: 1,
      on_time_rate: 100,
      on_time_trend: "up",
      avg_days: 5,
      avg_days_trend: "flat",
      delayed_count: 0,
      delayed_trend: "down",
    },
    projects: [createProjectSummary()],
    ...overrides,
  };
}

export function createProjectsListResponse(
  overrides: Partial<ProjectsListResponse> = {},
): ProjectsListResponse {
  return {
    projects: [createProjectSummary()],
    pagination: {
      offset: 0,
      limit: 100,
      total: 1,
    },
    ...overrides,
  };
}

export function createProjectDetailResponse(
  overrides: Partial<ProjectDetailResponse> = {},
): ProjectDetailResponse {
  return {
    project: {
      ...createProjectSummary(),
      chapters: [createChapterSummary()],
    },
    ...overrides,
  };
}

export function createProjectChaptersResponse(
  overrides: Partial<ProjectChaptersResponse> = {},
): ProjectChaptersResponse {
  return {
    project: createProjectSummary(),
    chapters: [createChapterSummary()],
    ...overrides,
  };
}

export function createLockState(overrides: Partial<LockState> = {}): LockState {
  return {
    is_checked_out: false,
    checked_out_by_id: null,
    checked_out_by_username: null,
    checked_out_at: null,
    ...overrides,
  };
}

export function createFileRecord(overrides: Partial<FileRecord> = {}): FileRecord {
  return {
    id: 100,
    project_id: 10,
    chapter_id: 20,
    filename: "chapter01.docx",
    file_type: "docx",
    category: "Manuscript",
    uploaded_at: "2026-03-16T00:00:00",
    version: 1,
    lock: createLockState(),
    available_actions: ["download", "delete", "edit", "technical_edit", "checkout"],
    ...overrides,
  };
}

export function createChapterDetailResponse(
  overrides: Partial<ChapterDetailResponse> = {},
): ChapterDetailResponse {
  return {
    project: createProjectSummary(),
    chapter: {
      id: 20,
      project_id: 10,
      number: "01",
      title: "Chapter One",
      has_art: false,
      has_manuscript: true,
      has_indesign: false,
      has_proof: false,
      has_xml: false,
      category_counts: {
        Art: 0,
        Manuscript: 1,
        InDesign: 0,
        Proof: 0,
        XML: 0,
        Miscellaneous: 0,
      },
    },
    active_tab: "Manuscript",
    viewer: createViewer(),
    ...overrides,
  };
}

export function createChapterFilesResponse(
  overrides: Partial<ChapterFilesResponse> = {},
): ChapterFilesResponse {
  return {
    project: createProjectSummary(),
    chapter: createChapterDetailResponse().chapter,
    files: [createFileRecord()],
    viewer: createViewer(),
    ...overrides,
  };
}

export function createTechnicalScanResponse(
  overrides: Partial<TechnicalScanResponse> = {},
): TechnicalScanResponse {
  return {
    status: "ok",
    file: createFileRecord(),
    issues: [
      {
        key: "issue-1",
        label: "Issue 1",
        category: "format",
        count: 1,
        found: ["teh"],
        options: ["the"],
      },
    ],
    raw_scan: {
      "issue-1": {
        label: "Issue 1",
        category: "format",
        count: 1,
        found: ["teh"],
        options: ["the"],
      },
    },
    ...overrides,
  };
}

export function createStructuringReviewResponse(
  overrides: Partial<StructuringReviewResponse> = {},
): StructuringReviewResponse {
  return {
    status: "ok",
    viewer: createViewer(),
    file: createFileRecord(),
    processed_file: {
      filename: "chapter01_Processed.docx",
      exists: true,
    },
    editor: {
      mode: "structuring",
      collabora_url: "http://localhost/cool.html?WOPISrc=http://localhost/wopi/files/100/structuring",
      wopi_mode: "structuring",
      save_mode: "wopi_autosave",
    },
    actions: {
      save_endpoint: "/api/v2/files/100/structuring-review/save",
      export_href: "/api/v2/files/100/structuring-review/export",
      return_href: "/ui/projects/10/chapters/20",
      return_mode: "route",
    },
    styles: ["style-a", "style-b"],
    ...overrides,
  };
}

export function createAdminRole(overrides: Partial<AdminRole> = {}): AdminRole {
  return {
    id: 1,
    name: "Admin",
    description: "Administrator",
    ...overrides,
  };
}

export function createAdminDashboardResponse(
  overrides: Partial<AdminDashboardResponse> = {},
): AdminDashboardResponse {
  return {
    viewer: createViewer(),
    stats: {
      total_users: 4,
      total_files: 18,
      total_validations: 7,
      total_macro: 2,
    },
    ...overrides,
  };
}

export function createAdminUser(overrides: Partial<AdminUser> = {}): AdminUser {
  return {
    id: 1,
    username: "existing",
    email: "existing@example.com",
    is_active: true,
    roles: [{ id: 1, name: "Admin" }],
    ...overrides,
  };
}

export function createNotificationsResponse(
  overrides: Partial<NotificationsResponse> = {},
): NotificationsResponse {
  const notification: NotificationItem = {
    id: "notif-1",
    type: "file_upload",
    title: "Upload complete",
    description: "chapter01.docx uploaded",
    relative_time: "just now",
    icon: "upload",
    color: "blue",
    file_id: 100,
    project_id: 10,
    chapter_id: 20,
  };

  return {
    notifications: [notification],
    refreshed_at: "2026-03-16T00:00:00",
    ...overrides,
  };
}

export function createApiError(
  message: string,
  {
    status = 400,
    code = "TEST_ERROR",
  }: {
    status?: number;
    code?: string;
  } = {},
) {
  const data: ErrorResponse = {
    status: "error",
    code,
    message,
    field_errors: null,
    details: null,
  };

  return new AxiosError(
    message,
    String(status),
    {
      headers: new AxiosHeaders(),
    } as InternalAxiosRequestConfig,
    undefined,
    {
      data,
      status,
      statusText: String(status),
      headers: {},
      config: {
        headers: new AxiosHeaders(),
      } as InternalAxiosRequestConfig,
    },
  );
}
