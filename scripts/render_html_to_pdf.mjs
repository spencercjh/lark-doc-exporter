import { chromium } from "playwright";
import { pathToFileURL } from "node:url";
import path from "node:path";

const [, , inputHtml, outputPdf] = process.argv;

if (!inputHtml || !outputPdf) {
  console.error("usage: node scripts/render_html_to_pdf.mjs <input.html> <output.pdf>");
  process.exit(1);
}

const browser = await chromium.launch({ headless: true });

try {
  const page = await browser.newPage();
  await page.goto(pathToFileURL(path.resolve(inputHtml)).href, { waitUntil: "load" });
  await page.emulateMedia({ media: "print" });
  await page.pdf({
    path: path.resolve(outputPdf),
    format: "A4",
    printBackground: true,
    preferCSSPageSize: true
  });
} finally {
  await browser.close();
}

