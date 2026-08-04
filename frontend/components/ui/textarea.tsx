import * as React from "react"

import { cn } from "@/lib/utils"

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "min-h-32 w-full rounded-lg border border-input bg-background px-3.5 py-2.5 text-[15px] transition-[border-color,box-shadow] outline-none placeholder:text-dim focus-visible:border-brand focus-visible:ring-2 focus-visible:ring-brand/15 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive",
        className
      )}
      {...props}
    />
  )
}

export { Textarea }
