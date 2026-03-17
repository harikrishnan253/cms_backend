import { useState } from "react";

import type { AdminRole, AdminUser } from "@/types/api";

type AdminActionKind = "create" | "role" | "status" | "edit" | "password" | "delete";

interface AdminUsersTableProps {
  users: AdminUser[];
  roles: AdminRole[];
  isPending: (action: AdminActionKind, userId?: number | null) => boolean;
  onUpdateRole: (userId: number, roleId: number, username: string) => Promise<unknown>;
  onToggleStatus: (userId: number, isActive: boolean, username: string) => Promise<unknown>;
  onDeleteUser: (userId: number, username: string) => Promise<unknown>;
  onOpenEditUser: (user: AdminUser) => void;
  onOpenPasswordUser: (user: AdminUser) => void;
}

function initials(value: string) {
  return value.trim().slice(0, 1).toUpperCase();
}

function AdminUserRow({
  user,
  roles,
  isPending,
  onUpdateRole,
  onToggleStatus,
  onDeleteUser,
  onOpenEditUser,
  onOpenPasswordUser,
}: {
  user: AdminUser;
  roles: AdminRole[];
  isPending: AdminUsersTableProps["isPending"];
  onUpdateRole: AdminUsersTableProps["onUpdateRole"];
  onToggleStatus: AdminUsersTableProps["onToggleStatus"];
  onDeleteUser: AdminUsersTableProps["onDeleteUser"];
  onOpenEditUser: AdminUsersTableProps["onOpenEditUser"];
  onOpenPasswordUser: AdminUsersTableProps["onOpenPasswordUser"];
}) {
  const [selectedRoleId, setSelectedRoleId] = useState<number>(user.roles[0]?.id ?? roles[0]?.id ?? 0);

  return (
    <tr className="admin-users-table__row">
      <td className="admin-users-table__user-cell">
        <div className="admin-user-chip">
          <div aria-hidden="true" className="admin-user-chip__avatar">
            {initials(user.username)}
          </div>
          <div>
            <div className="admin-user-chip__name">{user.username}</div>
            <div className="admin-user-chip__email">{user.email}</div>
          </div>
        </div>
      </td>

      <td className="admin-users-table__role-cell">
        <div className="admin-users-table__role-stack">
          <div className="admin-role-badges">
            {user.roles.length > 0 ? (
              user.roles.map((role) => (
                <span className="admin-role-badge" key={`${user.id}-${role.id}`}>
                  {role.name}
                </span>
              ))
            ) : (
              <span className="admin-role-empty">No roles</span>
            )}
          </div>
          <div className="admin-users-table__role-editor">
            <select
              className="select-input admin-users-table__role-select"
              disabled={isPending("role", user.id)}
              value={selectedRoleId}
              onChange={(event) => setSelectedRoleId(Number.parseInt(event.target.value, 10))}
            >
              {roles.map((role) => (
                <option key={role.id} value={role.id}>
                  {role.name}
                </option>
              ))}
            </select>
            <button
              className="button button--secondary button--small"
              disabled={isPending("role", user.id)}
              type="button"
              onClick={() => void onUpdateRole(user.id, selectedRoleId, user.username)}
            >
              {isPending("role", user.id) ? "Updating..." : "Save"}
            </button>
          </div>
        </div>
      </td>

      <td className="admin-users-table__status-cell">
        <span
          className={`admin-status-badge${
            user.is_active ? " admin-status-badge--active" : ""
          }`}
        >
          <span aria-hidden="true" className="admin-status-badge__dot" />
          {user.is_active ? "Active" : "Inactive"}
        </span>
      </td>

      <td className="admin-users-table__actions-cell">
        <div className="admin-users-table__actions">
          <button
            aria-label={`Edit ${user.username}`}
            className="admin-icon-button"
            type="button"
            onClick={() => onOpenEditUser(user)}
          >
            Edit
          </button>
          <button
            aria-label={`Change password for ${user.username}`}
            className="admin-icon-button admin-icon-button--amber"
            type="button"
            onClick={() => onOpenPasswordUser(user)}
          >
            Password
          </button>
          <button
            aria-label={`${user.is_active ? "Disable" : "Enable"} ${user.username}`}
            className="admin-icon-button admin-icon-button--slate"
            disabled={isPending("status", user.id)}
            type="button"
            onClick={() => void onToggleStatus(user.id, !user.is_active, user.username)}
          >
            {isPending("status", user.id)
              ? "Updating..."
              : user.is_active
                ? "Disable"
                : "Enable"}
          </button>
          <button
            aria-label={`Delete ${user.username}`}
            className="admin-icon-button admin-icon-button--danger"
            disabled={isPending("delete", user.id)}
            type="button"
            onClick={() => void onDeleteUser(user.id, user.username)}
          >
            {isPending("delete", user.id) ? "Deleting..." : "Delete"}
          </button>
        </div>
      </td>
    </tr>
  );
}

export function AdminUsersTable({
  users,
  roles,
  isPending,
  onUpdateRole,
  onToggleStatus,
  onDeleteUser,
  onOpenEditUser,
  onOpenPasswordUser,
}: AdminUsersTableProps) {
  return (
    <div className="admin-users-table-card">
      <div className="admin-users-table-card__scroll">
        <table className="admin-users-table">
          <thead>
            <tr>
              <th>User</th>
              <th>Role</th>
              <th>Status</th>
              <th className="admin-users-table__actions-heading">Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <AdminUserRow
                isPending={isPending}
                key={user.id}
                onDeleteUser={onDeleteUser}
                onOpenEditUser={onOpenEditUser}
                onOpenPasswordUser={onOpenPasswordUser}
                onToggleStatus={onToggleStatus}
                onUpdateRole={onUpdateRole}
                roles={roles}
                user={user}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
