import { FormEvent, useEffect, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { getApiErrorMessage } from "@/api/client";
import { getSession } from "@/api/session";
import { AuthButton } from "@/features/session/components/AuthButton";
import { AuthCard } from "@/features/session/components/AuthCard";
import { AuthErrorBlock } from "@/features/session/components/AuthErrorBlock";
import { AuthInput } from "@/features/session/components/AuthInput";
import { getRegisterErrorMessage, useRegister } from "@/features/session/useRegister";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { uiPaths } from "@/utils/appPaths";

export function RegisterPage() {
  useDocumentTitle("CMS Register");
  const navigate = useNavigate();
  const registerMutation = useRegister();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const sessionQuery = useQuery({
    queryKey: ["session"],
    queryFn: getSession,
    staleTime: 60_000,
    retry: 1,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (!registerMutation.isSuccess) {
      return;
    }

    navigate(uiPaths.login, { replace: true });
  }, [registerMutation.isSuccess, navigate]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    registerMutation.mutate({
      username,
      email,
      password,
      confirm_password: confirmPassword,
      redirect_to: uiPaths.login,
    });
  }

  if (sessionQuery.isPending) {
    return (
      <AuthCard
        subtitle={
          <>
            Or{" "}
            <Link className="auth-page__link" to={uiPaths.login}>
              sign in to your existing account
            </Link>
          </>
        }
        title="Create a new account"
      >
        <form className="auth-form" onSubmit={(event) => event.preventDefault()}>
          <div className="auth-loading-copy">Checking whether you already have an active CMS session.</div>
        </form>
      </AuthCard>
    );
  }

  if (sessionQuery.isError) {
    return (
      <AuthCard
        subtitle={
          <>
            Or{" "}
            <Link className="auth-page__link" to={uiPaths.login}>
              sign in to your existing account
            </Link>
          </>
        }
        title="Create a new account"
      >
        <div className="auth-form">
          <AuthErrorBlock
            message={getApiErrorMessage(
              sessionQuery.error,
              "The frontend could not verify the current CMS session.",
            )}
          />
          <div className="auth-actions auth-actions--single">
            <AuthButton onClick={() => sessionQuery.refetch()} type="button">
              Retry
            </AuthButton>
          </div>
        </div>
      </AuthCard>
    );
  }

  if (sessionQuery.data?.authenticated) {
    return <Navigate replace to={uiPaths.dashboard} />;
  }

  return (
    <AuthCard
      subtitle={
        <>
          Or{" "}
          <Link className="auth-page__link" to={uiPaths.login}>
            sign in to your existing account
          </Link>
        </>
      }
      title="Create a new account"
    >
      <form className="auth-form" onSubmit={handleSubmit}>
        {registerMutation.isError ? (
          <AuthErrorBlock message={getRegisterErrorMessage(registerMutation.error)} />
        ) : null}
        <AuthInput
          autoComplete="username"
          id="username"
          label="Username"
          name="username"
          onChange={(event) => setUsername(event.target.value)}
          required
          type="text"
          value={username}
        />
        <AuthInput
          autoComplete="email"
          id="email"
          label="Email address"
          name="email"
          onChange={(event) => setEmail(event.target.value)}
          required
          type="email"
          value={email}
        />
        <AuthInput
          autoComplete="new-password"
          id="password"
          label="Password"
          name="password"
          onChange={(event) => setPassword(event.target.value)}
          required
          type="password"
          value={password}
        />
        <AuthInput
          autoComplete="new-password"
          id="confirm_password"
          label="Confirm Password"
          name="confirm_password"
          onChange={(event) => setConfirmPassword(event.target.value)}
          required
          type="password"
          value={confirmPassword}
        />
        <div className="auth-actions auth-actions--single">
          <AuthButton disabled={registerMutation.isPending} type="submit">
            {registerMutation.isPending ? "Creating account..." : "Create Account"}
          </AuthButton>
        </div>
      </form>
    </AuthCard>
  );
}
