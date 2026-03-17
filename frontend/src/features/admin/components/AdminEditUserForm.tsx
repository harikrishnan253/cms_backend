import { useEffect, useState } from "react";

import type { AdminUser } from "@/types/api";

interface AdminEditUserFormProps {
  user: AdminUser;
  isPending: boolean;
  onSubmit: (email: string) => Promise<unknown>;
  onCancel: () => void;
}

export function AdminEditUserForm({
  user,
  isPending,
  onSubmit,
  onCancel,
}: AdminEditUserFormProps) {
  const [email, setEmail] = useState(user.email);

  useEffect(() => {
    setEmail(user.email);
  }, [user.email, user.id]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onSubmit(email);
  }

  return (
    <section className="admin-form-card admin-form-card--edit">
      <div className="admin-form-card__header">
        <div>
          <h2>Edit User: {user.username}</h2>
          <p>Update the current user email address.</p>
        </div>
      </div>

      <form className="admin-form-grid admin-form-card__grid" onSubmit={handleSubmit}>
        <label className="field">
          <span>Email</span>
          <input
            className="search-input admin-form-card__input"
            disabled={isPending}
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>

        <div className="upload-actions admin-form-card__actions">
          <button className="button" disabled={isPending} type="submit">
            {isPending ? "Saving..." : "Save Changes"}
          </button>
          <button
            className="button button--secondary"
            disabled={isPending}
            type="button"
            onClick={onCancel}
          >
            Cancel
          </button>
        </div>
      </form>
    </section>
  );
}
