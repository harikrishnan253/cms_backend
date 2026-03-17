import { useEffect, useState } from "react";

import type { AdminUser } from "@/types/api";

interface AdminPasswordFormProps {
  user: AdminUser;
  isPending: boolean;
  onSubmit: (password: string) => Promise<unknown>;
  onCancel: () => void;
}

export function AdminPasswordForm({
  user,
  isPending,
  onSubmit,
  onCancel,
}: AdminPasswordFormProps) {
  const [password, setPassword] = useState("");

  useEffect(() => {
    setPassword("");
  }, [user.id]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!password) {
      return;
    }

    await onSubmit(password);
    setPassword("");
  }

  return (
    <section className="admin-form-card admin-form-card--password">
      <div className="admin-form-card__header">
        <div>
          <h2>Change Password</h2>
          <p>
            Update password for user: <strong>{user.username}</strong>
          </p>
        </div>
      </div>

      <form className="admin-form-grid admin-form-card__grid" onSubmit={handleSubmit}>
        <label className="field">
          <span>New Password</span>
          <input
            className="search-input admin-form-card__input"
            disabled={isPending}
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>

        <div className="upload-actions admin-form-card__actions">
          <button className="button" disabled={isPending || password.length === 0} type="submit">
            {isPending ? "Updating..." : "Update Password"}
          </button>
          <button
            className="button button--secondary"
            disabled={isPending}
            type="button"
            onClick={onCancel}
          >
            Back to Users
          </button>
        </div>
      </form>
    </section>
  );
}
