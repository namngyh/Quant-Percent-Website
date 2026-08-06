/**
 * Screenshot every page in a real browser and report layout problems.
 *
 * HTTP 200 says nothing about how a page looks. The three faults that shipped
 * — a stale "illustrative" badge, an empty four-column gap in a seven-column
 * grid, and the same three quotes rendered twice — all returned 200 and all
 * were obvious on sight. This closes that gap.
 *
 *   npx tsx scripts/screenshot.ts                 # desktop + mobile
 *   npx tsx scripts/screenshot.ts --only /vi      # one page
 *
 * Uses the Chrome already installed on the machine, so nothing extra is
 * downloaded. Images land in screenshots/, which is gitignored.
 */
import { existsSync, mkdirSync, rmSync } from "node:fs";
import path from "node:path";
import puppeteer, { type Browser, type Page } from "puppeteer-core";

const BASE = process.env.SITE_URL ?? "http://localhost:3000";
const OUT = path.resolve(process.cwd(), "screenshots");

const CHROME = [
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
].find((p) => existsSync(p));

const PAGES = [
  "/vi",
  "/en",
  "/vi/market-intelligence",
  "/vi/models",
  "/vi/models/msdp",
  // The network model carries the ranking table and cluster charts, so it is
  // the page most likely to break on a layout change.
  "/vi/models/dynamic-graph",
  "/en/models/dynamic-graph",
  "/vi/models/rarf-fhe",
  "/vi/performance",
  // Empty-state only: the filled result panel needs a submitted portfolio,
  // which `npm run check:portfolio` drives end to end.
  "/vi/quant-portfolio",
  "/en/quant-portfolio",
  "/vi/about",
  "/vi/contact",
  "/vi/system-status",
  "/vi/login",
];

const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "mobile", width: 390, height: 844 },
];

type Problem = { page: string; viewport: string; kind: string; detail: string };

/** Checks that need the live DOM — the reason a real browser is worth it. */
async function inspect(page: Page): Promise<Omit<Problem, "page" | "viewport">[]> {
  return page.evaluate(() => {
    const found: { kind: string; detail: string }[] = [];

    // Horizontal overflow: the page body must never scroll sideways.
    if (document.documentElement.scrollWidth > window.innerWidth + 1) {
      found.push({
        kind: "overflow-x",
        detail: `${document.documentElement.scrollWidth}px > ${window.innerWidth}px viewport`,
      });
    }

    // Elements poking past the right edge — but only ones a visitor can
    // actually see spill. A decorative glow inside an overflow-hidden hero is
    // clipped by its parent and causes no scrollbar; flagging it trains the
    // reader to ignore this check.
    // No named helper here: the bundler rewrites named functions with a
    // __name shim that does not exist inside page.evaluate.
    for (const el of Array.from(document.querySelectorAll<HTMLElement>("*"))) {
      if (el.getAttribute("aria-hidden") === "true") continue;
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.right <= window.innerWidth + 2) continue;

      let isClipped = false;
      for (let p = el.parentElement; p; p = p.parentElement) {
        const o = getComputedStyle(p);
        if (
          o.overflow !== "visible" ||
          o.overflowX !== "visible"
        ) {
          isClipped = true;
          break;
        }
      }
      if (isClipped) continue;

      found.push({
        kind: "element-overflow",
        detail: `<${el.tagName.toLowerCase()} class="${el.className.toString().slice(0, 60)}"> right=${Math.round(r.right)}`,
      });
      break;
    }

    // A grid whose children fill fewer than half its columns leaves a visible
    // dead zone — exactly the empty grey block that shipped on the homepage.
    for (const el of Array.from(document.querySelectorAll<HTMLElement>("*"))) {
      const style = getComputedStyle(el);
      if (!style.display.includes("grid")) continue;
      const cols = style.gridTemplateColumns.split(" ").filter(Boolean).length;
      const kids = Array.from(el.children).filter(
        (c) => (c as HTMLElement).offsetParent !== null
      ).length;
      if (cols >= 4 && kids > 0 && kids < cols / 2) {
        found.push({
          kind: "sparse-grid",
          detail: `${kids} child(ren) in ${cols} columns — class="${el.className.toString().slice(0, 60)}"`,
        });
      }
    }

    // Text clipped by a fixed-height box. Screen-reader-only text is clipped
    // on purpose — that is how sr-only works — so skip anything shrunk to a
    // pixel or hidden behind a clip rect.
    for (const el of Array.from(document.querySelectorAll<HTMLElement>("p,h1,h2,h3,td,dt,dd,span"))) {
      const style = getComputedStyle(el);
      if (style.overflow !== "hidden") continue;
      if (el.clientHeight <= 2 || el.clientWidth <= 2) continue;
      if (style.clipPath !== "none" || style.clip !== "auto") continue;
      if (style.webkitLineClamp !== "none") continue; // deliberate truncation
      if (el.scrollHeight > el.clientHeight + 4) {
        found.push({
          kind: "clipped-text",
          detail: `"${(el.textContent ?? "").trim().slice(0, 50)}"`,
        });
        break;
      }
    }

    // Anything still advertising itself as placeholder data.
    const body = document.body.innerText;
    for (const marker of ["MINH HỌA", "ILLUSTRATIVE", "undefined", "NaN", "[object Object]"]) {
      if (body.includes(marker)) {
        found.push({ kind: "bad-text", detail: marker });
      }
    }
    return found;
  });
}

