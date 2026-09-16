import { cn } from "@/lib/utils";

/** Initials in a circle. Nobody uploads a portrait, so a letter it is. */
export function AuthorAvatar({
  name,
  size = "md",
}: {
  name: string;
  size?: "sm" | "md";
}) {
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
      className={cn(
        "flex shrink-0 items-center justify-center rounded-full bg-brand-soft font-semibold uppercase text-brand-strong",
        size === "sm" ? "size-8 text-[12px]" : "size-10 text-[13px]"
      )}
    >
      {initials}
    </span>
  );
}
