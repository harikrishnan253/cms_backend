import type { ButtonHTMLAttributes, ReactNode } from "react";

type AuthButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
};

export function AuthButton({ children, type = "button", ...buttonProps }: AuthButtonProps) {
  return (
    <button className="auth-button" type={type} {...buttonProps}>
      {children}
    </button>
  );
}
