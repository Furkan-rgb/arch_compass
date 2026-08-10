/** How text is cut to fit a card, and how a relationship kind becomes a class name. */

export function truncate(value: string, length: number) {
  return value.length > length ? `${value.slice(0, length - 1)}…` : value;
}

export function edgeKindClass(kind: string) {
  return kind.replaceAll("_", "-").replace(/[^a-z0-9-]/gi, "").toLocaleLowerCase();
}
