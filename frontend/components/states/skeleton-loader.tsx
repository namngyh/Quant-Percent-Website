import { cn } from "@/lib/utils";

export function SkeletonLoader({
  className,
  rows = 3,
  barClassName,
}: {
  className?: string;
  rows?: number;
  /** Bar fill, for skeletons that sit on something other than the white
   *  ground. `bg-surface` is a hair off white and disappears on a dark
   *  section. */
  barClassName?: string;
}) {
  return (
    <div className={cn("animate-pulse space-y-3", className)} aria-hidden="true">
      {Array.from({ length: rows }, (_, i) => (
        <div
          key={i}
          className={cn("h-4 rounded-md bg-surface", barClassName)}
          style={{ width: `${100 - (i % 3) * 18}%` }}
        />
      ))}
    </div>
  );
}
