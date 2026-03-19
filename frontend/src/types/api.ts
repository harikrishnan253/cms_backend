export interface ErrorResponse {
  status: "error";
  code: string;
  message: string;
  field_errors: Record<string, string> | null;
  details: Record<string, string | number | boolean | null> | null;
}

export interface Viewer {
  id: number;
  username: string;
  email: string;
  roles: string[];
  is_active: boolean;
}

export interface SessionAuth {
  mode: "cookie" | "bearer" | null;
  expires_at: string | null;
}

export interface SessionState {
  authenticated: boolean;
  auth_mode: "cookie";
  expires_at: string | null;
}

export interface SessionLoginRequest {
  username: string;
  password: string;
  redirect_to?: string | null;
}

export interface SessionLoginResponse {
  status: "ok";
  session: SessionState;
  viewer: Viewer;
  redirect_to: string;
}

export interface SessionRegisterRequest {
  username: string;
  email: string;
  password: string;
  confirm_password: string;
  redirect_to?: string | null;
}

export interface SessionRegisterResponse {
  status: "ok";
  user: Viewer;
  redirect_to: string;
}

export interface SessionGetResponse {
  authenticated: boolean;
  viewer: Viewer | null;
  auth: SessionAuth;
}

export interface SessionDeleteResponse {
  status: "ok";
  redirect_to: string;
}

export interface DashboardStats {
  total_projects: number;
  on_time_rate: number;
  on_time_trend: string;
  avg_days: number;
  avg_days_trend: string;
  delayed_count: number;
  delayed_trend: string;
}

export interface ProjectSummary {
  id: number;
  code: string;
  title: string;
  client_name: string | null;
  xml_standard: string;
  status: string;
  team_id: number | null;
  chapter_count: number;
  file_count: number;
}

export interface ChapterSummary {
  id: number;
  project_id: number;
  number: string;
  title: string;
  has_art: boolean;
  has_manuscript: boolean;
  has_indesign: boolean;
  has_proof: boolean;
  has_xml: boolean;
}

export interface DashboardResponse {
  viewer: Viewer;
  stats: DashboardStats;
  projects: ProjectSummary[];
}

export interface ProjectsPagination {
  offset: number;
  limit: number;
  total: number;
}

export interface ProjectsListResponse {
  projects: ProjectSummary[];
  pagination: ProjectsPagination;
}

export interface ProjectDetail extends ProjectSummary {
  chapters: ChapterSummary[];
}

export interface ProjectDetailResponse {
  project: ProjectDetail;
}

export interface ProjectChaptersResponse {
  project: ProjectSummary;
  chapters: ChapterSummary[];
}

export interface LockState {
  is_checked_out: boolean;
  checked_out_by_id: number | null;
  checked_out_by_username: string | null;
  checked_out_at: string | null;
}

export interface ChapterCategoryCounts {
  Art: number;
  Manuscript: number;
  InDesign: number;
  Proof: number;
  XML: number;
  Miscellaneous: number;
}

export interface ChapterDetail extends ChapterSummary {
  category_counts: ChapterCategoryCounts;
}

export interface FileRecord {
  id: number;
  project_id: number;
  chapter_id: number | null;
  filename: string;
  file_type: string;
  category: string;
  uploaded_at: string;
  version: number;
  lock: LockState;
  available_actions: string[];
}

export interface FileDeleteInfo {
  file_id: number;
  filename: string;
  category: string;
  project_id: number;
  chapter_id: number | null;
}

export interface FileDeleteResponse {
  status: "ok";
  deleted: FileDeleteInfo;
  redirect_to: string | null;
}

export interface FileCheckoutResponse {
  status: "ok";
  file_id: number;
  lock: LockState;
  redirect_to: string | null;
}

export interface UploadSkippedItem {
  filename: string;
  code: string;
  message: string;
}

export interface UploadResultItem {
  file: FileRecord;
  operation: "created" | "replaced";
  archive_path: string | null;
  archived_version_num: number | null;
}

export interface FileUploadResponse {
  status: "ok";
  uploaded: UploadResultItem[];
  skipped: UploadSkippedItem[];
  redirect_to: string | null;
}

export interface VersionRecord {
  id: number;
  file_id: number;
  version_num: number;
  archived_filename: string;
  archived_path: string;
  uploaded_at: string;
  uploaded_by_id: number | null;
}

export interface FileVersionsFile {
  id: number;
  filename: string;
  current_version: number;
}

export interface FileVersionsResponse {
  file: FileVersionsFile;
  versions: VersionRecord[];
}

export interface ProcessingStartResponse {
  status: "processing";
  message: string;
  source_file_id: number;
  process_type: string;
  mode: string;
  source_version: number;
  lock: LockState;
  status_endpoint: string | null;
}

export interface ProcessingStatusResponse {
  status: "processing" | "completed";
  source_file_id: number;
  process_type: string;
  derived_file_id: number | null;
  derived_filename: string | null;
  compatibility_status: string;
  legacy_status_endpoint: string;
}

export interface TechnicalIssue {
  key: string;
  label: string;
  category: string | null;
  count: number;
  found: string[];
  options: string[];
}

