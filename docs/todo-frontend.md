> **Superseded.** A completed design brief, written in the imperative and kept for its
> reasoning rather than its instructions. The workbench it describes has shipped; read
> [experience.md](experience.md) and [frontend-regions.md](frontend-regions.md) for what
> is actually on screen.

Refactor the ArchCompass frontend into a premium, modern, product-led experience for software engineers and architecture teams, with the goal of making the product feel trustworthy, technically serious, easy to understand, and pleasant to use during repository architecture reviews.

Do not begin from the existing UI or supplied mockup as a visual template. Begin from the product's user journeys and information hierarchy, then design the interface that best supports them.

Design it with the polish of leading developer-tool and modern SaaS brands: clean typography, generous whitespace, restrained use of gradients, subtle glassmorphism only where appropriate, high-quality spacing, strong hierarchy, refined surfaces, and smooth but non-distracting motion. Use elegant animations including scroll reveals, staggered entrances, hover transitions, ambient motion, loading transitions, state changes, and small interactive microinteractions.

The product is ArchCompass: a repository architecture reviewer that deterministically analyzes a codebase, detects architecture candidates, retrieves relevant architectural policies, asks clarification questions when needed, and produces architecture findings and review revisions.

The frontend should communicate these core ideas clearly:

- ArchCompass is not an autonomous coding agent.
- The application decides what to inspect.
- The model decides what the evidence means.
- The model does not invent repository identity or policy identity.
- Repository analysis is deterministic.
- Policy retrieval is auditable.
- Architecture reviews are revisioned.
- Clarification questions can update the case and trigger rejudgement.
- Standing decisions remain human decisions.
- The product should feel like a serious engineering review workbench rather than an AI chatbot.

PRIMARY USERS

Target:

- software engineers
- staff/principal engineers
- architects
- tech leads
- platform teams
- engineering teams reviewing architecture quality

The UI should feel credible to technical users. Avoid generic AI-product visual language, excessive neon gradients, oversized marketing slogans, chat-first layouts, and gimmicky “AI magic” interactions.

VISUAL DIRECTION

Aim for:

- premium developer tooling
- calm, technical, structured
- editorial clarity
- slightly opinionated visual identity
- high information density where useful, but never cramped
- strong use of cards, rails, tabs, badges, timelines, metadata, code-like details, and architectural visualizations
- refined responsive behavior
- clear distinction between domain state, workflow state, findings, evidence, policies, and user actions

Use:

- neutral or warm-neutral background
- subtle accent color
- restrained gradient accents
- soft borders
- layered surfaces
- subtle shadows
- readable typography
- monospace selectively for IDs, paths, commits, fingerprints, model identities, and technical metadata
- display font only for major headings if appropriate

Avoid:

- generic dashboard template look
- giant rounded cards everywhere
- excessive gradients
- excessive glassmorphism
- glowing buttons
- noisy animations
- emoji-heavy UI
- overuse of pills
- overly playful copy
- crypto/web3 aesthetics
- AI chatbot tropes

INFORMATION ARCHITECTURE

The application should have a clear persistent shell with:

- primary navigation
- current workspace/repository context
- selected reasoning model
- selected embedding model
- review status
- quick access to settings
- responsive mobile navigation

Suggested primary sections:

1. Home / Start
2. Repositories
3. Reviews
4. Architecture Cases
5. Policies
6. Settings

The frontend should make the product mental model visually understandable:

Repository
→ Repository Atlas
→ Architecture Candidates
→ Relevant Policies
→ Architecture Findings
→ Clarification Questions
→ Revised Architecture Case
→ Review Revision

LANDING / START EXPERIENCE

Create a polished product entry page, but keep it integrated with the actual application rather than building a disconnected marketing site.

Include:

1. Sticky navbar
   - ArchCompass branding
   - Product
   - How it works
   - Architecture
   - Policies
   - Docs
   - GitHub if already appropriate
   - prominent “Review a repository” CTA

2. Hero
   - concise product positioning
   - clear explanation that ArchCompass reviews software architecture using deterministic repository analysis plus policy-grounded model judgement
   - primary CTA: Review a repository
   - secondary CTA: Explore example review
   - visual product preview, not abstract AI artwork

