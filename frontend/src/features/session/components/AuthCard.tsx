import type { ReactNode } from "react";



type AuthCardProps = {
  title: string;
  subtitle: ReactNode;
  children: ReactNode;
};

export function AuthCard({ title, subtitle, children }: AuthCardProps) {
  return (
    <main className="auth-page">
      <div className="auth-page__brand">
        <div className="auth-page__logo-wrap">
          <img
            alt="S4Carlisle Logo"
            className="auth-page__logo"
            src="/logo.png"
          />
        </div>
        <h2 className="auth-page__title">{title}</h2>
        <p className="auth-page__subtitle">{subtitle}</p>
      </div>

      <div className="auth-card">{children}</div>
    </main>
  );
}
