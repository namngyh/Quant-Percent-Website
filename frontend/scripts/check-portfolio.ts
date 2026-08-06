/**
 * npm run check:portfolio
 *
 * Drive the Quant Portfolio page the way a reader would: type a real
 * portfolio, submit, and capture what comes back.
 *
 * A passing API test does not prove the page works — the form has to reach
 * the endpoint through the proxy, the response has to satisfy the Zod
 * contract, and the result panel has to render. This checks all three.
 */
import puppeteer from "puppeteer-core";
import { writeFileSync } from "node:fs";

const CHROME =
  "C:/Program Files/Google/Chrome/Application/chrome.exe";
const OUT = "screenshots";

// Deliberately mixes VN30 names with mid-cap HOSE names, so the check fails
// if the portfolio tools ever regress to the VN30-only universe.
const HOLDINGS = [
  { symbol: "VCB", quantity: "2000", cost: "60000" },
  { symbol: "HSG", quantity: "5000", cost: "18000" },
  { symbol: "PNJ", quantity: "1000", cost: "95000" },
  { symbol: "DXG", quantity: "4000", cost: "15000" },
];

async function main() {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: true,
    args: ["--no-sandbox"],
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1440, height: 1200 });

    const consoleErrors: string[] = [];
    page.on("console", (m) => {
      if (m.type() === "error") consoleErrors.push(m.text().slice(0, 200));
    });

    await page.goto("http://localhost:3000/vi/quant-portfolio", {
      waitUntil: "networkidle0",
      timeout: 60000,
    });

    // Two rows exist by default; add the rest.
    const addButton = await page.$$("button");
    for (const b of addButton) {
      const text = await page.evaluate((el) => el.textContent ?? "", b);
      if (text.includes("Thêm cổ phiếu")) {
        await b.click();
        await b.click();
        break;
      }
    }

    const symbolInputs = await page.$$('input[placeholder="FPT"]');
    const qtyInputs = await page.$$('input[placeholder="1.000"]');
    const costInputs = await page.$$('input[placeholder="có thể bỏ trống"]');

    console.log(
      `rows found: symbol=${symbolInputs.length} qty=${qtyInputs.length} cost=${costInputs.length}`,
    );

    for (let i = 0; i < HOLDINGS.length; i++) {
      await symbolInputs[i].type(HOLDINGS[i].symbol);
      await qtyInputs[i].type(HOLDINGS[i].quantity);
      await costInputs[i].type(HOLDINGS[i].cost);
    }

    const cash = await page.$('input[placeholder="50.000.000"]');
    await cash?.type("80000000");

    const buttons = await page.$$("button");
    for (const b of buttons) {
      const text = await page.evaluate((el) => el.textContent ?? "", b);
      if (text.includes("Phân tích danh mục")) {
        await b.click();
        break;
      }
    }

    // Wait on structure, not on wording. Matching the heading text meant
    // every copy edit silently broke this check.
    await page.waitForFunction(
      () =>
        document.querySelector("#pf-overview") !== null ||
        document.querySelector('[role="alert"]') !== null,
      { timeout: 45000 },
    );

    // ECharts draws on the next frames after mount; capturing immediately
    // records an empty canvas and looks like a broken chart.
    await new Promise((r) => setTimeout(r, 2500));
    const canvases = await page.evaluate(
      () =>
        Array.from(document.querySelectorAll("canvas")).map(
          (c) => `${(c as HTMLCanvasElement).width}x${(c as HTMLCanvasElement).height}`,
        ),
    );
    console.log("canvases:", canvases.join(", ") || "none");

    const text = await page.evaluate(() => document.body.innerText);
    const ok = await page.evaluate(
      () => document.querySelector("#pf-overview") !== null,
    );
    console.log(ok ? "RESULT RENDERED" : "ERROR STATE");

    // Report the headline lines so the numbers can be eyeballed.
    for (const line of text.split("\n")) {
      if (
        /Giá trị danh mục|Lãi lỗ hiện tại|Mức rủi ro|So với VN-Index|tổng rủi ro|khoản đầu tư độc lập|Ngưỡng lỗ|tương đương/.test(
          line,
        )
      ) {
        console.log("  |", line.trim().slice(0, 160));
      }
    }

    await page.screenshot({ path: `${OUT}/portfolio-result.png`, fullPage: true });
    writeFileSync(`${OUT}/portfolio-result.txt`, text, "utf8");

    if (consoleErrors.length) {
      console.log(`console errors: ${consoleErrors.length}`);
      consoleErrors.slice(0, 5).forEach((e) => console.log("  !", e));
    } else {
      console.log("console errors: none");
    }

    process.exitCode = ok ? 0 : 1;
  } finally {
    await browser.close();
  }
}

main();
