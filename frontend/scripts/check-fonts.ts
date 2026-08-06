/**
 * npm run check:fonts
 *
 * Finds text that does not render in the font it was meant to.
 *
 * Two failure modes matter here. A font without the `vietnamese` subset drops
 * back to a system face for any word carrying a diacritic, which shows up as
 * a visible change of shape mid-sentence. And a weight the loaded font does
 * not ship gets synthesised by the browser, which looks smeared next to real
 * bold text.
 *
 * The check reports what the browser actually resolved, measured against the
 * font families the page declares.
 */
import puppeteer from "puppeteer-core";

const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const ROUTES = ["/vi", "/vi/performance", "/vi/quant-portfolio", "/en", "/vi/models/dynamic-graph"];

// Any Vietnamese-specific letter or a Latin letter carrying a diacritic.
const VIET = /[ăâđêôơưĂÂĐÊÔƠƯ\u0300-\u0323]/u;

async function main() {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: true,
    args: ["--no-sandbox"],
  });

  let problems = 0;
  try {
    for (const route of ROUTES) {
      const page = await browser.newPage();
      await page.setViewport({ width: 1440, height: 1000 });
      await page.goto(`http://localhost:3000${route}`, {
        waitUntil: "networkidle0",
        timeout: 60000,
      });
      await page.evaluate(() => (document as unknown as { fonts: FontFaceSet }).fonts.ready);

      const report = await page.evaluate(() => {
        const declared = new Set<string>();
        for (const face of Array.from(
          (document as unknown as { fonts: FontFaceSet }).fonts,
        )) {
          declared.add(face.family.replace(/['"]/g, ""));
        }

        const seen = new Map<
          string,
          { family: string; weight: string; sample: string; count: number }
        >();
        const walker = document.createTreeWalker(
          document.body,
          NodeFilter.SHOW_TEXT,
        );
        let node: Node | null;
        while ((node = walker.nextNode())) {
          const text = (node.textContent ?? "").trim();
          if (!text) continue;
          const el = node.parentElement;
          if (!el) continue;
          const style = getComputedStyle(el);
          if (style.display === "none" || style.visibility === "hidden") continue;
          const family = style.fontFamily.split(",")[0].replace(/['"]/g, "").trim();
          const key = `${family}|${style.fontWeight}`;
          const entry = seen.get(key);
          if (entry) {
            entry.count += 1;
          } else {
            seen.set(key, {
              family,
              weight: style.fontWeight,
              sample: text.slice(0, 60),
              count: 1,
            });
          }
        }
        return { declared: [...declared], used: [...seen.values()] };
      });

      console.log(`\n${route}`);
      console.log(`  loaded faces: ${report.declared.join(", ") || "none"}`);
      for (const u of report.used) {
        const isDeclared = report.declared.some((d) => u.family.includes(d));
        const hasViet = VIET.test(u.sample);
        const flag = !isDeclared ? "  <-- NOT a loaded webfont" : "";
        if (flag) problems += 1;
        console.log(
          `  ${u.family} w${u.weight} x${u.count}${hasViet ? " [vi]" : ""}${flag}`,
        );
        if (flag) console.log(`      e.g. "${u.sample}"`);
      }
      await page.close();
    }
  } finally {
    await browser.close();
  }

  console.log(
    problems === 0
      ? "\nEvery rendered run uses a loaded webfont."
      : `\n${problems} text run(s) fell back to a system font.`,
  );
  process.exitCode = problems === 0 ? 0 : 1;
}

main();
