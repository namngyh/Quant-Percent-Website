import Image from "next/image";
import { cn } from "@/lib/utils";

export function Brand({
  className,
  priority = false,
}: {
  className?: string;
  priority?: boolean;
}) {
  return (
    <span className={cn("inline-flex items-center gap-2.5 whitespace-nowrap", className)}>
      <Image
        src="/quant-percent-mark.svg"
        alt=""
        width={38}
        height={38}
        priority={priority}
        className="size-[38px] shrink-0"
      />
      <span className="text-[15px] font-semibold">Quant Percent</span>
    </span>
  );
}
