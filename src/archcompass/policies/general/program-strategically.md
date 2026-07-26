---
id: program-strategically
title: Invest in design continuously instead of patching tactically
scope: general
strength: guidance
tags: [strategic-programming, complexity, incremental-change]
source:
  author: ArchCompass
  inspiration: ["John Ousterhout, A Philosophy of Software Design (2nd ed.)"]
---
## Intent
Prevent complexity from accumulating through a sequence of individually reasonable shortcuts.
## Guidance
Treat each change as an opportunity to leave the affected design slightly better; when a change fights the current structure, adjust the structure or record the debt explicitly instead of adding another workaround.
## Signals
Fixes cluster in one module as flag additions, copy-adjusted branches, and callers routing around a known-awkward interface rather than changing it.
## Diagnostic questions
If every future change were made in this same style, what would this module look like in a year, and is the shortcut worth that trajectory?
## Likely consequences
Development speed stays level over time, and cleanup happens in small continuous doses rather than rare risky rewrites.
## Exceptions
A time-boxed incident fix or throwaway prototype may be deliberately tactical when the follow-up correction is visible and scheduled.
## Positive example
Adding a fourth report format prompts extracting format selection into the renderer that owns it, so the fourth case becomes one registration.
## Counterexample
Each new provider adds another conditional to the same dispatch function because one more branch is always cheaper than fixing the dispatch.
## Related policies
See `design-it-twice`, `optimize-locality-of-change`, and `pull-complexity-downward`.
