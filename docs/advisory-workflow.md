# Advisory workflow

Greenfield and brownfield advice use one pipeline. Brownfield adds an optional atlas and focused
query loop. The CLI delegates to `AdviceService`; the workflow owns reasoning and the atomic
successful run/case commit, while the report service writes the completed report into the
workspace.

```mermaid
sequenceDiagram
    actor User
    participant CLI
    participant Advice as AdviceService
    participant Workflow
    participant Cases
    participant Atlas
    participant Policies
    participant Reasoner
    participant Validator
    participant Runs
    participant Reports

    User->>CLI: advise case --repo path
    CLI->>Advice: advise(case_id, repository_root)
    Advice->>Workflow: advise(case_id, repository_root)
    Workflow->>Cases: load immutable revision
    Workflow->>Atlas: resolve persisted version and check freshness
    Workflow->>Policies: ensure matching policy index exists
    Workflow->>Reasoner: discover_design_forces(global_context)
    Workflow->>Reasoner: cluster_design_forces(context, forces)
    loop at most configured zoom iterations
        Workflow->>Reasoner: plan cluster-keyed atlas queries
        Workflow->>Atlas: validate and execute bounded queries
        Atlas-->>Workflow: typed summaries, metrics, relations, tests, excerpts
    end
    loop once per concern cluster
        Workflow->>Policies: retrieve policies for cluster
        Workflow->>Reasoner: analyze one focused packet
    end
    Workflow->>Reasoner: alternatives and scenarios
    Workflow->>Reasoner: synthesize across separate concern analyses
    Workflow->>Validator: validate claims, support, atlas locations, policies
    alt invalid
        Workflow->>Validator: one deterministic conservative repair
        Workflow->>Validator: validate again
    end
    Workflow->>Runs: atomically persist successful run
    Workflow->>Cases: atomically append recommendation revision
    Workflow-->>Advice: completed run
    Advice->>Reports: write Markdown and JSON safely
    Advice-->>CLI: completed run
```

Global context contains only the case summary, goals, constraints, future changes, non-goals,
actors/workflows, facts, assumptions, unresolved questions, user-authored design forces, policy
applicability identity, and an optional bounded typed `AtlasOverview`. The overview names
top-level nodes and a small set of hotspots with metric semantics, signals, and selection reasons;
it is not the complete graph. The reasoner must partition all discovered and preserved user
forces exactly once into one to four concern clusters. Invalid, duplicate, omitted, or invented
force references fail structured-output validation.

The case statement is not treated as an exhaustive defect inventory. A typed atlas signal may
seed an additional investigation force even when the user did not name the underlying concern.
That does not turn the signal into a violation: the force and focused query preserve its
measurement/proxy nature and limitations, and the concern analysis must inspect located evidence
before recommending a responsibility move.

Internal force and cluster IDs are application-owned and are never round-tripped through the
reasoning model at these stages. Discovery returns force content only; ArchCompass assigns the
canonical force IDs. For clustering, the adapter exposes the bounded force set as request-local
handles (`F1`, `F2`, and so on), constrains `force_refs` to that closed enum, validates an exact
partition, and maps the handles back to canonical IDs. This is an exact-reference problem, not a
retrieval problem: embeddings and `sqlite-vec` remain appropriate for finding relevant policies
from an open corpus, but are deliberately not used to guess which known force a cluster means.

Each zoom iteration has one cluster-keyed planning call. `max_queries_per_iteration` is a global
budget shared round-robin by every cluster in that iteration so an early cluster cannot consume
all investigation capacity. `max_query_results` limits unique nodes per cluster across the
complete consultation, and `max_excerpt_lines` limits total excerpt lines per cluster. The
workflow clamps excess results and records query, node, relationship, test, and excerpt
truncation in execution metadata.

One `FocusedAnalysisPacket` is built per cluster. It contains explicit self-describing node
evidence, metric definitions and proxy labels, resolved relationship endpoints, related tests,
excerpts, applicable policies, assumptions, and uncertainty. Each packet is analysed once.
Scenario results are keyed by alternative ID and every scenario must cover every alternative
exactly once.

Policy retrieval queries combine the cluster and its design forces with bounded case problem,
outcome, requirements, constraints, and expected changes. Brownfield queries also include only
atlas signals surfaced for that cluster. This lets general policies cover greenfield
responsibility questions while allowing repository observations to sharpen brownfield retrieval.

The final reasoner receives the separate structured concern analyses and canonical policy
summaries, not the focused packets, full atlas, or source tree. Packets remain internal evidence
allowlists for validation and statement-support linking. Reference validation permits one
deterministic, conservative repair constrained to surfaced nodes and retrieved policies. It
removes unsupported evidence rather than asking a model to regenerate the full report. A
repository observation with an invalid source location is removed as a whole; repair never
strips the location while leaving its prose. Remaining errors fail the run explicitly.

Final synthesis also produces one to twelve canonical architectural findings. The model supplies
finding meaning, contextual importance, confidence, response, uncertainty, its concern-cluster
handle, and its claim handles. It supplies no finding evidence: the proposal has no field for
node IDs, locations, metric observations, obscurity signals, or policies, and the application
derives each from the linked claims in that cluster's exact focused packet. The workflow assigns
stable ordered `FIND-nnn` IDs during composition.

A proposal that cites an unknown handle, mixes claims across concern clusters, leaves a cluster
without a finding, or names an unknown disposition is rejected before composition and returned for
one constrained repair. Synthesis itself is never re-run. If the repaired proposal is still
invalid the run fails explicitly at the synthesis stage, and the ArchitectureCase is unchanged. Report conversations begin only after this workflow has completed successfully
and are described separately in
[report-conversations.md](report-conversations.md).

## Atlas selection and audit

For CLI advice, an explicit `--repo` selects that repository's latest persisted atlas. Otherwise
the case's recorded atlas version is used; a case with only a recorded root uses its latest
version. A case without repository data is greenfield. Programmatic `atlas_version_id` selection
also reloads a persisted version; arbitrary unsaved atlas aggregates are never trusted as
evidence. Every selected brownfield atlas is freshness-checked before reasoning.

A successful brownfield consultation records the exact atlas root and version in the next case
revision. The case records only policy IDs cited by the final report or conflict analysis.

After a valid case revision is loaded, any terminal atlas resolution/freshness, policy, query,
provider, structured-output, validation, rendering, or commit failure is persisted as an
immutable failed run before the exception is returned. Runs contain only prompt identities that
were actually executed, stage timings, clusters, plans, packets, analyses, validation errors
before and after repair, repair actions, a failure stage, sanitized errors, safe structured
failure diagnostics, and execution counters/truncations. Clustering diagnostics expose only
request-local `F` handles and allowlisted counts, never model prose, repository paths, or internal
IDs. Failed runs retain partial or invalid model output for diagnosis without applying
success-only partition/coverage invariants, and they never advance the case revision.
