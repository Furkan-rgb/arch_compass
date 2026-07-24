export function policyApplicabilityLabel(
  scope: string,
  appliesTo?: string | null,
): string {
  const normalizedScope = scope.replaceAll("_", " ");
  if (scope === "general") return "All contexts";
  if (!appliesTo) return `${normalizedScope} · identity unavailable`;
  return `${normalizedScope} · ${appliesTo}`;
}
