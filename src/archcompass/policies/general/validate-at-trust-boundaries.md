---
id: validate-at-trust-boundaries
title: Validate once at the boundary and pass proven values inward
scope: general
strength: guidance
tags: [validation, boundaries, types, security]
source:
  author: ArchCompass
  inspiration: ["Alexis King, Parse, Don't Validate"]
description: >-
  Input from outside a trust boundary is checked exactly once, at entry, and
  converted into a representation that carries its proof. Interior code neither
  re-validates defensively nor handles rawness it should never see.
---
## Intent
Establish one place where untrusted input becomes trustworthy, so that everything inside can be written for valid data only.
## Guidance
Identify the boundaries where data enters a trust domain — network requests, message consumers, files, command-line arguments, responses from other systems, anything a user or another program controls — and validate there, completely, once. Validation should yield a value rather than a verdict: parse the input into a representation that can hold only what was accepted, and pass that inward instead of the raw payload. Reject the whole input early rather than sanitizing it into something the sender did not send, and where a defaulting rule is needed, apply it explicitly at the boundary instead of implicitly at each use. Interior code then neither re-checks nor tolerates rawness; a function deep in the system testing whether a string is a well-formed identifier means either the boundary is not doing its job or the value never crossed one. Treat responses from other systems the same way, because a dependency's output is untrusted input arriving through a different door.
## Signals
The same null, length or format check appears at three different call depths. A function accepts a dictionary parsed from a request body and reaches into it by key. Error messages about malformed input are produced by code with no idea which request it came from. Interior branches handle values the boundary is supposed to have rejected. Validation rules for a single entry point are spread across a request handler, a service and a persistence layer, and they disagree about the maximum length.
## Diagnostic questions
Where exactly does this value stop being attacker-controlled, and what does it become at that point? If this interior check were deleted, could anything invalid actually reach it? Does the type of this parameter tell a reader what has already been proven about it?
## Likely consequences
A single boundary check gives one place to audit for security, one place to change a rule, and interior code that is shorter because it only handles cases that can occur. Scattered re-validation means nobody can say whether an input is checked at all: rules diverge, some paths are missed entirely, and the paths that are covered pay the cost repeatedly while providing no guarantee anyone can point to.
## Exceptions
A check at a genuinely separate trust boundary is not duplication — a persistence layer escaping values, or a service that does not trust its sibling, is validating for its own domain and should keep doing so. Assertions of internal invariants remain legitimate as long as they are stated as invariants that abort, not as recovery paths for input the system expects to receive.
## Positive example
An intake endpoint converts a request body into a typed command: identifiers become identifier values, the timestamp becomes an instant in a fixed zone, and an out-of-range page size is rejected with a message naming the offending field. Every function beneath receives that command, so none of them contains a format check, and the entire input contract is readable in one file.
## Counterexample
A file-processing service passes a raw upload path down five layers. The layer that reads the file checks the extension, the layer that names the output checks for traversal sequences, and the layer that archives it checks neither — so the one code path that skips the first two becomes the vulnerability, found by an auditor rather than a test.
## Related policies
See `make-illegal-states-unrepresentable`, `eliminate-errors-by-design`, and `aggregate-error-handling`.
