import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpenText,
  FolderPlus,
  RefreshCw,
  Search,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { api } from "../api";
import {
  Badge,
  ErrorPanel,
  Loading,
  PageHeader,
  useDialogFocus,
} from "../components";
import { policyApplicabilityLabel } from "../policy-applicability";
import type { Policy } from "../types";

export function filterPolicies(
  policies: Policy[],
  search: string,
  scope: string,
): Policy[] {
  const term = search.trim().toLocaleLowerCase();
  return policies.filter(
    (policy) =>
      (scope === "all" || policy.scope === scope) &&
      (!term ||
        `${policy.id} ${policy.title} ${policy.tags.join(" ")} ${policy.body} ${policy.applies_to || ""}`
          .toLocaleLowerCase()
          .includes(term)),
  );
}

export function PoliciesPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [scope, setScope] = useState("all");
  const [selected, setSelected] = useState<Policy | null>(null);
  const [source, setSource] = useState("");
  const closePolicy = useCallback(() => setSelected(null), []);
  const policyDialogRef = useDialogFocus(closePolicy, selected !== null);
  const policies = useQuery({ queryKey: ["policies"], queryFn: api.policies });
  const sources = useQuery({ queryKey: ["policy-sources"], queryFn: api.policySources });
  const addSource = useMutation({
    mutationFn: api.addPolicySource,
    onSuccess: () => {
      setSource("");
      void queryClient.invalidateQueries({ queryKey: ["policy-sources"] });
      void queryClient.invalidateQueries({ queryKey: ["policies"] });
    },
  });
  const removeSource = useMutation({
    mutationFn: api.removePolicySource,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["policy-sources"] });
      void queryClient.invalidateQueries({ queryKey: ["policies"] });
    },
  });
  const rebuild = useMutation({
    mutationFn: api.rebuildPolicies,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["workspace"] }),
  });

  const scopes = useMemo(
    () => [...new Set((policies.data || []).map((policy) => policy.scope))],
    [policies.data],
  );
  const filtered = useMemo(() => {
    return filterPolicies(policies.data || [], search, scope);
  }, [policies.data, scope, search]);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Normative guidance, not automatic lint"
        title="Policy library"
        description="Browse authored policy documents and manage the sources included in consultation retrieval."
        action={
          <button
            className="button button--primary"
            type="button"
            disabled={rebuild.isPending}
            onClick={() => rebuild.mutate()}
          >
            <RefreshCw size={16} className={rebuild.isPending ? "spin" : ""} />
            {rebuild.isPending ? "Rebuilding…" : "Rebuild index"}
          </button>
        }
      />
      {(policies.error || sources.error || addSource.error || removeSource.error || rebuild.error) && (
        <ErrorPanel
          error={
            policies.error ||
            sources.error ||
            addSource.error ||
            removeSource.error ||
            rebuild.error
          }
        />
      )}

      <section className="policy-toolbar">
        <label className="search-field">
          <Search size={17} />
          <span className="sr-only">Search policies</span>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search intent, tags, or guidance…"
          />
        </label>
        <div className="segmented" aria-label="Filter by policy scope">
          <button className={scope === "all" ? "active" : ""} onClick={() => setScope("all")}>All</button>
          {scopes.map((item) => (
            <button key={item} className={scope === item ? "active" : ""} onClick={() => setScope(item)}>
              {item}
            </button>
          ))}
        </div>
        <span className="result-count">{filtered.length} policies</span>
      </section>

      {policies.isLoading ? (
        <Loading label="Reading authored policies…" />
      ) : (
        <div className="policy-grid">
          {filtered.map((policy) => (
            <button type="button" className="policy-card" key={policy.id} onClick={() => setSelected(policy)}>
              <div>
                <span className="policy-card__icon"><ShieldCheck size={18} /></span>
                <Badge tone={policy.strength === "required" ? "warning" : "neutral"}>
                  {policy.strength}
                </Badge>
              </div>
              <h2>{policy.title}</h2>
              <p>{policy.body.split("##")[1]?.replace(/^[^\n]+\n/, "").trim().slice(0, 180)}…</p>
              <footer>
                <code>{policy.id}</code>
                <span title={policy.applies_to || undefined}>
                  {policyApplicabilityLabel(policy.scope, policy.applies_to)}
                </span>
              </footer>
            </button>
          ))}
        </div>
      )}

      <section className="panel source-panel">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Workspace configuration</span>
            <h2>Additional policy sources</h2>
            <p>Files remain authored outside Arch Compass; source registration is persistent.</p>
          </div>
        </div>
        <div className="source-add">
          <FolderPlus size={20} />
          <label>
            <span>Policy file or directory</span>
            <input
              value={source}
              onChange={(event) => setSource(event.target.value)}
              placeholder="/absolute/path/to/team-policies"
            />
          </label>
          <button
            className="button button--secondary"
            disabled={!source.trim() || addSource.isPending}
            onClick={() => addSource.mutate(source.trim())}
          >
            Add source
          </button>
        </div>
        <div className="source-list">
          {sources.data?.map((item) => (
            <div key={item.canonical_path}>
              <BookOpenText size={17} />
              <code>{item.canonical_path}</code>
              <button
                type="button"
                className="icon-button"
                aria-label={`Remove ${item.canonical_path}`}
                onClick={() => removeSource.mutate(item.canonical_path)}
              >
                <Trash2 size={16} />
              </button>
            </div>
          ))}
          {!sources.data?.length && <p className="muted">Only the bundled Arch Compass corpus is active.</p>}
        </div>
      </section>

      {selected && (
        <div className="drawer-backdrop" role="presentation" onMouseDown={closePolicy}>
          <aside
            ref={policyDialogRef}
            className="policy-drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="policy-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <button className="drawer-close" type="button" aria-label="Close policy" onClick={closePolicy}>
              <X size={20} />
            </button>
            <Badge tone="teal">{selected.scope}</Badge>
            <h2 id="policy-title">{selected.title}</h2>
            <code>{selected.id}</code>
            <div className="policy-meta">
              <span>Strength <strong>{selected.strength}</strong></span>
              <span>Author <strong>{selected.source.author}</strong></span>
              <span>Tags <strong>{selected.tags.join(", ")}</strong></span>
              <span>
                Applies to
                <strong>
                  {policyApplicabilityLabel(selected.scope, selected.applies_to)}
                </strong>
              </span>
            </div>
            <div className="markdown policy-markdown">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{selected.body}</ReactMarkdown>
            </div>
            <footer><code>{selected.source_path}</code></footer>
          </aside>
        </div>
      )}
    </div>
  );
}
