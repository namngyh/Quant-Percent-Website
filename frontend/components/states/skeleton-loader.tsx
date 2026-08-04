import { cn } from "@/lib/utils";

export function SkeletonLoader({
  className,
  rows = 3,
}: {
  className?: string;
  rows?: number;
}) {
  return (
    <div className={cn("animate-pulse space-y-3", className)} aria-hidden="true">
      {Array.from({ length: rows }, (_, i) => (
        <div
          key={i}
          className="h-4 rounded-md bg-surface"
          style={{ width: `${100 - (i % 3) * 18}%` }}
        />
      ))}
    </div>
  );
}
