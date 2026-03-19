import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  Activity,
  BarChart3,
  ChevronRight,
  Files,
  FolderOpen,
  GitBranch,
  LayoutDashboard,
  Loader2,
  LogOut,
  ShieldCheck,
  Users,
} from "lucide-react";

import { NotificationBell } from "@/features/notifications/components/NotificationBell";
import { useLogout } from "@/features/session/useLogout";
import { useSessionStore } from "@/stores/sessionStore";
import { uiPaths } from "@/utils/appPaths";

// ─── Types ──────────────────────────────────────────────────────────────────

interface NavItem {
  label: string;
  to: string;
  icon: React.ReactNode;
  end?: boolean;
}

// ─── Helpers ────────────────────────────────────────────────────────────────

/**
 * Converts a URL pathname segment into a human-readable label.
 * e.g. "chapter-detail" → "Chapter Detail"
 */
function segmentToLabel(segment: string): string {
  return segment
    .replace(/-/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Maps a full UI pathname to a list of breadcrumb crumbs.
 * Returns at minimum [{ label: "Home", path: "/" }].
 */
interface Crumb {
  label: string;
  path: string;
}

function buildBreadcrumbs(pathname: string): Crumb[] {
  const crumbs: Crumb[] = [{ label: "Home", path: "/" }];

  // Strip the /ui prefix
  const stripped = pathname.replace(/^\/ui\/?/, "");
  if (!stripped) return crumbs;

  const segments = stripped.split("/").filter(Boolean);

  // Build human labels for well-known segments
  const labelMap: Record<string, string> = {
    dashboard: "Dashboard",
    admin: "Admin Dashboard",
    users: "Users",
    projects: "Projects",
    chapters: "Chapter",
    files: "File",
    "technical-review": "Technical Review",
    "structuring-review": "Structuring Review",
  };

  let accPath = "/ui";
  for (const seg of segments) {
    accPath = `${accPath}/${seg}`;
    // If the segment looks like a numeric ID, show it as an ID crumb
    if (/^\d+$/.test(seg)) {
      const prev = crumbs[crumbs.length - 1];
      // e.g. "Projects" → "Projects #42"
      crumbs[crumbs.length - 1] = {
        ...prev,
        label: `${prev.label} #${seg}`,
      };
    } else {
      crumbs.push({
        label: labelMap[seg] ?? segmentToLabel(seg),
        path: accPath,
      });
    }
  }

  return crumbs;
}

// ─── Sidebar style constants (inline — bypasses Tailwind compilation) ────────

const SIDEBAR_BG   = '#1A1714';
const SIDEBAR_TEXT = '#D4CFC9';
const SIDEBAR_MUTED = '#6B6560';
const GOLD         = '#C9821A';

const NAV_ITEM_CLASS =
  "flex items-center gap-3 mx-2 my-0.5 rounded-md cursor-pointer transition-colors duration-150";

// ─── Sidebar ────────────────────────────────────────────────────────────────

interface SidebarProps {
  isAdmin: boolean;
  username: string;
  role: string;
  viewerInitial: string;
  isPendingLogout: boolean;
  onLogout: () => void;
}

function Sidebar({
  isAdmin,
  username,
  role,
  viewerInitial,
  isPendingLogout,
  onLogout,
}: SidebarProps) {
  const [logoError, setLogoError] = useState(false);

  const primaryNavItems: NavItem[] = [
    {
      label: "Dashboard",
      to: uiPaths.dashboard,
      icon: <LayoutDashboard className="w-[18px] h-[18px] flex-shrink-0" />,
      end: false,
    },
    {
      label: "Projects",
      to: uiPaths.projects,
      icon: <FolderOpen className="w-[18px] h-[18px] flex-shrink-0" />,
      end: false,
    },
    {
      label: "Workflow",
      to: "/workflow",
      icon: <GitBranch className="w-[18px] h-[18px] flex-shrink-0" />,
      end: false,
    },
    {
      label: "Files",
      to: "/files",
      icon: <Files className="w-[18px] h-[18px] flex-shrink-0" />,
      end: false,
    },
    {
      label: "Quality Control",
      to: "/quality-control",
      icon: <ShieldCheck className="w-[18px] h-[18px] flex-shrink-0" />,
      end: false,
    },
    {
      label: "Reports",
      to: "/reports",
      icon: <BarChart3 className="w-[18px] h-[18px] flex-shrink-0" />,
      end: false,
    },
    {
      label: "Activities",
      to: "/activities",
      icon: <Activity className="w-[18px] h-[18px] flex-shrink-0" />,
      end: false,
    },
  ];

  const adminNavItems: NavItem[] = [
    {
      label: "Admin Dashboard",
      to: uiPaths.adminDashboard,
      icon: <BarChart3 className="w-[18px] h-[18px] flex-shrink-0" />,
    },
    {
      label: "Users",
      to: uiPaths.adminUsers,
      icon: <Users className="w-[18px] h-[18px] flex-shrink-0" />,
    },
  ];

  return (
    <aside
      style={{ backgroundColor: SIDEBAR_BG }}
      className="w-[220px] h-screen flex flex-col fixed left-0 top-0 z-20"
      aria-label="Application sidebar"
    >
      {/* Logo area */}
      <div
        style={{ borderColor: 'rgba(255,255,255,0.1)' }}
        className="px-4 py-5 border-b"
      >
        {!logoError ? (
          <img
            alt="PubCMS logo"
            className="h-8 w-auto object-contain"
            src="/logo.png"
            onError={() => setLogoError(true)}
          />
        ) : (
          <span style={{ color: '#FFFFFF' }} className="font-semibold text-base">PubCMS</span>
        )}
      </div>

      {/* Nav */}
      <nav
        className="flex-1 overflow-y-auto py-2"
        aria-label="Primary navigation"
      >
        <p
          style={{ color: SIDEBAR_MUTED }}
          className="px-4 pt-5 pb-1 text-[10px] font-medium uppercase tracking-widest"
        >
          Main
        </p>
        {primaryNavItems.map((item) => (
          <NavLink
            key={item.label}
            to={item.to}
            end={item.end}
            className={NAV_ITEM_CLASS}
            style={({ isActive }) => ({
              color: isActive ? '#FFFFFF' : SIDEBAR_TEXT,
              backgroundColor: isActive ? 'rgba(201,130,26,0.15)' : 'transparent',
              borderLeft: isActive ? `3px solid ${GOLD}` : '3px solid transparent',
              paddingTop: '0.625rem',
              paddingBottom: '0.625rem',
              paddingLeft: isActive ? '0.75rem' : '1rem',
              paddingRight: '1rem',
            })}
          >
            {item.icon}
            <span className="text-[14px] font-medium">{item.label}</span>
          </NavLink>
        ))}

        {isAdmin && (
          <>
            <p
              style={{ color: SIDEBAR_MUTED }}
              className="px-4 pt-5 pb-1 text-[10px] font-medium uppercase tracking-widest"
            >
              Admin
            </p>
            {adminNavItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={NAV_ITEM_CLASS}
                style={({ isActive }) => ({
                  color: isActive ? '#FFFFFF' : SIDEBAR_TEXT,
                  backgroundColor: isActive ? 'rgba(201,130,26,0.15)' : 'transparent',
                  borderLeft: isActive ? `3px solid ${GOLD}` : '3px solid transparent',
                  paddingTop: '0.625rem',
                  paddingBottom: '0.625rem',
                  paddingLeft: isActive ? '0.75rem' : '1rem',
                  paddingRight: '1rem',
                })}
              >
                {item.icon}
                <span className="text-[14px] font-medium">{item.label}</span>
              </NavLink>
            ))}
          </>
        )}
      </nav>

      {/* Bottom user section */}
      <div
        style={{ borderColor: 'rgba(255,255,255,0.1)' }}
        className="mt-auto px-4 py-4 border-t"
      >
        <div className="flex items-center gap-3">
          <div
            style={{ backgroundColor: GOLD, color: '#FFFFFF' }}
            className="w-8 h-8 rounded-full flex items-center justify-center text-[13px] font-semibold flex-shrink-0"
          >
            {viewerInitial}
          </div>
          <div className="min-w-0">
            <p style={{ color: '#FFFFFF' }} className="text-[13px] font-semibold truncate">{username}</p>
            <p style={{ color: SIDEBAR_MUTED }} className="text-[11px] truncate">{role}</p>
          </div>
        </div>
        <button
          style={{ color: SIDEBAR_MUTED }}
          className="flex items-center gap-2 text-[13px] mt-3 cursor-pointer w-full bg-transparent border-none transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
          disabled={isPendingLogout}
          type="button"
          onClick={onLogout}
          onMouseEnter={(e) => { e.currentTarget.style.color = '#F87171'; }}
          onMouseLeave={(e) => { e.currentTarget.style.color = SIDEBAR_MUTED; }}
        >
          {isPendingLogout ? (
            <Loader2 className="w-4 h-4 flex-shrink-0 animate-spin" />
          ) : (
            <LogOut className="w-4 h-4 flex-shrink-0" />
          )}
          <span>{isPendingLogout ? "Signing out…" : "Logout"}</span>
        </button>
      </div>
    </aside>
  );
}

