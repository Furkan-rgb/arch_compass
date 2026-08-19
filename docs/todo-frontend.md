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

REFERENCE MOCKUP

An HTML mockup is attached as optional UX inspiration.

Do NOT reproduce it literally.
Do NOT treat its layout, spacing, colors, component shapes, sidebar structure, panel arrangement, or visual styling as requirements.

The mockup exists only to communicate several UX ideas that may be useful:

- prioritize items that require human attention over cleared findings
- make the user's next action obvious
- treat the review as the primary workbench
- make a selected finding easy to understand in depth
- keep evidence, policies, architecture-case context, and provenance available as supporting context
- make clarification questions feel like part of the review workflow rather than a chatbot
- keep standing decisions visibly separate from the finding itself
- de-emphasize technical metadata until the user asks for it
- make revision/history information accessible without allowing it to dominate the current review
- preserve a clear distinction between repository evidence, policy guidance, model judgement, and human decisions

Use these as product/UX considerations, not as a prescribed information architecture.

You are encouraged to redesign the experience from first principles if you can produce a clearer, more elegant, more intuitive solution.

Before implementing, reason about the user's primary jobs-to-be-done and propose the information hierarchy you think best supports them.

Prefer a better solution over fidelity to the supplied mockup.

<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>ArchCompass — UX Refined Review Workbench</title>
<style>
  :root{
    --bg:#f6f7f4;
    --surface:#ffffff;
    --surface-2:#fafbf9;
    --surface-3:#f1f3ef;
    --ink:#171a17;
    --muted:#667067;
    --muted-2:#8c958d;
    --line:#dde3dd;
    --line-strong:#cfd7cf;
    --accent:#4056d6;
    --accent-soft:#eef1ff;
    --accent-2:#283887;
    --green:#177a55;
    --green-soft:#eaf7f1;
    --amber:#9f6716;
    --amber-soft:#fff7e6;
    --red:#b44742;
    --red-soft:#fff1ef;
    --nav:#111511;
    --nav-2:#1a211b;
    --shadow:0 10px 28px rgba(23,26,23,.055);
    --shadow-sm:0 4px 14px rgba(23,26,23,.04);
    --radius:16px;
  }

\*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
margin:0;
background:
radial-gradient(circle at 80% -5%, rgba(64,86,214,.07), transparent 26rem),
var(--bg);
color:var(--ink);
font-family:Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
-webkit-font-smoothing:antialiased;
}
button,input,textarea{font:inherit}
button{cursor:pointer}
a{color:inherit}

.app{
display:grid;
grid-template-columns:232px minmax(0,1fr);
min-height:100vh;
}

