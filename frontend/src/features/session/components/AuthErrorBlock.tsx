type AuthErrorBlockProps = {
  message: string;
};

export function AuthErrorBlock({ message }: AuthErrorBlockProps) {
  return (
    <div aria-live="polite" className="auth-alert auth-alert--error" role="alert">
      <div className="auth-alert__icon-wrap" aria-hidden="true">
        <svg className="auth-alert__icon" viewBox="0 0 20 20">
          <path d="M2.93 17.07A10 10 0 1 1 17.07 2.93 10 10 0 0 1 2.93 17.07zm12.73-1.41A8 8 0 1 0 4.34 4.34a8 8 0 0 0 11.32 11.32zM9 11V9h2v6H9v-4zm0-6h2v2H9V5z" />
        </svg>
      </div>
      <div>
        <p className="auth-alert__title">Error</p>
        <p className="auth-alert__message">{message}</p>
      </div>
    </div>
  );
}
