import { dump } from "js-yaml";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";

import { ErrorPanel, Loading } from "./components";
import type { ArchitectureCase } from "./types";

/**
 * Reading a stored case, as YAML.
 *
 * Reading only. A case used to be authored on this surface too — a skeleton, a form,
 * a paste box — but authoring moved to the review itself: a run without a case asks
 * what it could not weigh, and the answers become the case (master plan §6C.1). Two
 * ways of writing the same document meant a form on the start screen whose correct
 * use was almost always "skip it". YAML remains the exchange format — the CLI still
 * authors cases through `POST /api/cases/import-yaml` — so what this surface shows is
 * exactly what that route accepts.
 */
const caseSurface = "grid gap-3.5 p-[var(--card-pad)]";
const caseHead = "flex items-center justify-between gap-3";
const caseNote = "m-0 text-ui leading-[1.5] text-ink-2";

/** Identity and bookkeeping ArchCompass owns, which nobody authors. */
const GENERATED_KEYS = new Set([
  "schema_version",
  "case_id",
  "revision",
  "created_at",
  "updated_at",
]);

function authoredFields(value: object): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(value).filter(
      ([key, item]) => key !== "id" && item !== null && item !== undefined,
    ),
  );
}

/**
 * A stored case as its author would write it: generated identity removed, empty fields
 * dropped, statement IDs left out. What comes back is YAML the import route would accept
 * unchanged, so reading a case and authoring one stay the same format.
 */
export function caseToYaml(snapshot: ArchitectureCase): string {
  const authored: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(snapshot)) {
    if (GENERATED_KEYS.has(key) || value === null || value === undefined) continue;
    if (Array.isArray(value)) {
      if (!value.length) continue;
      authored[key] = value.map((item) =>
        item && typeof item === "object" ? authoredFields(item) : item,
      );
      continue;
    }
    if (typeof value === "object") {
      const nested = authoredFields(value);
      if (Object.keys(nested).length) authored[key] = nested;
      continue;
    }
    authored[key] = value;
  }
  return dump(authored, { lineWidth: 88, noRefs: true });
}

export function CaseView({
  snapshot,
  loading,
  error,
  onRetry,
  retrying,
  onClose,
}: {
  snapshot: ArchitectureCase | undefined;
  loading: boolean;
  error: unknown;
  /**
   * Read the stored revision again.
   *
   * Worth wiring here: nothing on this surface asks for anything, so a failed read
   * leaves a panel with a strip in it and no way to try again short of closing the
   * layer and finding the case in the rail a second time.
   */
  onRetry?: () => void;
  retrying?: boolean;
  onClose: () => void;
}) {
  return (
    <div className={caseSurface}>
      <div className={caseHead}>
        <h3 className="m-0 text-sub">{snapshot?.title || "Case"}</h3>
        <Button type="button" size="icon" onClick={onClose} aria-label="Close the case">
          <X size={16} aria-hidden />
        </Button>
      </div>
      {loading ? <Loading label="Reading the case…" /> : null}
      {error ? (
        <ErrorPanel
          error={error}
          onRetry={onRetry}
          retrying={retrying}
          retryLabel="Read it again"
        />
      ) : null}
      {snapshot ? (
        // Styled by a rule rather than by utilities: see `[data-slot="case-yaml"]`.
        <pre data-slot="case-yaml">{caseToYaml(snapshot)}</pre>
      ) : null}
      <p className={caseNote}>
        Revision {snapshot?.revision ?? "?"}, exactly as a review would pin it.
      </p>
    </div>
  );
}
