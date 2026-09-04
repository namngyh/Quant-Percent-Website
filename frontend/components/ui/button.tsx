import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/lib/utils"

// Quant Percent buttons are restrained and use no gradients. They are pills:
// at this size a fully rounded edge reads as a control rather than as a box,
// and it is the one shape the whole interface shares — chips, nav items, tags
// and buttons all end the same way, which is most of what makes a surface look
// designed rather than assembled.
const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-full text-[14px] font-medium tracking-[0.01em] transition-colors duration-200 outline-none select-none focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        // One flat accent, darkening on hover. It was a three-stop gradient
        // that slid on hover behind a white sheen; the button is 40px tall and
        // most of that colour travel was never visible at that size anyway.
        primary: "bg-accent text-white hover:bg-accent-strong",
        outline:
          "border border-input bg-transparent text-foreground hover:border-accent hover:bg-accent-tint hover:text-accent-strong",
        ghost:
          "border border-transparent bg-transparent text-ink hover:bg-surface-2 hover:text-brand-strong",
        subtle: "bg-brand-soft text-brand-strong hover:bg-brand hover:text-white",
      },
      size: {
        default: "px-6 py-2.5",
        sm: "px-4 py-2 text-[13px]",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "primary",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
