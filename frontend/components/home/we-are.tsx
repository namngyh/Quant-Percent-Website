"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useReducedMotion } from "framer-motion";
import { useHydrated } from "@/lib/use-hydrated";

/**
 * "Chúng tôi là …" with the role typing itself out, erasing, and typing the
 * next one.
 *
 * A rotating list says something a fixed line cannot: that the same people are
 * all of these at once. One label would have to be chosen, and any single
 * choice — traders, or researchers, or mathematicians — is narrower than the
 * truth.
 *
 * Three details that matter more than the effect itself:
 *
 *   * **It starts finished.** The initial state is the first role fully typed,
 *     not an empty string, so the server renders a complete sentence and the
 *     first frame in the browser is identical to it. Starting at zero would
 *     have meant a dangling "Chúng tôi là" in the HTML — for a reader without
 *     JavaScript, permanently.
 *   * **It reserves its height.** The roles differ in length and the widest is
 *     nearly twice the shortest, so the line is given a fixed minimum height
 *     and the board below it never moves as words change.
 *   * **Assistive technology gets the list, not the animation.** The animated
 *     text is `aria-hidden` and a visually hidden sentence carries every role
 *     in reading order. A screen reader announcing a character at a time, then
 *     unannouncing them one at a time, would be unusable.
 *
 * Under `prefers-reduced-motion` nothing runs: the first role is shown and
 * stays, cursor included but not blinking (the blink is CSS, disabled globally
 * by the same media query).
 */

/** Milliseconds per keystroke, per erase, and the pause at a finished word. */
const TYPE_MS = 58;
const ERASE_MS = 28;
const HOLD_MS = 1750;
const BETWEEN_MS = 260;

/**
 * Coerce whatever `t.raw` hands back into a list of strings.
 *
 * This is defensive on purpose. The first version assumed an array and called
 * `.join` on it; when the dev server was holding a stale copy of the messages
 * file the key was absent, `.join` threw, and the whole homepage returned 500
 * — a decorative line took the page down with it. Nothing here is important
 * enough to do that, so an unusable value now yields an empty list and the
 * component renders nothing at all.
 */
function toRoles(value: unknown): string[] {
  if (Array.isArray(value)) return value.filter((v) => typeof v === "string");
  // next-intl can hand back an object keyed by index depending on how the
  // messages were loaded.
  if (value && typeof value === "object") {
    return Object.values(value).filter((v): v is string => typeof v === "string");
  }
  return [];
}

export function WeAre() {
  const t = useTranslations("home.hero");
  const label = t("weAre");
  // `t.raw` because this key is a list, not a string.
  const roles = toRoles(t.raw("roles"));
  const finale = t("finale");

  const reduced = useReducedMotion();
  const hydrated = useHydrated();
  const still = hydrated && reduced;

  /*
   * The roles once through, then the closing line, and then it stops.
   *
   * "tất cả những điều trên" only means anything as a conclusion. Left in the
   * loop it would sweep past every fifteenth turn like the others and say
   * nothing — a summary of a list the reader is still in the middle of. So the
   * sequence runs once and holds there, which also ends the animation instead
   * of moving something on the page forever.
   *
   * It is deliberately absent under reduced motion and before hydration: with
   * no list having been shown, "all of the above" refers to nothing. Those
   * readers get the first role instead, which stands on its own.
   */
  const sequence = useMemo(() => [...roles, finale], [roles, finale]);

  // Begins on the first role, fully typed — see the note above.
  const [state, setState] = useState({
    i: 0,
    n: roles[0]?.length ?? 0,
    erasing: false,
  });

  useEffect(() => {
    if (still || sequence.length < 2) return;
    const last = sequence.length - 1;
    const word = sequence[state.i] ?? "";

    // The closing line, fully typed: nothing further is scheduled.
    if (state.i === last && !state.erasing && state.n === word.length) return;

    let delay: number;
    if (!state.erasing && state.n < word.length) delay = TYPE_MS;
    else if (!state.erasing) delay = HOLD_MS;
    else if (state.n > 0) delay = ERASE_MS;
    else delay = BETWEEN_MS;

    // setState lives in the timer callback, never in the effect body, so this
    // schedules one render per keystroke rather than cascading during render.
    const id = window.setTimeout(() => {
      setState((s) => {
        const w = sequence[s.i] ?? "";
        if (!s.erasing && s.n < w.length) return { ...s, n: s.n + 1 };
        if (!s.erasing) return { ...s, erasing: true };
        if (s.n > 0) return { ...s, n: s.n - 1 };
        return { i: Math.min(s.i + 1, last), n: 0, erasing: false };
      });
    }, delay);

    return () => window.clearTimeout(id);
  }, [state, sequence, still]);

  // Nothing to say — render nothing, rather than a dangling "Chúng tôi là".
  if (roles.length === 0) return null;

  const shown = still
    ? (roles[0] ?? "")
    : (sequence[state.i] ?? "").slice(0, state.n);

  return (
    /*
      The height is fixed, not minimum, and the row centres rather than sharing
      a baseline. Both are needed to stop the board below from moving.

      The animated span used to be an `inline-flex` with `min-height`, which
      makes it an atomic inline box whose height is its content's height. In
      Vietnamese that height changes with almost every keystroke — "học" carries
      a mark above and a dot below where "nhà t" carries neither — so the line
      box grew and shrank by about a pixel per character and the whole right
      column shivered. Measured at 0.53px of travel on the board, which is small
      but moving constantly, which is what made it read as jitter.

      With a fixed `h-7` the line cannot respond to its content at all, and the
      text is a plain inline span again so it never forms a box of its own.
      `whitespace-nowrap` keeps a long role on one line; the longest fits the
      narrowest two-column width with room to spare.
    */
    <p className="flex h-7 items-center gap-x-2.5 overflow-hidden text-[15px]">
      <span className="shrink-0 uppercase tracking-[0.1em] text-dim">
        {label}
      </span>

      <span
        aria-hidden="true"
        className="whitespace-nowrap font-medium text-accent"
      >
        {shown}
        <span className="we-are-caret" />
      </span>

      {/* What a screen reader actually reads: the whole list, once. */}
      <span className="sr-only">{roles.join(", ")}</span>
    </p>
  );
}
