---
id: fail-fast-on-bad-configuration
title: Fail loudly at startup, degrade deliberately at runtime
scope: general
strength: guidance
tags: [configuration, fail-fast, resilience, errors]
source:
  author: ArchCompass
  inspiration: ["Jim Shore, Fail Fast (IEEE Software)", "George Candea & Armando Fox, Crash-Only Software"]
description: >-
  Misconfiguration found at first use is an outage; found at startup it is a failed
  deploy. Validate configuration, connectivity, and invariants before accepting work,
  refuse loudly when they fail, and prefer designed degradation to limping on guesses.
---
## Intent
Move the discovery of a bad configuration from the first request that happens to need it
to the moment the component starts, when someone is still watching.
## Guidance
At startup, read the whole configuration and check it: required values present, values
parsed into their real types and ranges, endpoints resolvable and reachable, credentials
able to perform the operations they will be used for, mutually dependent settings
consistent, paths writable. Report every problem found in one message that names each
setting and where its value came from, then exit non-zero — not a warning, not a silent
default. Reserve defaults for values that represent a genuine choice, and avoid them
where the default is really a guess about what the operator meant, since a wrong guess is
indistinguishable from a correct one at runtime. Once running, when a dependency or a
value becomes unusable, take a designed degraded path — refuse the affected operation,
serve an answer marked stale, stop accepting new work — rather than substituting a value
and continuing. Make the effective configuration readable from a running instance, so
what was validated is also what can be inspected later.
## Signals
A missing environment variable surfaces as a null dereference inside a request handler
hours after deploy. Configuration is read lazily at each point of use, so different
settings are validated at different times and some only on rare paths. Invalid values
produce warnings that scroll past during startup. Durations, sizes, and counts are carried
as strings until the instant they are used. A component reports healthy without ever
having contacted the dependency it exists to talk to. A deployment goes green and the
failure arrives later as customer-visible errors.
## Diagnostic questions
If a required setting is absent or malformed, at what point does the system notice, and
who is watching then? Does this component accept traffic before it has demonstrated it can
do its work? Which settings currently fall back to a default, and would an operator be
able to tell that the fallback happened?
## Likely consequences
Validated at startup, a misconfiguration is a failed deploy: caught by the pipeline,
attributable to a specific change, and reverted automatically. Discovered at first use,
the same mistake is an incident, often a partial one where most requests succeed and one
path does not, which is the hardest kind to attribute. Loud refusal also removes an
ambiguity from every later investigation, because a running component is by definition one
whose configuration was accepted.
## Exceptions
Optional capabilities may legitimately be unconfigured, but their absence belongs in an
explicit disabled state reported at startup rather than in an unnoticed fallback. A
component whose job is to work while its dependencies are down — a recovery tool, or a
service designed to keep serving through an outage — should still validate the shape of
its configuration strictly, while treating connectivity as a runtime concern with a
designed degraded mode instead of a startup gate.
## Positive example
A worker validates everything before opening its listener: it parses each duration and
size, connects once to its store and its message broker, confirms the credential can
perform the writes it will need, and prints one report of the settings in effect. A typo
in a timeout stops the rollout at the first instance, before any traffic has been routed
to it.
## Counterexample
An export service reads its destination path the first time an export runs, on the first
day of the month. The path was misspelled three weeks earlier during an unrelated change;
the deploy was green, monitoring was green, and the failure finally appears as a missing
report with no visible connection to the change that caused it.
## Related policies
See `eliminate-errors-by-design`, `explicit-source-of-truth`,
`validate-at-trust-boundaries`, and `design-for-partial-failure`.
