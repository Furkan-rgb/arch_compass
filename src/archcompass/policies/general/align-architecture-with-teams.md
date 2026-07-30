---
id: align-architecture-with-teams
title: Draw system boundaries where team boundaries can hold them
scope: general
strength: guidance
tags: [conways-law, teams, boundaries, ownership]
source:
  author: ArchCompass
  inspiration: ["Melvin Conway, How Do Committees Invent?", "Matthew Skelton & Manuel Pais, Team Topologies"]
description: >-
  A system's structure converges on the communication structure of the
  organization that builds it. Put boundaries where a single team can own a
  component end to end, and treat a mismatch between design and ownership as a
  design defect rather than a staffing detail.
---
## Intent
Choose module and service boundaries that one team can own end to end, so the structure
survives contact with how the work is actually divided.
## Guidance
A system's interfaces converge on the communication paths of the organization building it,
so treat the ownership map as part of the design. Prefer seams where one team can change a
component, test it, and release it without scheduling anyone else, and be suspicious of any
boundary that requires two teams to agree on every change — such a boundary will either
dissolve or become a queue. Where a component has no owner, assign one before it grows;
unowned code collects the changes nobody wants to defend. When the design a team wants and
the ownership they hold disagree, treat that as a design problem with two admissible fixes,
move the boundary or move the ownership, and choose one deliberately instead of letting the
mismatch decide.
## Signals
A module is edited by four teams and reviewed by whoever is available. A change everyone
calls small requires a coordinated release across two services owned by different groups.
Interfaces inside a team are informal and shifting while interfaces between teams are rigid
regardless of how much coupling actually exists. A component's history shows alternating
styles, each matching whichever team last needed something from it.
## Diagnostic questions
Which team can change this component alone and release it alone? Does any boundary here
require standing agreement between groups that do not otherwise talk? If two teams must
both touch a feature to ship it, is the split between them the split the domain suggests?
## Likely consequences
Boundaries that match ownership stay sharp, because the team on each side has both the
authority and the incentive to defend them. Boundaries that cut across teams erode:
shortcuts appear wherever coordination is expensive, and the design drifts toward the shape
of the organization anyway, but without anyone having chosen it.
## Exceptions
A small enough group is a single team, and imposing boundaries on it to model a future
organization adds ceremony for a structure that does not exist. Shared foundational
components such as a common domain model or a platform library legitimately span teams;
they need an explicit steward and a contribution contract, not a boundary redrawn around
one group.
## Positive example
One team owns billing: the service, its data, and the events it publishes. When a pricing
rule changes they alter the calculation, migrate their own tables, and release, and other
teams learn about it only through an event contract that did not change.
## Counterexample
A checkout flow is split into a front-end service and a back-end service by technology
rather than by domain, with a different team on each side. Every user-visible change needs
work in both, so the teams negotiate release order weekly, and the interface between them
accumulates fields that exist only so one team can avoid waiting for the other.
## Related policies
See `assign-clear-ownership`, `give-state-one-writer`, and `organize-by-responsibility`.
