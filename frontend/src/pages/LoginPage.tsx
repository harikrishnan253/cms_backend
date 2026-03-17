import { FormEvent, useEffect, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { getApiErrorMessage } from "@/api/client";
import { getSession } from "@/api/session";
import { AuthButton } from "@/features/session/components/AuthButton";
import { AuthCard } from "@/features/session/components/AuthCard";
import { AuthErrorBlock } from "@/features/session/components/AuthErrorBlock";
import { AuthInput } from "@/features/session/components/AuthInput";
import { useLogin } from "@/features/session/useLogin";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { uiPaths } from "@/utils/appPaths";

export function LoginPage() {
  useDocumentTitle("CMS Login");
  const navigate = useNavigate();
  const loginMutation = useLogin();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const sessionQuery = useQuery({
    queryKey: ["session"],
    queryFn: getSession,
    staleTime: 60_000,
    retry: 1,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (!loginMutation.isSuccess) {
      return;
    }

    navigate(uiPaths.dashboard, { replace: true });
  }, [loginMutation.isSuccess, navigate]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    loginMutation.mutate({
      username,
      password,
      redirect_to: uiPaths.dashboard,
    });
  }

  if (sessionQuery.isPending) {
    return (
      <AuthCard
        subtitle={
          <>
            Or{" "}
            <Link className="auth-page__link" to={uiPaths.register}>
              create a new account
            </Link>
          </>
        }
        title="Sign in to your account"
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
            <Link className="auth-page__link" to={uiPaths.register}>
              create a new account
            </Link>
          </>
        }
        title="Sign in to your account"
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
          <Link className="auth-page__link" to={uiPaths.register}>
            create a new account
          </Link>
        </>
      }
      title="Sign in to your account"
    >
      <form className="auth-form" onSubmit={handleSubmit}>
        {loginMutation.isError ? (
          <AuthErrorBlock message={getApiErrorMessage(loginMutation.error, "Login failed.")} />
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
          autoComplete="current-password"
          id="password"
          label="Password"
          name="password"
          onChange={(event) => setPassword(event.target.value)}
          required
          type="password"
          value={password}
        />
        <div className="auth-meta-row">
          <label className="auth-checkbox">
            <input className="auth-checkbox__input" id="remember-me" name="remember-me" type="checkbox" />
            <span className="auth-checkbox__label">Remember me</span>
          </label>
          <a className="auth-page__link auth-page__link--small" href="#">
            Forgot your password?
          </a>
        </div>
        <div className="auth-actions auth-actions--single">
          <AuthButton disabled={loginMutation.isPending} type="submit">
            {loginMutation.isPending ? "Signing in..." : "Sign in"}
          </AuthButton>
        </div>
      </form>
    </AuthCard>
  );
}
