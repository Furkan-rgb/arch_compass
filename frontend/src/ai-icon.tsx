/**
 * The one icon for talking to the model: a speech bubble with a spark on its shoulder.
 *
 * Drawn here rather than imported because lucide ships the bubble and the spark as
 * separate icons and this product's convention is the combination — the widely-recognised
 * "AI chat" mark. Every control that opens a conversation with the model wears exactly
 * this one, so a reader learns it once; the bare Sparkles icon stays reserved for content
 * the model produced (a suggested answer), which is a different statement.
 *
 * Matches lucide's geometry (24-unit viewBox, 2-unit round stroke, currentColor) so it
 * sits in a row of lucide icons without looking adopted. The spark is filled where the
 * bubble is stroked: it reads as sitting on the conversation, not drawn into it.
 */
export function AiChatIcon({ size = 14 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M16 15a2 2 0 0 1-2 2H7.5L3.5 21V8a2 2 0 0 1 2-2h8.5a2 2 0 0 1 2 2z" />
      <path
        d="M19.5 1q.8 3.2 4 4-3.2.8-4 4-.8-3.2-4-4 3.2-.8 4-4Z"
        fill="currentColor"
        stroke="none"
      />
    </svg>
  );
}