Suggested copy direction:

Headline:
“Architecture review grounded in your code, policies, and decisions.”

Supporting text:
“ArchCompass deterministically maps your repository, detects architecture candidates, retrieves the policies that matter, and uses structured model judgement to produce auditable architecture findings.”

3. Product workflow section
   Visually explain:
   Repository
   → Atlas
   → Candidate
   → Policies
   → Finding
   → Review

4. Trust / design principles section
   Show principles such as:
   - deterministic analysis
   - auditable retrieval
   - structured model judgement
   - revision history
   - human clarification
   - human standing decisions

5. Product showcase
   Use realistic UI previews for:
   - repository atlas
   - findings
   - policy retrieval provenance
   - clarification questions
   - review revisions

6. Feature sections
   Examples:
   - Deterministic repository analysis
   - Policy-grounded architecture judgement
   - Clarification loops
   - Review delta and lineage
   - Standing decisions
   - Local or hosted model support

7. Architecture section
   Explain:
   LangGraph = workflow
   LangChain = model/RAG infrastructure
   ArchCompass domain = product concepts
   Keep this technically credible and visually concise.

8. FAQ
   Examples:
   - Is ArchCompass an autonomous coding agent?
   - Does it send my whole repository to an LLM?
   - How are policies selected?
   - Can I use Ollama?
   - What happens after I answer a clarification question?
   - Are findings persisted?
   - Can I add my own architecture policies?

9. Final CTA
   “Review your repository with context, not guesswork.”

10. Footer

- Docs
- GitHub
- Architecture
- License
- Privacy/security if relevant

PRODUCT UI REFACTOR

Do not only redesign the landing page. Refactor the actual app views as a coherent system.

START PAGE

Make the start page feel like a guided technical workflow.

It should clearly support:

- choosing or adding a repository
- choosing an architecture case
- selecting reasoning model
- selecting embedding model
- starting a review

Do not make this feel like a long settings form.
Use progressive disclosure and clear visual hierarchy.

REPOSITORIES PAGE

Each repository should show useful context:

- repository name
- branch
- source/location
- last indexed time
- atlas freshness
- latest review
- review status
- relevant metadata

Actions should be obvious:

- Review
- Open atlas
- Refresh/index
- Manage

REVIEW PAGE

This is the most important screen.

Treat it as an architecture review workbench.

Suggested layout:

Desktop:

- left: revision/navigation rail
- center: primary finding/review content
- right: contextual details such as evidence, policies, provenance, case context

Mobile:

- stacked views with drawers/tabs

The screen should clearly separate:

- review summary
- findings
- questions
- evidence
- relevant policies
- retrieval provenance
- review delta
- architecture case
- standing decision controls
- revision history

Do not present findings as generic chat messages.

FINDINGS

Each finding should feel like a structured architecture assessment.

Show:

- verdict
- title/summary
- reasoning
- involved code locations
- evidence
- relevant policies
- uncertainty/hinge if present
- recommendation where applicable
- model/prompt/retrieval provenance behind an expandable technical detail section

Use visual distinction between:

- material finding
- cleared candidate
- held / needs clarification

Clarification state should be obvious without feeling like an error.

QUESTIONS

Questions should feel like part of the review workflow, not a chat interface.

Each question should show:

- what ArchCompass needs to know
- why the answer matters
- related candidate/finding
- answer input
- skip option
- clear submit behavior

Support repeated clarification rounds elegantly.

POLICIES PAGE

Refactor the policy corpus into a polished technical knowledge interface.

Requirements:

- strong search
- filtering by strength and scope
- readable Markdown rendering
- clear source/scope/strength metadata
- expandable policy details
- authoring experience for workspace policies
- markdown preview or good markdown authoring experience
- delete controls only where appropriate
- optional retrieval-related metadata where useful

The policy body must render Markdown correctly.

ARCHITECTURE CASES PAGE

Cases should feel like living architectural context, not form records.

Show:

- goal
- constraints
- decisions
- clarification answers
- revision number
- related reviews
- timestamps

Make case evolution understandable.

SETTINGS / MODELS

Make reasoning model and embedding model configuration visually distinct.

Users must understand:

