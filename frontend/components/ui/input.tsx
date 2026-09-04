import * as React from "react"

import { cn } from "@/lib/utils"

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "h-12 w-full min-w-0 rounded-full border border-input bg-surface px-5 py-2 text-[15px] transition-[border-color,box-shadow,background-color] outline-none placeholder:text-dim hover:bg-surface-2 focus-visible:border-brand focus-visible:bg-background focus-visible:ring-4 focus-visible:ring-brand/12 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive",
        className
      )}
      {...props}
    />
  )
}

export { Input }
