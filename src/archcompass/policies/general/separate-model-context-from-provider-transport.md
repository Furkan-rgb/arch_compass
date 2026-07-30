---
id: separate-model-context-from-provider-transport
title: Keep semantic context decisions out of model transport
scope: general
strength: preferred
tags: [model-context, evidence, responsibility, transport, boundaries]
source:
  author: ArchCompass
  inspiration: [hexagonal architecture, information hiding]
description: >-
  The application decides what a model may know; a transport adapter only
  encodes an already-assembled context for a provider API. Selecting, merging,
  excluding, ranking, and truncating evidence are domain decisions and must not
  migrate into the code that speaks the wire protocol.
---
## Intent
Contain the application decision about what a model may know, so that evidence rules,
document interpretation, and conversation policy do not leak into the code that talks to a
provider API.
## Guidance
Have an application-level owner assemble a validated, bounded context object and hand it to
a model port. The adapter behind that port does transport work only: encode the context in
the provider's request format, apply transport options such as timeouts and sampling
parameters, request the output schema, parse or repair the response, and translate provider
failures into the port's error vocabulary. Everything that decides content — which sources
are authoritative, which findings are eligible, how prior exchanges are summarized, what
gets dropped when a budget is exceeded — happens before that boundary and is expressible
with no provider in the picture. The working test is whether the adapter could be handed a
context object it had no part in building and still do its whole job.
## Signals
An adapter method receives a broad aggregate — a case, a session, a repository handle — and
walks several levels of domain structure to find what to send. Selection, ranking, or
truncation of evidence appears in the same function that builds the outbound request.
Changing a document schema or an eligibility rule requires editing transport code. The only
way to test which evidence would be included is to run the request path against a stub
server. Domain vocabulary and protocol vocabulary appear in the same parameter list.
## Diagnostic questions
Does this method decide what information is authoritative and relevant, or does it only
encode an already-decided context? Would changing document structure, evidence eligibility,
claim validation, or truncation rules require touching the code that speaks to the
provider? Could the assembled context be inspected, logged, and asserted on with no
adapter present?
## Likely consequences
The adapter acquires few reasons to change, and they are all transport reasons: protocol,
encoding, error mapping. Evidence and conversation rules become directly testable as
ordinary application logic, and a reviewer can read one object to see exactly what the
model was told. When those rules live inside transport code, every domain change becomes a
change to integration code, no artifact states what the model actually saw, and a second
provider integration cannot be added without re-deciding the domain questions.
## Exceptions
An adapter may deliberately translate a rich input as an anti-corruption layer, or project
the context into provider-specific shapes such as tool definitions or cached message
prefixes. That is legitimate when the application has already settled which evidence is
authoritative and the adapter is only re-expressing it. Fitting an already-selected context
to a provider's token limit may also live at the boundary, provided the rule for what is
dropped first was decided upstream and is stated somewhere other than the adapter.
## Positive example
A document-review assistant builds a conversation-context object from the pinned document
version, a bounded set of retrieved passages, a rolling summary, and the last few
exchanges. The LLM provider adapter receives that object and serializes it; when retrieval
changes from keyword matching to embeddings, the adapter is untouched, and the same context
can be sent to a second provider without re-deciding anything.
## Counterexample
An LLM provider adapter takes the whole review session, picks which document sections and
findings to include, builds an allowlist of quotable claims, truncates the history to fit a
context window, and assembles the request — all in one method. A change to which findings
count as evidence now lands in networking code, and reviewing that change means reading a
request builder.
## Related policies
See `contain-dependencies`, `assign-clear-ownership`, and `model-stable-concepts`. The same
split — decide in a deterministic core, act at the boundary — is stated generally in
`keep-effects-at-the-edges`.
