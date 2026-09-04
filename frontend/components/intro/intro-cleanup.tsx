"use client";

import { useEffect } from "react";

/**
 * Clears `data-intro` once the opening sequence is over, and lets a reader cut
 * it short.
 *
 * The animation itself does not need this — every keyframe ends on `forwards`
 * at opacity 0 with pointer events off, so the page is usable whether or not
 * this component ever mounts. Removing the attribute is housekeeping: it takes
 * the finished panels out of the layer tree and stops the header brand
 * carrying an animation it has already finished.
 *
 * Skipping works by removing the attribute early, which drops the panels
 * instantly. That is deliberate — trying to fast-forward a CSS animation
 * mid-flight looks worse than cutting to the finished page.
 */

/** Slightly past the longest keyframe so nothing is cut off on its own.
 *  The board reveal is the last to finish, at 3s. */
const SEQUENCE_MS = 3150;

export function IntroCleanup() {
  useEffect(() => {
    const root = document.documentElement;
    if (root.getAttribute("data-intro") !== "play") return;

    const clear = () => root.removeAttribute("data-intro");
    const timer = window.setTimeout(clear, SEQUENCE_MS);

    const opts = { once: true, passive: true } as const;
    window.addEventListener("pointerdown", clear, opts);
    window.addEventListener("keydown", clear, opts);
    window.addEventListener("wheel", clear, opts);
    window.addEventListener("touchmove", clear, opts);

    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("pointerdown", clear);
      window.removeEventListener("keydown", clear);
      window.removeEventListener("wheel", clear);
      window.removeEventListener("touchmove", clear);
      clear();
    };
  }, []);

  return null;
}
