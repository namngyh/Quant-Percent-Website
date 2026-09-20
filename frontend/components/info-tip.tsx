"use client";

import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Info } from "lucide-react";
import { cn } from "@/lib/utils";

interface TooltipPosition {
  left: number;
  top: number;
  placement: "top" | "bottom";
}

/**
 * Small accessible tooltip for metric explanations (spec §7.3, §8.7).
 *
 * `text` may be several paragraphs: a section's assumptions and limits
 * live behind one icon rather than as a block of small print under the
 * table. `wide` is for those — a 15rem box wraps a paragraph into a column.
 */
export function InfoTip({
  text,
  className,
  wide = false,
}: {
  text: string | string[];
  className?: string;
  wide?: boolean;
}) {
  const paragraphs = Array.isArray(text) ? text : [text];
  const label = paragraphs.join(" ");
  const id = useId();
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<TooltipPosition | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const tooltipRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;

    const updatePosition = () => {
      const trigger = triggerRef.current;
      if (!trigger) return;

      const rect = trigger.getBoundingClientRect();
      const viewportPadding = 12;
      // Open to the right of the icon, so the box never runs under the
      // heading it explains; only slide back when the viewport is short.
      const tooltipWidth = Math.min(wide ? 352 : 240, window.innerWidth - 2 * viewportPadding);
      const left = Math.max(
        viewportPadding,
        Math.min(window.innerWidth - viewportPadding - tooltipWidth, rect.left)
      );
      const placement = rect.top >= 128 ? "top" : "bottom";

      setPosition({
        left,
        top: placement === "top" ? rect.top - 8 : rect.bottom + 8,
        placement,
      });
    };

    const frame = window.requestAnimationFrame(updatePosition);
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open, wide]);

  useEffect(() => {
    if (!open) return;

    const closeOnOutsidePress = (event: PointerEvent) => {
      const target = event.target as Node;
      if (
        triggerRef.current?.contains(target) ||
        tooltipRef.current?.contains(target)
      ) {
        return;
      }
      setOpen(false);
      setPosition(null);
    };

    document.addEventListener("pointerdown", closeOnOutsidePress);
    return () => document.removeEventListener("pointerdown", closeOnOutsidePress);
  }, [open]);

  return (
    <span className={cn("inline-flex", className)}>
      <button
        ref={triggerRef}
        type="button"
        aria-describedby={open ? id : undefined}
        aria-label={label}
        className="text-dim transition-colors hover:text-foreground focus-visible:text-foreground"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => {
          setOpen(false);
          setPosition(null);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => {
          setOpen(false);
          setPosition(null);
        }}
        onClick={() => {
          if (open) {
            setOpen(false);
            setPosition(null);
          } else {
            setOpen(true);
          }
        }}
      >
        <Info className={wide ? "size-4" : "size-3.5"} aria-hidden="true" />
      </button>
      {open &&
        position &&
        createPortal(
          <span
            ref={tooltipRef}
            id={id}
            role="tooltip"
            className={cn(
              "pointer-events-none fixed z-[100] max-w-[calc(100vw-1.5rem)] rounded-lg border border-border bg-background p-3 text-xs font-normal normal-case leading-relaxed tracking-normal text-ink shadow-lg",
              wide ? "w-[22rem] space-y-2 text-left" : "w-60",
            )}
            style={{
              left: position.left,
              top: position.top,
              transform: position.placement === "top" ? "translate(0, -100%)" : "none",
            }}
          >
            {paragraphs.map((p, i) => (
              <span key={i} className="block">
                {p}
              </span>
            ))}
          </span>,
          document.body
        )}
    </span>
  );
}
