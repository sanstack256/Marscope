import React from "react";

interface StatusBadgeProps {
  status: string;
  label?: string;
}

export function StatusBadge({ status, label }: StatusBadgeProps) {
  const normalized = status.toLowerCase();
  let classes = "bg-slate-800/80 text-slate-300 border-slate-700/70";
  if (
    [
      "verified",
      "processed",
      "indexed",
      "product_validated",
      "integrity_validated",
      "eligible",
      "feasible_under_configured_model",
      "feasible_with_explicit_constraints",
      "satisfied",
      "current",
      "pass",
    ].includes(normalized)
  ) {
    classes = "bg-emerald-950/60 text-emerald-300 border-emerald-700/50";
  } else if (
    [
      "pending",
      "available",
      "discovered",
      "downloaded",
      "downloading",
      "download_pending",
      "processing",
      "processing_pending",
      "limited",
      "eligible_with_limitations",
      "conditionally_eligible",
      "partially_satisfied",
      "incomplete_constraint_evaluation",
      "stale_upstream_dependency_changed",
    ].includes(normalized)
  ) {
    classes = "bg-amber-950/60 text-amber-200 border-amber-700/50";
  } else if (
    [
      "failed",
      "rejected",
      "infeasible",
      "infeasible_under_configured_model",
      "mismatch",
      "corrupt",
      "disqualified",
      "unsatisfied",
      "blocked_by_unknown_inputs",
      "blocked_by_data_gap",
      "fail",
    ].includes(normalized)
  ) {
    classes = "bg-red-950/60 text-red-200 border-red-700/50";
  } else if (["unverified", "unknown", "unavailable", "not_applicable", "not_evaluated", "incomplete_inputs"].includes(normalized)) {
    classes = "bg-slate-900 text-slate-400 border-slate-700";
  }

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded border text-[10px] font-mono uppercase tracking-wide ${classes}`}
    >
      {label ?? status}
    </span>
  );
}
