---
id: repo-ledger-single-writer
title: The stock ledger is written only by the reconciliation path
scope: repository
applies_to: eval-warehouse-sync
strength: preferred
tags: [ownership, state, ledger, reconciliation]
source:
  author: Warehouse Sync maintainers
  inspiration: [evaluation fixture]
description: >-
  Stock quantities in the ledger are written by reconciliation and by nothing else.
  Reporting, the HTTP transport and the digest read through the ledger's interface. Finance
  reports the ledger's numbers, so a second writer is an unreconcilable discrepancy.
---
## Intent
Keep one code path answerable for every number finance publishes.
## Guidance
Reconciliation owns the write. Other subsystems read through the ledger's interface or
consume a snapshot it publishes; none of them opens the table. A correction is a
reconciliation input, not a direct update — including a manual one, which enters through
the same path with an operator recorded on it.
## Signals
A module other than reconciliation holds an INSERT or UPDATE against the ledger tables. A
support runbook contains SQL. Two subsystems disagree about a quantity and neither can say
which write happened last.
## Diagnostic questions
Which code paths can change this quantity? If two of them ran in the same minute, which
number does finance see? How would a wrong quantity be traced back to the write that caused it?
## Likely consequences
Every number has one path to explain it, and a discrepancy is a bug in one place. With
several writers, discrepancies become permanent because no reconstruction is possible.
## Exceptions
A schema migration may write the tables directly while the service is stopped.
## Positive example
The nightly digest reads quantities through the ledger's query interface and never opens
the table, so a change to reconciliation's rounding is visible in the digest the same night
without the digest being edited.
## Counterexample
The HTTP transport writes a corrected quantity straight into the ledger when a partner
sends a late adjustment, and reconciliation overwrites it the following night.
## Related policies
give-state-one-writer, assign-clear-ownership, explicit-source-of-truth
