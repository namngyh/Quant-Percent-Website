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

/** Small accessible tooltip for metric explanations (spec §7.3, §8.7). */
export function InfoTip({
  text,
  className,
}: {
  text: string;
  className?: string;
}) {
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
      const tooltipHalfWidth = Math.min(120, (window.innerWidth - 24) / 2);
      const left = Math.min(
        window.innerWidth - viewportPadding - tooltipHalfWidth,
        Math.max(
          viewportPadding + tooltipHalfWidth,
          rect.left + rect.width / 2
        )
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
  }, [open]);

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
        aria-label={text}
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
        <Info className="size-3.5" aria-hidden="true" />
      </button>
      {open &&
        position &&
        createPortal(
          <span
            ref={tooltipRef}
            id={id}
            role="tooltip"
            className="pointer-events-none fixed z-[100] w-60 max-w-[calc(100vw-1.5rem)] -translate-x-1/2 rounded-lg border border-border bg-background p-3 text-xs font-normal normal-case leading-relaxed tracking-normal text-ink shadow-lg"
            style={{
              left: position.left,
              top: position.top,
              transform:
                position.placement === "top"
                  ? "translate(-50%, -100%)"
                  : "translate(-50%, 0)",
            }}
          >
            {text}
          </span>,
          document.body
        )}
    </span>
  );
}
