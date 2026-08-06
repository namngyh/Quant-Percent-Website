import { cn } from "@/lib/utils";

/**
 * The brand percent mark as inline SVG.
 *
 * The file in /public carries a baked white background and a fixed dark fill,
 * which is right for a favicon and wrong for a display element — on the dark
 * hero it would paint a white box. This draws the same three shapes with
 * `currentColor`, so a caller sets size and colour with normal classes and the
 * mark can run large, cropped, or at low opacity behind text.
 */
export function PercentMark({
  className,
  title,
}: {
  className?: string;
  title?: string;
}) {
  return (
    <svg
      viewBox="0 0 100 100"
      className={cn("shrink-0", className)}
      fill="currentColor"
      role={title ? "img" : "presentation"}
      aria-label={title}
      aria-hidden={title ? undefined : true}
    >
      {title && <title>{title}</title>}
      <rect x="22" y="18" width="18" height="18" />
      <path d="M70 14 78 22 30 76 22 68z" />
      <rect x="60" y="58" width="18" height="18" />
    </svg>
  );
}
