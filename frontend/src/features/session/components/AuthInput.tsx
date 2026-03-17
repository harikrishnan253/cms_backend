import type { InputHTMLAttributes } from "react";

type AuthInputProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
};

export function AuthInput({ id, label, type = "text", ...inputProps }: AuthInputProps) {
  return (
    <div className="auth-field">
      <label className="auth-field__label" htmlFor={id}>
        {label}
      </label>
      <div className="auth-field__control">
        <input className="auth-field__input" id={id} type={type} {...inputProps} />
      </div>
    </div>
  );
}
