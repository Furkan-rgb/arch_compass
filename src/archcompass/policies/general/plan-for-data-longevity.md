---
id: plan-for-data-longevity
title: Design data contracts to outlive the code around them
scope: general
strength: guidance
tags: [data-evolution, compatibility, schemas, contracts]
source:
  author: ArchCompass
  inspiration: ["Martin Kleppmann, Designing Data-Intensive Applications"]
description: >-
  Persisted records and published schemas outlive every implementation that
  touches them, and old data will always coexist with new code. Design the
  evolution path — versioning, tolerant readers, expand-then-contract migration
  — before the first record is written.
---
## Intent
Protect the data a system has already written, and the consumers already reading it, from every future change to the code that produced it.
## Guidance
Treat a stored format or a published message schema as a contract with an indefinite lifetime and an unknown set of readers. Add fields as optional with defined defaults, never repurpose an existing field's meaning, and never reuse a retired name or identifier for something new. Write tolerant readers that carry unknown fields through rather than failing on them, so a producer can move ahead of its consumers and a rollback does not become an outage. Make every structural change a two-phase sequence: add the new shape, write both shapes, backfill the old records, move readers one at a time, and drop the old shape only once evidence — not the calendar — says nothing reads it. Carry a version or a discriminator inside the data so an unfamiliar record can be identified rather than guessed at, and keep the schema described somewhere other than the class that happens to load it today.
## Signals
A release ships with a script that rewrites every historical row so the new code can read it. A field named for a workflow that no longer exists holds something else, explained by a comment. Deserialization raises on records written by the previous version. Producer and consumer must be deployed in a fixed order, so rolling back one breaks the other. The only specification of what is stored is the current data class, and reading last year's records requires checking out last year's code.
## Diagnostic questions
What happens when the previous release reads a record written by this one? Which readers exist outside this repository, and how would you find out? If this deploy were reverted an hour after release, which records would be unreadable?
## Likely consequences
Data designed to evolve lets the code around it be rewritten, replaced and rolled back with no coordination beyond the schema itself, and lets consumers upgrade on their own schedule. Data designed only for today's code turns every release into a migration and every rollback into a data-loss risk, and eventually freezes the design, because the cost of touching the format exceeds the value of any change that would need to.
## Exceptions
Derived data that can be rebuilt from a source of truth — caches, search indexes, materialized views — can be versioned by discarding and regenerating it, and does not need compatible evolution. A format with exactly one reader and one writer deployed as a single unit can change more freely, but write that assumption down, because it usually stops being true without anyone noticing.
## Positive example
An event log stores each record with an explicit schema version, and every consumer ignores fields it does not recognize. Splitting one name field into two ships as: add both new fields, write all three, backfill in the background, migrate each consumer at its own pace, then stop writing the old field a full release after the last reader stopped asking for it.
## Counterexample
A stored document is simply whatever the serializer emitted for the current class. Renaming one attribute makes every record written before the release unreadable, the remedy is a one-off script that must run with the service stopped, and there is no rollback plan because yesterday's code cannot read today's rows.
## Related policies
See `migrate-incrementally`, `model-stable-concepts`, and `explicit-source-of-truth`.
