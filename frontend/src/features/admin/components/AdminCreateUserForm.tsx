import { useState } from "react";

import type { AdminRole } from "@/types/api";

interface AdminCreateUserFormProps {
  roles: AdminRole[];
  isPending: boolean;
  onSubmit: (payload: {
    username: string;
    email: string;
    password: string;
    roleId: number;
  }) => Promise<unknown>;
  onCancel?: () => void;
}

export function AdminCreateUserForm({
  roles,
  isPending,
  onSubmit,
  onCancel,
}: AdminCreateUserFormProps) {
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [roleId, setRoleId] = useState<number>(roles[0]?.id ?? 0);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!username.trim() || !email.trim() || !password || !roleId) {
      return;
    }

    await onSubmit({
      username: username.trim(),
      email: email.trim(),
      password,
      roleId,
    });

    setUsername("");
    setEmail("");
    setPassword("");
    setRoleId(roles[0]?.id ?? 0);
  }

  return (
    <section className="admin-form-card admin-form-card--create">
      <div className="admin-form-card__header">
        <div>
          <h2>Create New User</h2>
          <p>Add a new user to the system</p>
        </div>
        {onCancel ? (
          <button className="admin-form-card__back" disabled={isPending} type="button" onClick={onCancel}>
            Back to Users
          </button>
        ) : null}
      </div>

      <form className="admin-form-grid admin-form-card__grid" onSubmit={handleSubmit}>
        <label className="field">
          <span>Username</span>
          <input
            className="search-input admin-form-card__input"
            disabled={isPending}
            placeholder="e.g. john_doe"
            type="text"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
        </label>
        <label className="field">
          <span>Email</span>
          <input
            className="search-input admin-form-card__input"
            disabled={isPending}
            placeholder="e.g. john@example.com"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>
        <label className="field">
          <span>Password</span>
          <input
            className="search-input admin-form-card__input"
            disabled={isPending}
            placeholder="Min. 6 characters"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <label className="field">
          <span>Role</span>
          <select
            className="select-input admin-form-card__input"
            disabled={isPending}
            value={roleId}
            onChange={(event) => setRoleId(Number.parseInt(event.target.value, 10))}
          >
            {roles.map((role) => (
              <option key={role.id} value={role.id}>
                {role.name}
                {role.description ? ` - ${role.description}` : ""}
              </option>
            ))}
          </select>
        </label>
        <div className="upload-actions admin-form-card__actions">
          <button className="button" disabled={isPending || roles.length === 0} type="submit">
            {isPending ? "Creating..." : "Create User"}
          </button>
        </div>
      </form>
    </section>
  );
}
