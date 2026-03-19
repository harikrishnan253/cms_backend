import type { PropsWithChildren } from "react";
import { Navigate } from "react-router-dom";

import { getApiErrorMessage } from "@/api/client";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { useSessionBootstrap } from "@/features/session/useSessionBootstrap";
import { uiPaths } from "@/utils/appPaths";

export function SessionGate({ children }: PropsWithChildren) {
  const sessionQuery = useSessionBootstrap();

  if (sessionQuery.isPending) {
    return (
      <LoadingState
        title="Loading CMS session"
        message="Checking your current browser session before the UI shell loads."
      />
    );
  }

  if (sessionQuery.isError) {
    return (
      <ErrorState
        title="Session bootstrap failed"
        message={getApiErrorMessage(sessionQuery.error, "Failed to bootstrap the CMS session.")}
        actions={
          <>
            <button className="button" onClick={() => sessionQuery.refetch()}>
              Retry
            </button>
          </>
        }
      />
    );
  }

  if (!sessionQuery.data?.authenticated) {
    return <Navigate replace to={uiPaths.login} />;
  }

  return <>{children}</>;
}
