import type { Value } from "./api";
import type { ReactNode } from "react";

const names: Record<string, string> = {
  pending: "Not started", running: "In progress", succeeded: "Complete",
  failed: "Failed", skipped: "Skipped", cancelled: "Cancelled",
};
export function BuildProgress({ build, children, showSteps = true }: { build: Value; children?: ReactNode; showSteps?: boolean }) {
  const steps = build.steps?.length ? build.steps : Object.entries(build.results || {}).map(([format, result]) => ({
    id: format, label: format.toUpperCase(), state: (result as Value).state,
  }));
  return <details className="build-progress">
    <summary>Details</summary>
    {showSteps && (steps.length ? <ol aria-label="Build steps">
      {steps.map((step: Value) => <li key={step.id} className={`step-${step.state}`}>
        <span className="step-icon" role="img" aria-label={names[step.state] || step.state}>
          {step.state === "succeeded" ? "✓" : step.state === "failed" ? "✕" : step.state === "running" ? "…" : "–"}
        </span>
        <span>{step.label}{step.pass_number ? <small> · PDF pass {step.pass_number}{step.phase === "bibliography" ? " · bibliography" : ""}</small> : null}</span>
      </li>)}
    </ol> : <p className="hint">Detailed steps were not recorded for this build yet.</p>)}
    {children}
  </details>;
}
