# Advisory workflow

Greenfield and brownfield advice use one pipeline. Brownfield adds an optional atlas and focused
query loop.

```mermaid
sequenceDiagram
    actor User
    participant CLI
    participant Workflow
    participant Cases
    participant Atlas
    participant Policies
    participant Reasoner
    participant Validator
    participant Runs

    User->>CLI: advise case --repo path
    CLI->>Workflow: advise(case_id, latest_atlas)
    Workflow->>Cases: load immutable revision
    Workflow->>Reasoner: discover_design_forces(global_context)
    loop at most configured zoom iterations
        Workflow->>Reasoner: plan_atlas_queries(summary, surfaced IDs)
        Workflow->>Atlas: validate and execute bounded queries
        Atlas-->>Workflow: focused results and excerpts
    end
    Workflow->>Policies: retrieve per force cluster
    Workflow->>Reasoner: analyze focused packet
    Workflow->>Reasoner: alternatives and scenarios
    Workflow->>Reasoner: synthesize from summaries and packets
    Workflow->>Validator: validate atlas and policy references
    alt invalid
        Workflow->>Reasoner: one constrained repair
        Workflow->>Validator: validate again
    end
    Workflow->>Runs: persist immutable run and report
    Workflow->>Cases: append recommendation revision
    Workflow-->>CLI: Markdown or JSON
```

Global context contains only the case summary, goals, constraints, future changes, non-goals,
facts, assumptions, and optional high-level atlas summary. A focused packet contains one concern
cluster, its rationale, selected nodes, metrics and blast-radius results, small excerpts, related
tests, retrieved policies, assumptions, and uncertainty.

The final reasoner receives structured concern analyses, not the full atlas. Reference validation
permits one repair constrained to the surfaced node IDs and retrieved policy IDs. Remaining errors
fail the run explicitly.

