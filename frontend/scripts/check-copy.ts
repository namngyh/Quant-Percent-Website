/**
 * npm run check:copy
 *
 * Catches the text faults a screenshot pass tends to miss.
 *
 * Four checks, all on the rendered page rather than the source:
 *  - a message key printed instead of its translation, which is what
 *    `next-intl` does when a key is absent;
 *  - an unsubstituted `{placeholder}` left in the output;
 *  - mojibake, the tell-tale `Ã`/`â€` sequences a bad encoding round-trip
 *    leaves behind in Vietnamese text;
 *  - the two locales drifting apart in which keys they define.
 */
import puppeteer from "puppeteer-core";
import { readFileSync } from "node:fs";

const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";

const ROUTES = [
  "/vi",
  "/vi/market-intelligence",
  "/vi/models",
  "/vi/models/dynamic-graph",
  "/vi/models/rarf-fhe",
  "/vi/models/msdp",
  "/vi/models/raemf-mc",
  "/vi/performance",
  "/vi/quant-portfolio",
  "/vi/about",
  "/vi/contact",
  "/vi/feedback",
  "/vi/join",
  "/vi/system-status",
  "/en",
  "/en/performance",
  "/en/quant-portfolio",
  "/en/feedback",
  "/en/join",
];

/** A key leaked into the page: dotted lowerCamel with no spaces. */
const LEAKED_KEY = /\b[a-z][a-zA-Z0-9]*(?:\.[a-z][a-zA-Z0-9]*){1,4}\b/g;
const PLACEHOLDER = /\{[a-zA-Z][a-zA-Z0-9_]*\}/g;
const MOJIBAKE = /(Ã[\u0080-\u00bf]|â€[\u0098-\u009d”“]|Æ°|áº|á»)/g;

/** Dotted strings that are legitimately visible text, not leaked keys. */
const ALLOWED = [
  /^\d/, // version numbers, dates
  /\.(com|vn|org|net|io|dev)$/i,
  /^(vi|en)\./,
  /^v\d/,
];

function flatten(obj: unknown, prefix = "", out: string[] = []): string[] {
  if (obj && typeof obj === "object" && !Array.isArray(obj)) {
    for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
      flatten(v, prefix ? `${prefix}.${k}` : k, out);
    }
  } else {
    out.push(prefix);
  }
  return out;
}

async function main() {
  // --- locale parity, before touching a browser -------------------------
  const vi = new Set(
    flatten(JSON.parse(readFileSync("messages/vi.json", "utf8"))),
  );
  const en = new Set(
    flatten(JSON.parse(readFileSync("messages/en.json", "utf8"))),
  );
  const onlyVi = [...vi].filter((k) => !en.has(k));
  const onlyEn = [...en].filter((k) => !vi.has(k));

  let problems = 0;
  if (onlyVi.length || onlyEn.length) {
    problems += onlyVi.length + onlyEn.length;
    console.log("locale key drift:");
    onlyVi.slice(0, 12).forEach((k) => console.log(`  vi only: ${k}`));
    onlyEn.slice(0, 12).forEach((k) => console.log(`  en only: ${k}`));
  } else {
    console.log(`locale parity: ${vi.size} keys in both`);
  }

  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: true,
    args: ["--no-sandbox"],
  });

  try {
    for (const route of ROUTES) {
      const page = await browser.newPage();
      await page.setViewport({ width: 1440, height: 1200 });
      try {
        await page.goto(`http://localhost:3000${route}`, {
          waitUntil: "networkidle0",
          timeout: 60000,
        });
      } catch {
        console.log(`${route}\n  LOAD FAILED`);
        problems += 1;
        await page.close();
        continue;
      }
      // Data-driven panels finish after the network settles.
      await new Promise((r) => setTimeout(r, 1800));
      const text = await page.evaluate(() => document.body.innerText);

      const found: string[] = [];

      for (const m of text.match(LEAKED_KEY) ?? []) {
        if (ALLOWED.some((re) => re.test(m))) continue;
        // A real translation key exists in the message files.
        if (vi.has(m) || en.has(m) || [...vi].some((k) => k.endsWith(`.${m}`))) {
          found.push(`untranslated key: ${m}`);
        }
      }
      for (const m of text.match(PLACEHOLDER) ?? []) {
        found.push(`unsubstituted placeholder: ${m}`);
      }
      for (const m of text.match(MOJIBAKE) ?? []) {
        found.push(`mojibake: ${JSON.stringify(m)}`);
      }

      const unique = [...new Set(found)];
      if (unique.length) {
        problems += unique.length;
        console.log(`${route}`);
        unique.slice(0, 8).forEach((f) => console.log(`  ${f}`));
      }
      await page.close();
    }
  } finally {
    await browser.close();
  }

  console.log(
    problems === 0
      ? "\nNo copy faults found."
      : `\n${problems} copy fault(s) found.`,
  );
  process.exitCode = problems === 0 ? 0 : 1;
}

main();