/_ Sidebar _/
.sidebar{
position:sticky; top:0; height:100vh;
display:flex; flex-direction:column;
background:linear-gradient(180deg,var(--nav),#0d110e);
color:#dce5dc; padding:20px 14px;
border-right:1px solid rgba(255,255,255,.05);
}
.brand{display:flex;align-items:center;gap:11px;padding:3px 8px 22px}
.brand-mark{
width:32px;height:32px;border-radius:9px;display:grid;place-items:center;
background:linear-gradient(145deg,#f2f4ff,#9fb0ff);color:#2743b5;font-weight:900;
}
.brand-name{font-weight:780;font-size:14px;letter-spacing:-.02em}
.brand-sub{font-size:10px;color:#7f8a80;margin-top:2px}
.nav-label{
padding:14px 10px 7px;font-size:9px;letter-spacing:.14em;
text-transform:uppercase;color:#647064;font-weight:800;
}
.nav{display:grid;gap:4px}
.nav a{
text-decoration:none; display:flex;align-items:center;justify-content:space-between;
padding:9px 10px;border-radius:9px;color:#aab5aa;font-size:12px;font-weight:650;
}
.nav a:hover,.nav a.active{background:#202821;color:#fff}
.count{font-size:9px;background:#2b352c;color:#a8b3a8;padding:3px 6px;border-radius:999px}
.workspace{
margin-top:auto;border:1px solid rgba(255,255,255,.07);
background:rgba(255,255,255,.03);border-radius:13px;padding:12px;
}
.workspace .k{font-size:9px;color:#768176;text-transform:uppercase;letter-spacing:.1em}
.workspace strong{display:block;margin:5px 0 3px;font-size:11px}
.workspace small{font-size:10px;color:#7f8a80;line-height:1.45}

/_ Main _/
.main{min-width:0}
.topbar{
position:sticky;top:0;z-index:20;height:64px;padding:0 26px;
display:flex;align-items:center;justify-content:space-between;
background:rgba(246,247,244,.9);backdrop-filter:blur(14px);
border-bottom:1px solid rgba(207,215,207,.78);
}
.crumbs{font-size:11px;color:var(--muted)}
.crumbs strong{color:var(--ink)}
.top-actions{display:flex;gap:8px;align-items:center}
.chip{
display:flex;align-items:center;gap:7px;
background:#fff;border:1px solid var(--line);
border-radius:999px;padding:6px 9px;font-size:10px;color:var(--muted)
}
.dot{width:7px;height:7px;border-radius:50%;background:var(--green)}
.btn{
border-radius:9px;padding:8px 11px;border:1px solid transparent;
font-size:11px;font-weight:750;transition:.16s ease;
}
.btn.primary{background:var(--ink);color:#fff}
.btn.primary:hover{transform:translateY(-1px);box-shadow:0 6px 16px rgba(23,26,23,.12)}
.btn.secondary{background:#fff;border-color:var(--line);color:var(--ink)}
.btn.ghost{background:transparent;color:var(--muted)}
.btn.danger{background:var(--red-soft);color:var(--red);border-color:#f0d2cf}

.content{max-width:1540px;margin:auto;padding:26px}

/_ Review header _/
.review-head{
display:grid;grid-template-columns:minmax(0,1fr) auto;gap:20px;align-items:start;
margin-bottom:18px;
}
.eyebrow{
font-size:10px;text-transform:uppercase;letter-spacing:.13em;
font-weight:850;color:var(--accent)
}
h1{font-size:30px;line-height:1.1;letter-spacing:-.035em;margin:7px 0 7px}
.lead{font-size:12.5px;color:var(--muted);line-height:1.55;max-width:760px}
.meta{display:flex;gap:7px;flex-wrap:wrap;margin-top:11px}
.pill{
border:1px solid var(--line);background:rgba(255,255,255,.76);
border-radius:999px;padding:5px 8px;font-size:9.5px;color:var(--muted)
}

.next-action{
min-width:290px;border:1px solid #ead7aa;background:var(--amber-soft);
border-radius:14px;padding:13px 14px;box-shadow:var(--shadow-sm);
}
.next-action .k{font-size:9px;text-transform:uppercase;letter-spacing:.1em;font-weight:850;color:var(--amber)}
.next-action strong{display:block;font-size:12px;margin-top:6px}
.next-action p{margin:4px 0 10px;font-size:10.5px;color:#6f644f;line-height:1.45}

/_ Review health strip _/
.status-strip{
display:grid;grid-template-columns:1.3fr repeat(3,1fr);
gap:10px;margin-bottom:16px;
}
.status-card{
background:var(--surface);border:1px solid var(--line);
border-radius:13px;padding:12px 13px;box-shadow:var(--shadow-sm)
}
.status-card.focus{
background:linear-gradient(135deg,#fbfcff,#f5f7ff);
border-color:#dbe0f7;
}
.status-card .k{
font-size:9px;text-transform:uppercase;letter-spacing:.11em;
color:var(--muted-2);font-weight:850
}
.status-card .v{font-size:18px;font-weight:800;margin-top:5px;letter-spacing:-.025em}
.status-card .s{font-size:9.5px;color:var(--muted);margin-top:2px;line-height:1.4}

/_ Core workbench _/
.workbench{
display:grid;
grid-template-columns:270px minmax(0,1fr) 330px;
gap:14px;align-items:start;
}
.panel{
background:var(--surface);border:1px solid var(--line);
border-radius:var(--radius);box-shadow:var(--shadow)
}
.panel-head{
display:flex;align-items:center;justify-content:space-between;
gap:10px;padding:14px 15px;border-bottom:1px solid var(--line)
}
.panel-title{font-size:11.5px;font-weight:850}
.panel-sub{font-size:9.5px;color:var(--muted-2);margin-top:3px}

/_ Attention queue _/
.queue-tabs{display:flex;gap:5px;padding:10px 10px 0}
.queue-tab{
border:1px solid var(--line);background:#fff;color:var(--muted);
padding:5px 8px;border-radius:999px;font-size:9px;font-weight:750
}
.queue-tab.active{background:var(--ink);color:#fff;border-color:var(--ink)}
.queue{padding:8px}
.queue-item{
width:100%;text-align:left;border:0;background:transparent;
padding:11px;border-radius:12px;transition:.15s ease
}
.queue-item:hover{background:var(--surface-2)}
.queue-item.active{background:var(--accent-soft)}
.queue-item + .queue-item{margin-top:2px}
.queue-top{display:flex;gap:9px;align-items:flex-start}
.queue-icon{
width:26px;height:26px;border-radius:8px;display:grid;place-items:center;
flex:0 0 auto;font-size:10px;font-weight:900
}
.queue-icon.material{background:var(--red-soft);color:var(--red)}
.queue-icon.held{background:var(--amber-soft);color:var(--amber)}
.queue-icon.cleared{background:var(--green-soft);color:var(--green)}
.queue-title{font-size:10.5px;font-weight:800;line-height:1.35}
.queue-meta{font-size:9px;color:var(--muted-2);margin-top:4px}
.queue-footer{padding:11px 12px;border-top:1px solid var(--line);font-size:9px;color:var(--muted)}

/_ Main finding detail _/
.finding-head{
padding:18px 18px 15px;border-bottom:1px solid var(--line);
}
.finding-topline{display:flex;align-items:center;justify-content:space-between;gap:12px}
.verdict-badge{
display:inline-flex;align-items:center;gap:7px;
font-size:9px;text-transform:uppercase;letter-spacing:.1em;font-weight:850;
padding:5px 8px;border-radius:999px
}
.verdict-badge.material{background:var(--red-soft);color:var(--red)}
.verdict-badge.held{background:var(--amber-soft);color:var(--amber)}
.verdict-badge.cleared{background:var(--green-soft);color:var(--green)}
.finding-title{font-size:19px;line-height:1.25;letter-spacing:-.025em;margin:11px 0 7px}
.finding-summary{font-size:12px;line-height:1.6;color:#515a52;max-width:850px}
.finding-context{
display:flex;gap:7px;flex-wrap:wrap;margin-top:12px
}
.tag{
font-size:8.5px;color:var(--muted);border:1px solid var(--line);
background:#fff;border-radius:999px;padding:4px 6px
}

.finding-body{padding:16px 18px 18px}
.section{margin-bottom:18px}
.section:last-child{margin-bottom:0}
.section-label{
font-size:9px;text-transform:uppercase;letter-spacing:.1em;
color:var(--muted-2);font-weight:850;margin-bottom:8px
}
.prose{font-size:11.5px;line-height:1.65;color:#414941}
.recommendation{
border:1px solid #d9e4dc;background:#f7fbf8;border-radius:12px;padding:12px
}
.recommendation strong{font-size:11px}
.recommendation p{font-size:10.5px;line-height:1.55;color:#4e5b52;margin:5px 0 0}

.evidence-list{display:grid;gap:8px}
.evidence{
border:1px solid var(--line);background:var(--surface-2);
border-radius:11px;padding:10px 11px
}
.evidence-top{display:flex;justify-content:space-between;gap:10px}
.path{
font-family:"SFMono-Regular",Consolas,monospace;font-size:9.5px;color:#39443a
}
.line{font-size:8.5px;color:var(--muted-2)}
.evidence p{font-size:10px;color:#596159;line-height:1.45;margin:6px 0 0}

.decision-row{
display:flex;align-items:center;justify-content:space-between;
gap:12px;border-top:1px solid var(--line);padding-top:14px
}
.decision-copy strong{font-size:10.5px}
.decision-copy p{font-size:9.5px;color:var(--muted);margin:3px 0 0}
.decision-actions{display:flex;gap:6px;flex-wrap:wrap}

/_ Right context _/
.tabs{display:flex;gap:4px;padding:10px 10px 0}
.tab{
border:0;background:transparent;color:var(--muted);
padding:6px 8px;border-radius:8px;font-size:9px;font-weight:750
}
.tab.active{background:var(--surface-3);color:var(--ink)}
.tab-content{padding:12px 13px}
.context-row{
display:grid;grid-template-columns:78px 1fr;gap:8px;
padding:8px 0;border-bottom:1px solid #edf0ec;font-size:9.8px
}
.context-row:last-child{border-bottom:0}
.context-row .k{color:var(--muted-2)}
.context-row .v{color:#424b43;line-height:1.45}

.policy{
padding:10px;border-radius:10px;border:1px solid transparent
}
.policy:hover{background:var(--surface-2)}
.policy + .policy{margin-top:3px}
.policy-top{display:flex;justify-content:space-between;gap:8px}
.policy-name{font-size:10px;font-weight:800}
.policy-score{font-size:8.5px;color:var(--muted-2)}
.policy p{font-size:9px;line-height:1.45;color:var(--muted);margin:4px 0 0}
.source-badge{
display:inline-block;margin-top:6px;font-size:7.8px;padding:3px 5px;
border-radius:6px;background:var(--accent-soft);color:#5263b6;font-weight:800
}

.clarification{
border:1px solid #ead7aa;background:var(--amber-soft);
border-radius:12px;padding:11px
}
.clarification .k{
font-size:8.5px;text-transform:uppercase;letter-spacing:.1em;
color:var(--amber);font-weight:850
}
.clarification strong{display:block;font-size:10.5px;margin-top:6px;line-height:1.4}
.clarification p{font-size:9.3px;line-height:1.45;color:#6f644f;margin:4px 0 8px}
.answer{display:grid;gap:7px}
.answer textarea{
min-height:72px;resize:vertical;border:1px solid #e6d2a3;
border-radius:9px;background:#fff;padding:8px;font-size:9.8px;outline:none
}
.answer textarea:focus{border-color:#c79a45;box-shadow:0 0 0 3px rgba(199,154,69,.1)}
.answer-actions{display:flex;gap:6px;justify-content:flex-end}

.review-history{
padding:10px 12px;border-top:1px solid var(--line);background:#fafbf9;
border-radius:0 0 16px 16px
}
.history-link{
width:100%;border:0;background:transparent;text-align:left;
font-size:9px;color:var(--muted);display:flex;justify-content:space-between
}

/_ Principle strip _/
.principle{
margin-top:16px;background:#131813;color:#dde6dd;
border-radius:14px;padding:14px 16px;display:flex;
align-items:center;justify-content:space-between;gap:18px
}
.principle .k{font-size:8.5px;text-transform:uppercase;letter-spacing:.11em;color:#788579;font-weight:850}
.principle p{font-size:10.5px;line-height:1.5;margin:5px 0 0}
.mini-flow{display:flex;align-items:center;gap:6px;font-size:8px;color:#8c978d}
.mini-flow span{background:#202720;border:1px solid #2d372e;color:#cfd9cf;padding:6px 7px;border-radius:7px}

/_ Responsive _/
@media(max-width:1200px){
.workbench{grid-template-columns:250px minmax(0,1fr)}
.right{grid-column:1/-1;display:grid;grid-template-columns:1fr 1fr;gap:14px}
}
@media(max-width:900px){
.app{grid-template-columns:1fr}
.sidebar{display:none}
.content{padding:18px}
.topbar{padding:0 18px}
.review-head{grid-template-columns:1fr}
.next-action{min-width:0}
.status-strip{grid-template-columns:1fr 1fr}
.workbench{grid-template-columns:1fr}
.right{grid-template-columns:1fr}
.queue-panel{order:2}
}
@media(max-width:560px){
h1{font-size:26px}
.top-actions .chip{display:none}
.status-strip{grid-template-columns:1fr}
.decision-row{align-items:flex-start;flex-direction:column}
.principle{align-items:flex-start;flex-direction:column}
.mini-flow{flex-wrap:wrap}
}
@media(prefers-reduced-motion:reduce){
\*{transition:none!important;scroll-behavior:auto!important}
}
</style>

</head>
<body>
<div class="app">

  <aside class="sidebar">
    <div class="brand">
      <div class="brand-mark">A</div>
      <div>
        <div class="brand-name">ArchCompass</div>
        <div class="brand-sub">Architecture review workspace</div>
      </div>
    </div>

    <div class="nav-label">Review</div>
    <nav class="nav">
      <a href="#">Start review</a>
      <a class="active" href="#"><span>Current review</span><span class="count">3</span></a>
      <a href="#"><span>Review history</span><span class="count">12</span></a>
    </nav>

    <div class="nav-label">Workspace</div>
    <nav class="nav">
      <a href="#">Repositories</a>
      <a href="#">Architecture cases</a>
      <a href="#">Policies</a>
      <a href="#">Models</a>
    </nav>

    <div class="workspace">
      <div class="k">Current repository</div>
      <strong>payments-platform</strong>
      <small>main · 8f31c2a<br/>Atlas fresh · 4 min ago</small>
    </div>

  </aside>

  <main class="main">
    <header class="topbar">
      <div class="crumbs">Reviews / <strong>payments-platform</strong> / rev. 4</div>
      <div class="top-actions">
        <div class="chip"><span class="dot"></span> Gemini 2.5 Pro</div>
        <div class="chip">Embeddings · Gemini 2</div>
        <button class="btn secondary">Export</button>
        <button class="btn primary">New review</button>
      </div>
    </header>

    <div class="content">

      <section class="review-head">
        <div>
          <div class="eyebrow">Architecture review · revision 4</div>
          <h1>Payments platform</h1>
          <div class="lead">
            Review the few places that need architectural judgement. ArchCompass has already mapped the repository,
            detected candidates, and retrieved the relevant policies.
          </div>
          <div class="meta">
            <span class="pill">github.com/acme/payments-platform</span>
            <span class="pill">branch: main</span>
            <span class="pill">case rev. 4</span>
            <span class="pill">review completed with 1 unresolved clarification</span>
          </div>
        </div>

        <aside class="next-action">
          <div class="k">Your next action</div>
          <strong>Answer 1 clarification</strong>
          <p>One candidate cannot be judged confidently until ArchCompass knows whether the timeout is a shared business rule.</p>
          <button class="btn primary" onclick="document.getElementById('clarification').scrollIntoView({behavior:'smooth'})">Answer clarification</button>
        </aside>
      </section>

      <section class="status-strip">
        <div class="status-card focus">
          <div class="k">Needs attention</div>
          <div class="v">3 items</div>
          <div class="s">2 material findings · 1 clarification</div>
        </div>
        <div class="status-card">
          <div class="k">Candidates reviewed</div>
          <div class="v">5</div>
          <div class="s">2 cleared · 3 require attention</div>
        </div>
        <div class="status-card">
          <div class="k">Policies considered</div>
          <div class="v">14</div>
          <div class="s">4 mandatory · 10 retrieved</div>
        </div>
        <div class="status-card">
          <div class="k">Repository delta</div>
          <div class="v">3 changed</div>
          <div class="s">2 unchanged · 0 addressed</div>
        </div>
      </section>

      <section class="workbench">

        <!-- Left: attention queue -->
        <aside class="panel queue-panel">
          <div class="panel-head">
            <div>
              <div class="panel-title">Attention queue</div>
              <div class="panel-sub">What deserves human review</div>
            </div>
          </div>

          <div class="queue-tabs">
            <button class="queue-tab active">Attention 3</button>
            <button class="queue-tab">Cleared 2</button>
            <button class="queue-tab">All 5</button>
          </div>

          <div class="queue">
            <button class="queue-item active" onclick="selectItem(this,'material')">
              <div class="queue-top">
                <div class="queue-icon material">!</div>
                <div>
                  <div class="queue-title">Provider abstraction has one implementation</div>
                  <div class="queue-meta">sole_implementation · changed</div>
                </div>
              </div>
            </button>

            <button class="queue-item" onclick="selectItem(this,'leak')">
              <div class="queue-top">
                <div class="queue-icon material">!</div>
                <div>
                  <div class="queue-title">Retry semantics leak into domain code</div>
                  <div class="queue-meta">concept_leak · new</div>
                </div>
              </div>
            </button>

            <button class="queue-item" onclick="selectItem(this,'held')">
              <div class="queue-top">
                <div class="queue-icon held">?</div>
                <div>
                  <div class="queue-title">Duplicate timeout values need context</div>
                  <div class="queue-meta">duplicate_constant · held</div>
                </div>
              </div>
            </button>

            <button class="queue-item" onclick="selectItem(this,'cleared')">
              <div class="queue-top">
                <div class="queue-icon cleared">✓</div>
                <div>
                  <div class="queue-title">Invoice boundary is appropriate</div>
                  <div class="queue-meta">cleared · unchanged</div>
                </div>
              </div>
            </button>
          </div>

          <div class="queue-footer">Cleared candidates stay available, but do not compete with items that need attention.</div>
        </aside>

        <!-- Center: selected finding -->
        <article class="panel">
          <div class="finding-head">
            <div class="finding-topline">
              <span id="mainVerdict" class="verdict-badge material">Material finding</span>
              <button class="btn ghost">Open candidate evidence</button>
            </div>

            <h2 id="mainTitle" class="finding-title">Payment provider abstraction is carrying only one implementation</h2>

            <div id="mainSummary" class="finding-summary">
              The interface adds architectural indirection today, but the latest case revision says a second provider is planned within six months.
              That makes the abstraction defensible only if the future provider remains a concrete near-term requirement.
            </div>

            <div class="finding-context">
              <span class="tag">sole_implementation</span>
              <span class="tag">payments/gateway.py</span>
              <span class="tag">changed candidate</span>
              <span class="tag">2 policy bearings</span>
            </div>
          </div>

          <div class="finding-body">
            <section class="section">
              <div class="section-label">Why this matters</div>
              <div class="prose">
                ArchCompass found a stable interface/implementation pair but no demonstrated runtime variability in the repository.
                The architecture case changes the interpretation: future provider variability is expected, so the key question is whether the current abstraction is carrying a real design commitment or speculative complexity.
              </div>
            </section>

            <section class="section">
              <div class="section-label">Evidence from the repository</div>
              <div class="evidence-list">
                <div class="evidence">
                  <div class="evidence-top">
                    <div class="path">payments/gateway.py</div>
                    <div class="line">lines 12–26</div>
                  </div>
                  <p><code>PaymentGateway</code> defines the abstraction. One implementation was found: <code>StripePaymentGateway</code>.</p>
                </div>
                <div class="evidence">
                  <div class="evidence-top">
                    <div class="path">payments/stripe_gateway.py</div>
                    <div class="line">lines 8–37</div>
                  </div>
                  <p>No second provider implementation or deterministic registration path was found in the analyzed repository snapshot.</p>
                </div>
              </div>
            </section>

            <section class="section">
              <div class="section-label">Recommendation</div>
              <div class="recommendation">
                <strong>Keep the abstraction only if the second provider is still a committed near-term design requirement.</strong>
                <p>If that variability is no longer expected, collapse the interface and implementation until a second provider actually appears.</p>
              </div>
            </section>

            <section class="section">
              <div class="decision-row">
                <div class="decision-copy">
                  <strong>Standing decision</strong>
                  <p>Record how the team wants to treat this finding without changing the finding itself.</p>
                </div>
                <div class="decision-actions">
                  <button class="btn secondary" onclick="setDecision(this)">Accept</button>
                  <button class="btn secondary" onclick="setDecision(this)">Waive</button>
                  <button class="btn secondary" onclick="setDecision(this)">Park</button>
                </div>
              </div>
            </section>
          </div>
        </article>

        <!-- Right: contextual support -->
        <aside class="right">

          <section class="panel">
            <div class="panel-head">
              <div>
                <div class="panel-title">Judgement context</div>
                <div class="panel-sub">Why ArchCompass reached this conclusion</div>
              </div>
            </div>

            <div class="tabs">
              <button class="tab active" onclick="showTab(this,'case')">Case</button>
              <button class="tab" onclick="showTab(this,'policies')">Policies</button>
              <button class="tab" onclick="showTab(this,'provenance')">Provenance</button>
            </div>

            <div id="case" class="tab-content">
              <div class="context-row"><div class="k">Goal</div><div class="v">Keep payment providers replaceable without unnecessary abstraction.</div></div>
              <div class="context-row"><div class="k">Constraint</div><div class="v">Stripe is the only production provider today.</div></div>
              <div class="context-row"><div class="k">Decision</div><div class="v">Provider-specific code stays at the infrastructure edge.</div></div>
              <div class="context-row"><div class="k">Answer</div><div class="v">A second provider is planned within six months.</div></div>
            </div>

            <div id="policies" class="tab-content" style="display:none">
              <div class="policy">
                <div class="policy-top">
                  <div class="policy-name">Prefer demonstrated variation points</div>
                  <div class="policy-score">0.91</div>
                </div>
                <p>Abstractions should reflect stable variability, not speculative extension points.</p>
                <span class="source-badge">dense · rank 1</span>
              </div>
              <div class="policy">
                <div class="policy-top">
                  <div class="policy-name">Keep domain contracts stable when providers vary</div>
                  <div class="policy-score">required</div>
                </div>
                <p>External provider change should not force domain-facing API churn.</p>
                <span class="source-badge">mandatory</span>
              </div>
            </div>

            <div id="provenance" class="tab-content" style="display:none">
              <div class="context-row"><div class="k">Retriever</div><div class="v">dense-scoped · 1-k20</div></div>
              <div class="context-row"><div class="k">Embedding</div><div class="v">google:gemini-embedding-2:3072</div></div>
              <div class="context-row"><div class="k">Judge</div><div class="v">google:gemini-2.5-pro</div></div>
              <div class="context-row"><div class="k">Prompt</div><div class="v">judge:v1</div></div>
            </div>

            <div class="review-history">
              <button class="history-link"><span>Review revision history</span><span>rev. 1 → 4</span></button>
            </div>
          </section>

          <section id="clarification" class="panel" style="margin-top:14px">
            <div class="panel-head">
              <div>
                <div class="panel-title">Clarification</div>
                <div class="panel-sub">One unresolved question remains</div>
              </div>
            </div>
            <div class="tab-content">
              <div class="clarification">
                <div class="k">Needed for candidate #3</div>
                <strong>Is the 30-second timeout intended to be one shared business rule?</strong>
                <p>This determines whether ArchCompass should treat the duplicate values as duplicated knowledge or separate operational settings.</p>
                <div class="answer">
                  <textarea placeholder="Explain the architectural intent…">They are independent operational settings.</textarea>
                  <div class="answer-actions">
                    <button class="btn ghost">Skip</button>
                    <button class="btn primary" onclick="saveAnswer(this)">Save and rejudge</button>
                  </div>
                </div>
              </div>
            </div>
          </section>

        </aside>
      </section>

      <section class="principle">
        <div>
          <div class="k">ArchCompass operating model</div>
          <p>The application decides what deserves attention. Policy retrieval supplies relevant guidance. The model judges meaning. Human decisions remain separate.</p>
        </div>
        <div class="mini-flow">
          <span>Atlas</span><b>→</b><span>Candidate</span><b>→</b><span>Policies</span><b>→</b><span>Finding</span>
        </div>
      </section>

    </div>

  </main>
</div>

<script>
function showTab(button, id){
  [...button.parentElement.querySelectorAll('.tab')].forEach(x=>x.classList.remove('active'));
  button.classList.add('active');
  ['case','policies','provenance'].forEach(name=>{
    const el=document.getElementById(name);
    if(el) el.style.display = name===id ? 'block' : 'none';
  });
}
function saveAnswer(btn){
  const old=btn.textContent;
  btn.textContent='Saved — rejudgement queued';
  btn.style.background='#177a55';
  setTimeout(()=>{btn.textContent=old;btn.style.background=''},1800);
}
function setDecision(btn){
  const parent=btn.parentElement;
  [...parent.querySelectorAll('button')].forEach(x=>{
    x.style.background='#fff';x.style.color='#171a17';x.style.borderColor='#dde3dd';
  });
  btn.style.background='#eef1ff';
  btn.style.color='#4056d6';
  btn.style.borderColor='#cfd6fb';
}
function selectItem(btn, kind){
  [...btn.parentElement.querySelectorAll('.queue-item')].forEach(x=>x.classList.remove('active'));
  btn.classList.add('active');
  const verdict=document.getElementById('mainVerdict');
  const title=document.getElementById('mainTitle');
  const summary=document.getElementById('mainSummary');

  if(kind==='leak'){
    verdict.className='verdict-badge material';
    verdict.textContent='Material finding';
    title.textContent='Retry policy leaks provider behavior into the domain package';
    summary.textContent='Provider-specific retry semantics are referenced by domain-facing code, weakening the package boundary and exposing infrastructure concerns where they are not owned.';
  } else if(kind==='held'){
    verdict.className='verdict-badge held';
    verdict.textContent='Needs clarification';
    title.textContent='Duplicate timeout values may represent duplicated knowledge';
    summary.textContent='The repository evidence is clear, but the architectural meaning depends on intent: one shared business rule or two independent operational settings.';
  } else if(kind==='cleared'){
    verdict.className='verdict-badge cleared';
    verdict.textContent='Cleared';
    title.textContent='Repository boundary around invoice generation is appropriate';
    summary.textContent='The dependency direction matches the architecture case and no relevant policy bearing indicates material risk.';
  } else {
    verdict.className='verdict-badge material';
    verdict.textContent='Material finding';
    title.textContent='Payment provider abstraction is carrying only one implementation';
    summary.textContent='The interface adds architectural indirection today, but the latest case revision says a second provider is planned within six months. That makes the abstraction defensible only if the future provider remains a concrete near-term requirement.';
  }
}
</script>
</body>
</html>
