import { useNavigate } from "react-router-dom";

import type { StructuringReviewActions } from "@/types/api";

interface StructuringReturnActionProps {
  actions: StructuringReviewActions;
  className?: string;
  label?: string;
}

export function StructuringReturnAction({
  actions,
  className = "button button--secondary",
  label = "Return",
}: StructuringReturnActionProps) {
  const navigate = useNavigate();

  if (actions.return_mode === "route" && actions.return_href) {
    return (
      <a className={className} href={actions.return_href}>
        {label}
      </a>
    );
  }

  return (
    <button className={className} type="button" onClick={() => navigate(-1)}>
      {label}
    </button>
  );
}
