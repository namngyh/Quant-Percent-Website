import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * Content taken out of service, visibly.
 *
 * When a result is withdrawn for re-examination there are two dishonest ways
 * to handle it and one honest one. Deleting the section pretends it never
 * existed; leaving it up pretends nothing is wrong. Sealing it — content
 * still there, dimmed and inert, with a stamp across it saying why — tells
 * a reader exactly what they need to know: this was here, it is under review,
 * and these numbers are not to be relied on right now.
 *
 * The stamp is a physical metaphor on purpose. A banner reads as a notice
 * that can be scrolled past; a seal reads as a closure that applies to
 * everything under it. It stays in view while the sealed region scrolls, so
 * a reader deep in a long report is never looking at a dimmed chart without
 * the reason beside it.
 *
 * The dimmed content is hidden from assistive technology: its figures are
 * exactly what the seal says not to rely on, and reading them out would undo
 * the seal for anyone who cannot see it. The stamp itself is announced.
 */
export function Sealed({
  title,
  note,
  tone = "light",
  sticky = false,
  className,
  children,
}: {
  /** The stamp's heading — one or two words, set in capitals. */
  title: string;
  /** Why this is sealed and what happens next. One or two sentences. */
  note: string;
  /** Light surfaces take a red ink; dark bands take a pale one. */
  tone?: "light" | "dark";
  /** Keep the stamp in view while a tall sealed region scrolls past. */
  sticky?: boolean;
  className?: string;
  children: ReactNode;
}) {
  // Dimming a dark band lifts it to mid-grey, so a translucent stamp on it
  // has nothing to contrast against. The dark tone therefore fills solid
  // navy: a dark stamp on the grey remnant of a dark band still reads as
  // belonging to it, and the white text stays legible.
  const ink =
    tone === "dark"
      ? "border-white/90 text-white [--seal-fill:rgba(15,27,42,0.88)]"
      : "border-negative text-negative [--seal-fill:rgba(255,255,255,0.72)]";

  return (
    <div className={cn("relative", className)}>
      <div
        aria-hidden="true"
        className="pointer-events-none select-none opacity-40 grayscale blur-[1.5px]"
      >
        {children}
      </div>

      <div
        className={cn(
          "absolute inset-0 z-10 flex justify-center px-4",
          sticky ? "items-start" : "items-center",
        )}
      >
        <div
          role="note"
          className={cn(
            "seal-stamp max-w-md -rotate-[5deg] rounded-md border-[3px] border-double px-6 py-4 text-center shadow-[0_8px_30px_rgba(15,27,42,0.12)] backdrop-blur-[2px]",
            "bg-[var(--seal-fill)]",
            sticky && "sticky top-[38vh] mt-24",
            ink,
          )}
        >
          <p className="figure text-[13px] font-semibold uppercase tracking-[0.28em]">
            {title}
          </p>
          <p className="mt-2 text-sm leading-snug">{note}</p>
        </div>
      </div>
    </div>
  );
}