- reasoning model = architecture judgement
- embedding model = policy retrieval

Show:

- provider
- model
- status
- availability
- selected state
- pinned state if environment-configured
- clear error states

Do not make users infer embedding dimensions unless technically necessary.

ATLAS EXPERIENCE

The repository atlas should feel like a technical exploration tool.

Prioritize:

- readable structure
- package/module navigation
- relationships
- metrics
- architectural signals
- evidence locations

Do not try to turn it into a flashy graph visualization unless the data genuinely benefits from it.

If visual graph views are used, they should supplement—not replace—structured navigation.

MOTION

Use motion sparingly and intentionally.

Good uses:

- page transitions
- drawer opening
- finding expansion
- revision changes
- progress/state transitions
- hover affordances
- loading skeletons
- successful saves
- newly added review state

Avoid continuous distracting motion inside the workbench.

RESPONSIVE DESIGN

Make the application genuinely usable on:

- large desktop
- laptop
- tablet
- mobile

Do not merely shrink desktop layouts.

For dense screens like Review:

- use tabs
- drawers
- bottom sheets
- collapsible context panels
- sticky action bars where appropriate

ACCESSIBILITY

Ensure:

- keyboard navigation
- visible focus states
- semantic headings
- ARIA where needed
- sufficient contrast
- screen-reader-friendly status messaging
- reduced-motion support
- buttons/inputs have proper labels
- no information is conveyed only through color

COMPONENT SYSTEM

Build a reusable design system rather than styling each page independently.

Create/refine reusable primitives for:

- page headers
- cards/panels
- badges/status indicators
- buttons
- inputs
- textareas
- tabs
- drawers
- modals
- empty states
- loading states
- error states
- metadata rows
- code/path display
- markdown rendering
- timeline/revision rail
- finding cards
- policy cards
- evidence blocks

Avoid giant generic components with dozens of boolean props.

Prefer small composable components with clear semantic roles.

TECHNICAL CONSTRAINTS

Keep the existing frontend stack unless there is a strong reason to change it.

Current stack includes:

- React
- TypeScript
- Vite
- Tailwind
- TanStack Query
- React Router
- react-markdown
- remark-gfm

Do not replace the stack merely for styling.

Preserve:

- existing API behavior
- existing routes unless there is a strong UX reason to adjust them
- backend contracts
- tests
- OpenAPI integration
- accessibility
- loading/error state handling

Do not redesign the backend as part of this task.

COPY

Rewrite weak/generic frontend copy where needed.

Tone:

- concise
- technical
- confident
- clear
- non-hypey

Avoid phrases such as:

- “AI-powered magic”
- “revolutionize your architecture”
- “supercharge”
- “10x”
- “next-generation”
- “intelligent assistant”

Prefer specific language about:

- repository analysis
- architecture candidates
- policies
- findings
- evidence
- clarification
- review revisions

IMPLEMENTATION APPROACH

Before changing code:

1. Audit every current frontend page and component.
2. Identify inconsistent patterns, duplicated UI, weak information hierarchy, accessibility issues, and poor responsive behavior.
3. Produce a short redesign plan.
4. Define the design tokens and component system.
5. Refactor reusable UI primitives first.
6. Refactor product shell/navigation.
7. Refactor the Review page first because it is the core product surface.
8. Refactor Policies, Cases, Repositories, Start, Reviews, and Settings.
9. Add/refine the integrated landing/start experience.
10. Add motion and polish only after structure is correct.
11. Run frontend tests, typecheck, and build.
12. Do not leave dead components or old styling paths behind.

Do not preserve a weak existing UI simply because it exists.
Do preserve product behavior and technical contracts.

DELIVERABLES

At completion, provide:

1. summary of UX problems found
2. design direction chosen
3. major component-system changes
4. pages refactored
5. major before/after structural changes
6. responsive behavior notes
7. accessibility improvements
8. test/typecheck/build results
9. any backend limitations that prevented a better frontend experience
10. screenshots or a concise walkthrough of the main screens if possible

The success criterion is:

ArchCompass should feel like a serious, polished architecture engineering product that a staff engineer or architect would trust—not like a generic admin dashboard, AI chat wrapper, or template-driven SaaS frontend.