// ─── TopBar ──────────────────────────────────────────────────────────────────

interface TopBarProps {
  username: string;
  viewerInitial: string;
}

function TopBar({ username, viewerInitial }: TopBarProps) {
  const location = useLocation();
  const crumbs = buildBreadcrumbs(location.pathname);

  return (
    <header className="h-14 flex-shrink-0 flex items-center justify-between px-6 bg-white border-b border-surface-300">
      {/* Breadcrumb */}
      <nav aria-label="Breadcrumb">
        <ol className="flex items-center gap-1 text-sm">
          {crumbs.map((crumb, index) => {
            const isLast = index === crumbs.length - 1;
            return (
              <li key={crumb.path} className="flex items-center gap-1">
                {index > 0 && (
                  <ChevronRight
                    aria-hidden="true"
                    className="text-navy-400"
                    size={14}
                  />
                )}
                {isLast ? (
                  <span className="font-medium text-navy-900" aria-current="page">
                    {crumb.label}
                  </span>
                ) : (
                  <span className="text-navy-400">{crumb.label}</span>
                )}
              </li>
            );
          })}
        </ol>
      </nav>

      {/* Right side actions */}
      <div className="flex items-center gap-4">
        {/* Notification bell */}
        <div className="relative">
          <NotificationBell />
        </div>

        {/* User menu (display only, no dropdown) */}
        <button
          className="flex items-center gap-2 px-3 py-1.5 rounded-md hover:bg-surface-100 text-sm font-medium text-navy-700 transition-colors cursor-pointer"
          type="button"
          aria-label={`Signed in as ${username}`}
        >
          <div className="w-6 h-6 rounded-full bg-gold-600 text-white text-xs font-bold flex items-center justify-center flex-shrink-0">
            {viewerInitial}
          </div>
          <span>{username}</span>
        </button>
      </div>
    </header>
  );
}

