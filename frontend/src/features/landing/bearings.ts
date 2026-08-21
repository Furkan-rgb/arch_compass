/**
 * The three specimens the hero shows: a policy, and the finding it produced.
 *
 * Home reads nothing from the workspace by design, so these are written out — but every
 * field is shaped like the record it stands for, because a hero that invents a field is a
 * promise the product cannot keep:
 *
 * - `policy` is a `Policy`, and all three quoted here are real bundled ones, verbatim from
 *   `src/archcompass/policies/general/*.md`.
 * - `retrieved` and `also` give the two counts the workbench already prints:
 *   `RetrievalProvenance.selected_policy_ids.length` against `Finding.policies.length`.
 *   Retrieval pulls several policies; only some of them bear on the verdict, and saying so
 *   is the most honest number on the page.
 * - `reasoning` is a `PolicyBearing.reasoning` — the model's account of how *this* policy
 *   bore on *this* candidate. It is not the policy's text. `PolicyBearingResponse` carries
 *   `policy_id`, `policy_title` and `reasoning` and nothing else, so a finding surface
 *   could not quote a policy body even if it wanted to.
 * - `verdict` is a three-value `Verdict`. There is no score anywhere on this page because
 *   there is no score anywhere in the domain: the model returns `FindingOutput.material`,
 *   a bool.
 *
 * `node` is the one field with no counterpart on the wire. It names which element of the
 * atlas this finding was made against, which is what lets the map and the callout be the
 * same statement rather than two illustrations that happen to sit near each other.
 */
export type Bearing = {
  /** The atlas node this finding was made against. */
  node: string;
  policy: { id: string; title: string; strength: string; description: string };
  /** Bundled corpus or this workspace's own directory — `PolicyOrigin`. */
  origin: string;
  retrieved: number;
  candidate: string;
  verdict: "material" | "held" | "cleared";
  finding: string;
  reasoning: string;
  hinge?: string;
  /** The other policy that bore, if one did. */
  also?: string;
  source: string;
};

export const BEARINGS: Bearing[] = [
  {
    node: "gateway",
    policy: {
      id: "delay-premature-abstraction",
      title: "Delay abstractions until variation is credible",
      strength: "guidance",
      description:
        "An abstraction introduced before its variation exists is a guess about a boundary, paid for in interfaces, indirection, and configuration. Wait until a second real implementation or a committed change shows where the seam actually is.",
    },
    origin: "bundled corpus",
    retrieved: 6,
    candidate: "payments.gateway.PaymentGateway",
    verdict: "material",
    finding: "The payment provider abstraction carries a single implementation",
    reasoning:
      "The protocol has had one implementation since it was introduced, and it names stripe_retry_after — so the variation this abstraction was guessing at never arrived, and the interface now encodes the provider it was meant to keep replaceable.",
    also: "design-for-replaceability",
    source: "payments/gateway.py:12–26 · google:gemini-3.6",
  },
  {
    node: "orders",
    policy: {
      id: "give-state-one-writer",
      title: "Give every piece of shared state one writing owner",
      strength: "guidance",
      description:
        "State written by several components has no invariant anyone can enforce. Each datum gets one component that writes it, and everyone else reads through that component's interface or through a copy it publishes.",
    },
    origin: "bundled corpus",
    retrieved: 5,
    candidate: "orders.Repository",
    verdict: "held",
    finding: "The orders domain imports the persistence adapter directly",
    reasoning:
      "Five modules outside the domain reach this adapter and two of them write through it, so the state has more than one writer. Whether that breaks the policy depends on which component is meant to own it.",
    hinge: "who owns the adapter — the platform team, or the domain.",
    source: "domain/orders.py:4 · awaiting an answer since review 4",
  },
  {
    node: "invoice",
    policy: {
      id: "explicit-source-of-truth",
      title: "Make the source of truth explicit",
      strength: "guidance",
      description:
        "For every piece of authoritative state or configuration, one place defines it and everything else is visibly derived from that place. When several sources can supply the same value and precedence is implicit, the system's real behaviour is discovered by experiment rather than by reading.",
    },
    origin: "bundled corpus",
    retrieved: 7,
    candidate: "billing.invoice.InvoiceBoundary",
    verdict: "cleared",
    finding: "The invoice boundary is earning its place",
    reasoning:
      "Every posting path resolves through this boundary and no other module writes the ledger directly, so the authoritative place is both singular and visible. The seam does exactly what the policy asks of it.",
    also: "prefer-deep-modules",
    source: "billing/invoice.py:8 · unchanged since review 2",
  },
];