async function main() {
  if (!CHROME) {
    console.error("No Chrome or Edge found. Install one, or set SITE_URL and run elsewhere.");
    process.exitCode = 1;
    return;
  }
  const only = process.argv.includes("--only")
    ? process.argv[process.argv.indexOf("--only") + 1]
    : null;
  const targets = only ? [only] : PAGES;

  rmSync(OUT, { recursive: true, force: true });
  mkdirSync(OUT, { recursive: true });

  let browser: Browser | undefined;
  const problems: Problem[] = [];
  try {
    browser = await puppeteer.launch({
      executablePath: CHROME,
      headless: true,
      args: ["--no-sandbox", "--disable-dev-shm-usage"],
    });

    for (const viewport of VIEWPORTS) {
      const page = await browser.newPage();
      await page.setViewport({ width: viewport.width, height: viewport.height });
      const consoleErrors: string[] = [];
      page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
      page.on("pageerror", (e) => consoleErrors.push(String(e)));

      for (const route of targets) {
        consoleErrors.length = 0;
        const url = `${BASE}${route}`;
        try {
          await page.goto(url, { waitUntil: "networkidle2", timeout: 60_000 });
        } catch {
          problems.push({ page: route, viewport: viewport.name, kind: "load-failed", detail: url });
          continue;
        }
        // Scroll the whole page before capturing. Reveal animations and the
        // count-up figures are driven by IntersectionObserver, and charts
        // initialise lazily on the same trigger — a full-page screenshot taken
        // without scrolling shows them all in their hidden starting state and
        // reports perfectly good sections as blank.
        await page.evaluate(async () => {
          const step = window.innerHeight * 0.8;
          for (let y = 0; y < document.body.scrollHeight; y += step) {
            window.scrollTo(0, y);
            await new Promise((r) => setTimeout(r, 220));
          }
          window.scrollTo(0, 0);
        });
        await new Promise((r) => setTimeout(r, 1200));

        // Windows rejects ? : * " < > | in filenames, and a route with a
        // query string carries at least one of them.
        const name =
          route.replace(/[^a-zA-Z0-9]+/g, "_").replace(/^_|_$/g, "") || "root";
        await page.screenshot({
          path: path.join(OUT, `${viewport.name}-${name}.png`) as `${string}.png`,
          fullPage: true,
        });

        for (const p of await inspect(page)) {
          problems.push({ page: route, viewport: viewport.name, ...p });
        }
        // Two responses are the designed answer, not faults: /auth/me is 401
        // for a visitor who is not signed in, and /simulations is 404 for a
        // report that had only one run. Reporting them on every page would
        // bury anything that actually broke.
        const realErrors = consoleErrors.filter(
          (e) => !/401 \(Unauthorized\)|404 \(Not Found\)/.test(e)
        );
        for (const err of realErrors.slice(0, 3)) {
          problems.push({ page: route, viewport: viewport.name, kind: "console-error", detail: err.slice(0, 120) });
        }
      }
      await page.close();
    }
  } finally {
    await browser?.close();
  }

  console.log(`\nCaptured ${targets.length * VIEWPORTS.length} screenshot(s) in ${OUT}\n`);
  if (problems.length === 0) {
    console.log("No layout problems found.");
    return;
  }
  console.log(`${problems.length} problem(s):\n`);
  for (const p of problems) {
    console.log(`  [${p.kind}] ${p.page} (${p.viewport})`);
    console.log(`      ${p.detail}`);
  }
  process.exitCode = 1;
}

main().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
