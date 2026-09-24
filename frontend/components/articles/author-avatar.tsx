import { cn } from "@/lib/utils";

const SIZES = {
  xs: "size-6 text-[10px]",
  sm: "size-8 text-[12px]",
  md: "size-10 text-[13px]",
  lg: "size-16 text-[20px]",
  xl: "size-24 text-[28px]",
} as const;

/**
 * A member's portrait, or their initials in a circle when they have not
 * uploaded one.
 *
 * A plain <img> rather than next/image: the file is already a small square
 * Cloudinary rendition in the browser's best format, so the Next optimiser
 * would only add a second resize and a host allow-list to keep in step.
 */
export function AuthorAvatar({
  name,
  src,
  size = "md",
  className,
}: {
  name: string;
  src?: string | null;
  size?: keyof typeof SIZES;
  className?: string;
}) {
  const classes = cn(
    "flex shrink-0 items-center justify-center overflow-hidden rounded-full",
    SIZES[size],
    className
  );

  if (src) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={src}
        alt=""
        aria-hidden="true"
        loading="lazy"
        decoding="async"
        className={cn(classes, "bg-brand-soft object-cover")}
      />
    );
  }

  const words = name.trim().split(/\s+/).filter(Boolean);
  // Vietnamese names put the given name last, so that is the letter people
  // recognise; one more from the family name makes it distinguishable.
  const initials =
    words.length > 1
      ? `${words[0][0]}${words[words.length - 1][0]}`
      : (words[0]?.slice(0, 2) ?? "?");

  return (
    <span
      aria-hidden="true"
      className={cn(classes, "bg-brand-soft font-semibold uppercase text-brand-strong")}
    >
      {initials}
    </span>
  );
}
