/**
 * The name shadcn's registry imports `cn` from.
 *
 * A component copied out of the registry arrives with `import { cn } from "@/lib/utils"` at
 * the top. This file is that path, so a vendored component compiles here unedited and the
 * next `shadcn add` does not need a hand-rewritten import. The implementation stays in
 * `lib/cn.ts`, which is where the reasoning about `twMerge` is written down.
 */
export { cn } from "./cn";
