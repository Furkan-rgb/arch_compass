import type { FailureDiagnostic } from "./types";

export function describeFailureDiagnostic(diagnostic: FailureDiagnostic): string {
  switch (diagnostic.code) {
    case "cluster_count_out_of_range":
      return `Expected between 1 and 4 concern clusters; the model returned ${diagnostic.count ?? 0}.`;
    case "unknown_force_references": {
      const count = diagnostic.count ?? 0;
      return `The model returned ${count} unrecognized force ${count === 1 ? "reference" : "references"}; only the supplied F-number handles are allowed.`;
    }
    case "missing_force_references":
      return `Missing force handles: ${diagnostic.force_handles.join(", ")}.`;
    case "duplicate_force_references":
      return `Repeated force handles: ${diagnostic.force_handles.join(", ")}.`;
    case "duplicate_cluster_ids": {
      const count = diagnostic.count ?? 0;
      return `The model returned ${count} duplicate concern cluster ${count === 1 ? "ID" : "IDs"}.`;
    }
  }
}

export function FailureDiagnostics({
  diagnostics,
}: {
  diagnostics: FailureDiagnostic[];
}) {
  if (!diagnostics.length) return null;
  return (
    <div className="failure-diagnostics">
      <p>
        The clustering result was rejected before repository investigation because
        it did not assign every force exactly once.
      </p>
      <ul>
        {diagnostics.map((diagnostic, index) => (
          <li key={`${diagnostic.code}-${index}`}>
            {describeFailureDiagnostic(diagnostic)}
          </li>
        ))}
      </ul>
    </div>
  );
}