export interface TechnicalScanResponse {
  status: "ok";
  file: FileRecord;
  issues: TechnicalIssue[];
  raw_scan: Record<string, unknown>;
}

export interface TechnicalApplyResponse {
  status: "completed";
  source_file_id: number;
  new_file_id: number;
  new_file: FileRecord;
}

export interface StructuringProcessedFile {
  filename: string;
  exists: true;
}

export interface StructuringReviewEditor {
  mode: "structuring";
  collabora_url: string | null;
  wopi_mode: "structuring";
  save_mode: "wopi_autosave";
}

export interface StructuringReviewActions {
  save_endpoint: string;
  export_href: string;
  return_href: string | null;
  return_mode: "route" | "history";
}

export interface StructuringReviewResponse {
  status: "ok";
  viewer: Viewer;
  file: FileRecord;
  processed_file: StructuringProcessedFile;
  editor: StructuringReviewEditor;
  actions: StructuringReviewActions;
  styles: string[];
}

export interface StructuringSaveResponse {
  status: "ok";
  file_id: number;
  saved_change_count: number;
  target_filename: string;
}

export interface AdminDashboardStats {
  total_users: number;
  total_files: number;
  total_validations: number;
  total_macro: number;
}

export interface AdminDashboardResponse {
  viewer: Viewer;
  stats: AdminDashboardStats;
}

export interface AdminRole {
  id: number;
  name: string;
  description: string | null;
}

export interface AdminUserRole {
  id: number;
  name: string;
}

export interface AdminUser {
  id: number;
  username: string;
  email: string;
  is_active: boolean;
  roles: AdminUserRole[];
}

export interface AdminUsersPagination {
  offset: number;
  limit: number;
  total: number;
}

export interface AdminUsersResponse {
  users: AdminUser[];
  roles: AdminRole[];
  pagination: AdminUsersPagination;
}

export interface AdminRolesResponse {
  roles: AdminRole[];
}

export interface AdminCreateUserRequest {
  username: string;
  email: string;
  password: string;
  role_id: number;
}

export interface AdminCreateUserResponse {
  status: "ok";
  user: AdminUser;
  redirect_to: string | null;
}

export interface AdminUpdateRoleRequest {
  role_id: number;
}

export interface AdminUpdateRoleResponse {
  status: "ok";
  user: AdminUser;
  previous_role_ids: number[];
  redirect_to: string | null;
}

export interface AdminUpdateStatusRequest {
  is_active: boolean;
}

export interface AdminStatusUser {
  id: number;
  is_active: boolean;
}

export interface AdminUpdateStatusResponse {
  status: "ok";
  user: AdminStatusUser;
  redirect_to: string | null;
}

export interface AdminEditUserRequest {
  email: string | null;
}

export interface AdminEditUserResponse {
  status: "ok";
  user: AdminUser;
  redirect_to: string | null;
}

export interface AdminPasswordUpdateRequest {
  new_password: string;
}

export interface AdminPasswordUser {
  id: number;
}

export interface AdminPasswordUpdateResponse {
  status: "ok";
  user: AdminPasswordUser;
  password_updated: boolean;
  redirect_to: string | null;
}

export interface AdminDeleteUser {
  user_id: number;
}

export interface AdminDeleteUserResponse {
  status: "ok";
  deleted: AdminDeleteUser;
  redirect_to: string | null;
}

export interface ChapterCreateRequest {
  number: string;
  title: string;
}

export interface ChapterCreateResponse {
  status: "ok";
  chapter: ChapterSummary;
  redirect_to: string | null;
}

export interface ChapterRenameRequest {
  number: string;
  title: string;
}

export interface ChapterRenameResponse {
  status: "ok";
  chapter: ChapterSummary;
  previous_number: string;
  redirect_to: string | null;
}

export interface ChapterDeleteInfo {
  project_id: number;
  chapter_id: number;
  chapter_number: string;
}

export interface ChapterDeleteResponse {
  status: "ok";
  deleted: ChapterDeleteInfo;
  redirect_to: string | null;
}

export interface ChapterDetailResponse {
  project: ProjectSummary;
  chapter: ChapterDetail;
  active_tab: string;
  viewer: Viewer;
}

export interface ChapterFilesResponse {
  project: ProjectSummary;
  chapter: ChapterDetail;
  files: FileRecord[];
  viewer: Viewer;
}

export interface NotificationItem {
  id: string;
  type: "file_upload";
  title: string;
  description: string;
  relative_time: string;
  icon: string;
  color: string;
  file_id: number | null;
  project_id: number | null;
  chapter_id: number | null;
}

export interface NotificationsResponse {
  notifications: NotificationItem[];
  refreshed_at: string;
}

export interface ProjectBootstrapResponse {
  project: ProjectSummary;
  chapters: ChapterSummary[];
  ingested_files: FileRecord[];
  redirect_to: string;
}

export interface ActivityEntityRef {
  title: string;
}

export interface ActivityItem {
  id: string;
  type: string;
  title: string;
  description: string;
  project: ActivityEntityRef;
  chapter: ActivityEntityRef;
  category: string;
  timestamp: string;
}

export interface ActivitiesSummary {
  total: number;
  today: number;
}

export interface ActivitiesResponse {
  summary: ActivitiesSummary;
  activities: ActivityItem[];
}
