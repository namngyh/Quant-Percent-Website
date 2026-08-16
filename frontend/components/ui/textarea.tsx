import * as React from "react"

import { cn } from "@/lib/utils"

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        // A textarea holds paragraphs, so it keeps a rounded rectangle where a
        // single-line input becomes a pill — a pill several lines tall wastes
        // its first and last line to the curve.
        "min-h-32 w-full rounded-lg border border-input bg-surface px-4 py-3 text-[15px] transition-[border-color,box-shadow,background-color] outline-none placeholder:text-dim hover:bg-surface-2 focus-visible:border-brand focus-visible:bg-background focus-visible:ring-4 focus-visible:ring-brand/12 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive",
        className
      )}
      {...props}
    />
  )
}

export { Textarea }
