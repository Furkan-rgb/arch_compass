/** The band along the foot of the map: what was measured about the selected node. */

import type { AtlasNodeView } from "./graph-model";

export function AtlasMetricStrip({ node }: { node: AtlasNodeView }) {
  return (
    <div className="atlas-metric-strip" aria-label={`Metrics for ${node.label}`}>
      {(node.metrics.length
        ? node.metrics.slice(0, 5)
        : [{ label: "Evidence references", value: node.evidenceCount || 0 }]
      ).map((metric) => (
        <div key={`${metric.group}-${metric.label}`}>
          <span>{metric.group || "Metric"}</span>
          <strong>{metric.value}</strong>
          <small
            title={[
              metric.definition,
              metric.limitations,
              metric.scope
                ? `Scope: ${metric.scope.replaceAll("_", " ")}`
                : "",
            ].filter(Boolean).join(" · ")}
          >
            {metric.label}
          </small>
        </div>
      ))}
    </div>
  );
}
