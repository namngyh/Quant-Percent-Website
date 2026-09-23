"use client";

import type { ReactNode } from "react";
import { DropdownMenu } from "radix-ui";
import { ArrowUpRight, ChevronDown } from "lucide-react";
import { Link } from "@/i18n/navigation";
import { cn } from "@/lib/utils";

/**
 * One header menu: a pill that looks like the plain nav links beside it and
 * opens a short list under it.
 *
 * Radix supplies the parts that are easy to get subtly wrong by hand — arrow
 * keys, Escape, focus returning to the trigger, closing on outside click and on
 * item select. `modal={false}` because a modal menu locks page scroll and
 * blocks pointer events on everything else, which for a three-item nav list
 * only makes the page feel frozen.
 */
export function NavDropdown({
  label,
  active = false,
  align = "start",
  triggerClassName,
  children,
}: {
  label: ReactNode;
  /** Highlight the trigger the way an active nav link is highlighted. */
  active?: boolean;
  align?: "start" | "end";
  triggerClassName?: string;
  children: ReactNode;
}) {
  return (
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger
        data-active={active || undefined}
        className={cn(
          "nav-link group inline-flex items-center gap-1 whitespace-nowrap text-[13px] font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring",
          active ? "text-brand-strong" : "text-ink hover:text-brand-strong",
          triggerClassName
        )}
      >
        {label}
        <ChevronDown
          aria-hidden="true"
          className="size-3.5 opacity-60 transition-transform duration-200 group-data-[state=open]:rotate-180"
        />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align={align}
          sideOffset={8}
          className="nav-dropdown z-[60] min-w-[13rem] rounded-2xl border border-border bg-background p-1.5 shadow-[var(--shadow-md)]"
        >
          {children}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

const itemClass =
  "flex w-full cursor-pointer select-none flex-col rounded-xl px-3 py-2 text-left text-[13px] font-medium text-ink outline-none transition-colors data-[highlighted]:bg-surface-2 data-[highlighted]:text-brand-strong";

/** An in-site link inside a NavDropdown. */
export function NavDropdownLink({
  href,
  active = false,
  hint,
  children,
}: {
  href: string;
  active?: boolean;
  hint?: ReactNode;
  children: ReactNode;
}) {
  return (
    <DropdownMenu.Item asChild>
      <Link
        href={href}
        aria-current={active ? "page" : undefined}
        className={cn(itemClass, active && "bg-brand-soft text-brand-strong")}
      >
        <span>{children}</span>
        {hint && <span className="text-[12px] font-normal text-dim">{hint}</span>}
      </Link>
    </DropdownMenu.Item>
  );
}

/** A link to another site (the Terminal), opened in a new tab. */
export function NavDropdownExternal({
  href,
  hint,
  newTabLabel,
  children,
}: {
  href: string;
  hint?: ReactNode;
  /** Screen-reader note that the link leaves the current tab. */
  newTabLabel: string;
  children: ReactNode;
}) {
  return (
    <DropdownMenu.Item asChild>
      <a href={href} target="_blank" rel="noopener noreferrer" className={itemClass}>
        <span className="inline-flex items-center gap-1">
          {children}
          <ArrowUpRight aria-hidden="true" className="size-3.5" />
          <span className="sr-only">({newTabLabel})</span>
        </span>
        {hint && <span className="text-[12px] font-normal text-dim">{hint}</span>}
      </a>
    </DropdownMenu.Item>
  );
}

/** An action (sign out) inside a NavDropdown. */
export function NavDropdownButton({
  onSelect,
  children,
}: {
  onSelect: () => void;
  children: ReactNode;
}) {
  return (
    <DropdownMenu.Item onSelect={onSelect} className={itemClass}>
      {children}
    </DropdownMenu.Item>
  );
}

export function NavDropdownSeparator() {
  return <DropdownMenu.Separator className="mx-2 my-1 h-px bg-border" />;
}
