import { Badge, Tag } from "../../ui/badge";
import { Mono } from "../../ui/meta";

/**
 * A product preview built out of the product's own vocabulary, not a screenshot and not an
 * abstract illustration. Static by design: it is a picture of the workbench, so it uses the
 * same verdict marks, the same monospace identifiers, and the same three-pane shape.
 */
export function WorkbenchPreview() {
  return (
    <div
      aria-label="A preview of the ArchCompass review workbench"
      role="img"
      className="overflow-hidden rounded-lg border border-rule bg-surface shadow-hero"
    >
      <div className="flex items-center gap-2 border-b border-rule bg-surface-2 px-3 py-2">
        <span className="flex gap-1.5" aria-hidden="true">
          <span className="size-2 rounded-full bg-rule-strong" />
          <span className="size-2 rounded-full bg-rule-strong" />
          <span className="size-2 rounded-full bg-rule-strong" />
        </span>
        <Mono className="truncate text-[10px] text-ink-3">
          payments-platform · main · 8f31c2a · review 4
        </Mono>
      </div>

      <div className="grid gap-px bg-rule sm:grid-cols-[130px_minmax(0,1fr)_150px]">
        <div className="hidden bg-surface p-2.5 sm:block">
          <div className="text-[9px] font-bold uppercase tracking-[0.12em] text-ink-3">
            Attention
          </div>
          <ul className="mt-2 grid gap-1.5">
            {[
              ["▲", "Provider abstraction", "text-material"],
              ["▲", "Retry semantics leak", "text-material"],
              ["◆", "Duplicate timeouts", "text-held"],
              ["●", "Invoice boundary", "text-cleared"],
            ].map(([glyph, label, tone], index) => (
              <li
                key={label}
                className={`flex items-start gap-1.5 rounded-sm px-1.5 py-1 text-[10px] leading-4 ${
                  index === 0 ? "bg-accent-soft text-ink" : "text-ink-2"
                }`}
              >
                <span aria-hidden="true" className={`${tone} text-[8px] leading-4`}>
                  {glyph}
                </span>
                <span className="truncate">{label}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="bg-surface p-3">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone="material" glyph="▲">
              Material
            </Badge>
            <Tag>
              <span className="font-mono text-[10px]">sole_implementation</span>
            </Tag>
            <Tag>changed</Tag>
          </div>
          <h3 className="mt-2 font-display text-sm font-semibold leading-5 text-ink">
            The payment provider abstraction carries a single implementation
          </h3>
          <p className="mt-1.5 text-[11px] leading-5 text-ink-2">
            The port exists to keep providers replaceable, but only one adapter implements it and
            the domain still names Stripe-specific retry behaviour.
          </p>
          <div className="mt-2.5 rounded-sm border border-rule bg-sunken/70 px-2 py-1.5">
            <Mono className="block text-[10px] text-ink-3">payments/gateway.py:12-26</Mono>
            <Mono className="mt-0.5 block truncate text-[10px] text-ink">
              class PaymentGateway(Protocol):
            </Mono>
          </div>
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            <span className="rounded-xs border border-rule bg-surface-2 px-1.5 py-0.5 text-[9px] text-ink-2">
              Accept
            </span>
            <span className="rounded-xs border border-rule bg-surface-2 px-1.5 py-0.5 text-[9px] text-ink-2">
              Park
            </span>
            <span className="rounded-xs border border-rule bg-surface-2 px-1.5 py-0.5 text-[9px] text-ink-2">
              Waive
            </span>
          </div>
        </div>

        <div className="hidden bg-surface p-2.5 lg:block">
          <div className="text-[9px] font-bold uppercase tracking-[0.12em] text-ink-3">
            Provenance
          </div>
          <dl className="mt-2 grid gap-1.5 text-[10px] leading-4">
            {[
              ["Retriever", "dense-scoped · 1-k20"],
              ["Embedding", "ollama:nomic-embed"],
              ["Judge", "google:gemini-3.6"],
              ["Prompt", "judge:v1"],
            ].map(([key, value]) => (
              <div key={key}>
                <dt className="text-ink-3">{key}</dt>
                <dd className="truncate font-mono text-ink-2">{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </div>
  );
}
