---
id: separate-model-context-from-provider-transport
title: Keep semantic context decisions out of model transport
scope: general
strength: preferred
tags: [model-context, evidence, responsibility, transport, boundaries]
source:
  author: ArchCompass
  inspiration: [hexagonal architecture, information hiding]
---
## Intent
Contain the application decision about what a model may know instead of leaking report interpretation, evidence eligibility, and conversation rules into transport infrastructure.
## Guidance
Let an application-level owner assemble a validated and bounded semantic context object. The model port should accept that context; a transport adapter should encode it for the model API, apply transport-specific options, request the output schema, parse or repair the response, and translate failures. Selecting, merging, excluding, ranking, or truncating domain evidence belongs before that boundary.
## Signals
A model adapter receives a broad case, run, report, or repository aggregate; traverses several nested domain fields; selects or combines findings, claims, policies, evidence, or history; and constructs the outbound request in the same method. Report-schema or evidence-rule changes therefore touch transport code, and selection cannot be tested without the transport adapter.
## Diagnostic questions
Does this method decide what information is authoritative and relevant, or does it only encode an already-decided context? Would changing report structure, evidence eligibility, claim validation, truncation, or history rules require editing model transport code?
## Likely consequences
The adapter has fewer reasons to change, application evidence rules become directly testable, and report evolution remains local to one semantic owner. If another model integration is ever added, it also receives the same audited dossier, but that future variation is not required to justify the boundary.
## Exceptions
A transport adapter may deliberately translate a rich input as an anti-corruption layer, or project semantic context into model-specific tool calls and cached content. That translation is appropriate when the application has already decided which evidence is authoritative and the adapter is not silently making domain-selection decisions.
## Positive example
The application builds `ReportConversationContext` from the pinned report, bounded retrieval results, a rolling summary, and recent exchanges. Even when Ollama is the only model integration, its adapter merely serializes that context into the Ollama request format.
## Counterexample
An Ollama adapter receives `ConsultationRun`, chooses report sections and concern findings, builds claim allowlists, truncates evidence and chat history, and constructs the HTTP request in one method.
## Related policies
See `contain-dependencies`, `assign-clear-ownership`, and `model-stable-concepts`.
