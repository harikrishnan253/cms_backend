import { useState } from "react";
import { Link } from "react-router-dom";

import { getApiErrorMessage } from "@/api/client";
import { EmptyState } from "@/components/ui/EmptyState";
import { AdminCreateUserForm } from "@/features/admin/components/AdminCreateUserForm";
import { AdminEditUserForm } from "@/features/admin/components/AdminEditUserForm";
import { AdminPasswordForm } from "@/features/admin/components/AdminPasswordForm";
import { AdminUsersTable } from "@/features/admin/components/AdminUsersTable";
import { useAdminMutations } from "@/features/admin/useAdminMutations";
import { useAdminUsersQuery } from "@/features/admin/useAdminUsersQuery";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import type { AdminUser } from "@/types/api";
import { getSsrUrl, ssrPaths, uiPaths } from "@/utils/appPaths";

type AdminModalState =
  | { kind: "create" }
  | { kind: "edit"; user: AdminUser }
  | { kind: "password"; user: AdminUser }
  | null;

export function AdminUsersPage() {
  useDocumentTitle("CMS UI Admin Users");
  const usersQuery = useAdminUsersQuery(0, 100);
  const adminMutations = useAdminMutations();
  const [modalState, setModalState] = useState<AdminModalState>(null);

  if (usersQuery.isPending) {
    return (
      <main className="page admin-users-page admin-users-page--state">
        <section className="panel admin-users-state-card">
          <div className="admin-users-state-card__icon">...</div>
          <h1 className="admin-users-state-card__title">Loading admin users</h1>
          <p className="admin-users-state-card__message">
            Fetching the current /api/v2 admin users contract.
          </p>
        </section>
      </main>
    );
  }

  if (usersQuery.isError) {
    return (
      <main className="page admin-users-page admin-users-page--state">
        <section className="panel admin-users-state-card admin-users-state-card--error">
          <div className="admin-users-state-card__icon">!</div>
          <h1 className="admin-users-state-card__title">Admin users unavailable</h1>
          <p className="admin-users-state-card__message">
            {getApiErrorMessage(
              usersQuery.error,
              "The frontend shell could not load the admin users contract.",
            )}
          </p>
          <div className="admin-users-state-card__actions">
            <button className="button" onClick={() => void usersQuery.refetch()} type="button">
              Retry
            </button>
            <Link className="button button--secondary" to={uiPaths.adminDashboard}>
              Back to admin
            </Link>
            <a className="button button--secondary" href={getSsrUrl(ssrPaths.adminUsers)}>
              Open SSR admin users
            </a>
          </div>
        </section>
      </main>
    );
  }

  const { users, roles, pagination } = usersQuery.data;

  return (
    <main className="page admin-users-page">
      <div className="admin-users-shell">
        <div className="admin-users-header">
          <div>
            <h1>User Management</h1>
            <p>Manage system users, roles, and permissions</p>
          </div>
          <div className="admin-users-header__actions">
            <Link className="admin-users-header__back" to={uiPaths.adminDashboard}>
              Back
            </Link>
            <button className="button" type="button" onClick={() => setModalState({ kind: "create" })}>
              Create New User
            </button>
          </div>
        </div>

        <div className="admin-users-shell__meta">
          <span className="helper-text">
            {pagination.total} user{pagination.total === 1 ? "" : "s"} loaded from /api/v2/admin/users.
          </span>
          <a className="link-inline" href={getSsrUrl(ssrPaths.adminUsers)}>
            Open SSR admin users
          </a>
        </div>

        {adminMutations.status ? (
          <div className={`status-banner status-banner--${adminMutations.status.tone}`}>
            {adminMutations.status.message}
          </div>
        ) : null}

        {users.length === 0 ? (
          <EmptyState
            title="No users found"
            message="The current admin users contract returned an empty list."
          />
        ) : (
          <AdminUsersTable
            isPending={adminMutations.isPending}
            onDeleteUser={adminMutations.deleteUser}
            onOpenEditUser={(user) => setModalState({ kind: "edit", user })}
            onOpenPasswordUser={(user) => setModalState({ kind: "password", user })}
            onToggleStatus={adminMutations.toggleStatus}
            onUpdateRole={adminMutations.updateRole}
            roles={roles}
            users={users}
          />
        )}
      </div>

      {modalState ? (
        <div className="admin-dialog-backdrop" role="presentation">
          <div className="admin-dialog" role="dialog">
            {modalState.kind === "create" ? (
              <AdminCreateUserForm
                isPending={adminMutations.isPending("create")}
                onCancel={() => setModalState(null)}
                onSubmit={async (payload) => {
                  await adminMutations.createUser({
                    username: payload.username,
                    email: payload.email,
                    password: payload.password,
                    role_id: payload.roleId,
                  });
                  setModalState(null);
                }}
                roles={roles}
              />
            ) : null}

            {modalState?.kind === "edit" ? (
              <AdminEditUserForm
                isPending={adminMutations.isPending("edit", modalState.user.id)}
                onCancel={() => setModalState(null)}
                onSubmit={async (email) => {
                  await adminMutations.editUser(modalState.user.id, email, modalState.user.username);
                  setModalState(null);
                }}
                user={modalState.user}
              />
            ) : null}

            {modalState?.kind === "password" ? (
              <AdminPasswordForm
                isPending={adminMutations.isPending("password", modalState.user.id)}
                onCancel={() => setModalState(null)}
                onSubmit={async (password) => {
                  await adminMutations.updatePassword(
                    modalState.user.id,
                    password,
                    modalState.user.username,
                  );
                  setModalState(null);
                }}
                user={modalState.user}
              />
            ) : null}
          </div>
        </div>
      ) : null}
    </main>
  );
}