// ─── AppLayout ───────────────────────────────────────────────────────────────

/** Normalize a role value that might be a string, a {name} object, or a Python repr string. */
function resolveRoleName(role: unknown): string {
  if (typeof role === "string") {
    // Reject Python object reprs like "<app.models.Role object at 0x...>"
    if (role.startsWith("<") && role.endsWith(">")) return "User";
    return role;
  }
  if (role && typeof role === "object" && "name" in role) {
    return String((role as { name: unknown }).name);
  }
  return "User";
}

export function AppLayout() {
  const viewer = useSessionStore((state) => state.viewer);
  const logoutMutation = useLogout();

  const resolvedRoles = (viewer?.roles ?? []).map(resolveRoleName).filter(Boolean);
  const isAdmin = resolvedRoles.includes("Admin");
  const username = viewer?.username ?? "User";
  const viewerInitial = username[0]?.toUpperCase() ?? "U";
  const primaryRole = resolvedRoles[0] ?? "Viewer";

  return (
    <div className="h-screen overflow-hidden bg-surface-200">
      <Sidebar
        isAdmin={isAdmin}
        isPendingLogout={logoutMutation.isPending}
        role={primaryRole}
        username={username}
        viewerInitial={viewerInitial}
        onLogout={() => logoutMutation.mutate()}
      />

      <div className="ml-[220px] flex flex-col h-screen overflow-hidden">
        <TopBar username={username} viewerInitial={viewerInitial} />
        <main className="flex-1 overflow-y-auto p-6 page-enter">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
