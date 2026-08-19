/** Join class names, dropping anything falsy. The whole of our styling glue. */
export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}
