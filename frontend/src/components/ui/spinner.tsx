import { cn } from "@/lib/utils"
import { LoaderIcon } from "lucide-react"

/* The spoked loader, deliberately not the registry's arc (`Loader2Icon`). The arc is
   three-quarters of a circle, so even a mathematically centred rotation sends its whole
   visible mass travelling around the middle — at the 12–13px this design draws it, that
   reads as a blob orbiting rather than a mark spinning. The spokes are symmetric about
   the centre, so rotation reads as rotation. The transform-box pair stays: WebKit
   resolves an SVG's transform-origin against the viewport without it, which was the
   *other* way this icon orbited. */
function Spinner({ className, ...props }: React.ComponentProps<"svg">) {
  return (
    <LoaderIcon data-slot="spinner" role="status" aria-label="Loading" className={cn("size-4 animate-spin [transform-box:fill-box] origin-center", className)} {...props} />
  )
}

export { Spinner }
