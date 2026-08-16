"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * Subscribe to a CSS media query from React.
 *
 * Charts are the reason this exists. CSS can restyle a chart's container but
 * not its contents: an ECharts option is a plain object built in JavaScript,
 * so font sizes, label visibility and plot padding have to be decided before
 * the chart is handed the option, and on a 390px screen those need different
 * values than on a desktop.
 *
 * `useSyncExternalStore` rather than state plus an effect. `matchMedia` is
 * exactly what this hook is for — a value that lives outside React and changes
 * on its own — and it takes an explicit server snapshot, so the query is never
 * read during a render that has to match server output. Reading it with
 * `useState` + `useEffect` works but schedules a second render on every mount
 * and trips the lint rule against setting state synchronously in an effect.
 *
 * The server snapshot is `false`, so anything using this must be correct — if
 * plain — at the wide setting, and narrows once the browser takes over.
 */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onStoreChange: () => void) => {
      const mql = window.matchMedia(query);
      mql.addEventListener("change", onStoreChange);
      return () => mql.removeEventListener("change", onStoreChange);
    },
    [query],
  );

  const getSnapshot = useCallback(
    () => window.matchMedia(query).matches,
    [query],
  );

  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}
