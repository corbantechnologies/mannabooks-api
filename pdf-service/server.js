// MannaBooks PDF service: turns the HTML the API sends into an A4 PDF with Chromium (Playwright).
// POST /render  {"html": "<html>...", "landscape": false}  with header X-Render-Key: <PDF_SERVICE_KEY>  ->  application/pdf
// GET  /health  ->  ok
// The page is rendered with JavaScript and network off: everything it needs is inlined by the API.
const http = require("http");
const { chromium } = require("playwright");

const PORT = Number(process.env.PORT || 3100);
const KEY = process.env.PDF_SERVICE_KEY || "";
const MAX_BODY = 10 * 1024 * 1024;
let browser;

async function getBrowser() {
  if (!browser || !browser.isConnected()) browser = await chromium.launch({ args: ["--no-sandbox", "--disable-dev-shm-usage"] });
  return browser;
}

async function render(html, landscape) {
  const context = await (await getBrowser()).newContext({ javaScriptEnabled: false, offline: true });
  try {
    const page = await context.newPage();
    await page.setContent(html, { waitUntil: "load", timeout: 20000 });
    return await page.pdf({ format: "A4", landscape: Boolean(landscape), printBackground: true, margin: { top: "14mm", bottom: "16mm", left: "12mm", right: "12mm" } });
  } finally {
    await context.close();
  }
}

http.createServer((req, res) => {
  if (req.method === "GET" && req.url === "/health") return res.end("ok");
  if (req.method !== "POST" || req.url !== "/render") { res.statusCode = 404; return res.end(); }
  if (!KEY || req.headers["x-render-key"] !== KEY) { res.statusCode = 401; return res.end("unauthorised"); }
  let size = 0;
  const chunks = [];
  req.on("data", (c) => { size += c.length; if (size > MAX_BODY) { res.statusCode = 413; res.end(); req.destroy(); } else chunks.push(c); });
  req.on("end", async () => {
    try {
      const { html, landscape } = JSON.parse(Buffer.concat(chunks).toString("utf8"));
      if (typeof html !== "string" || !html) { res.statusCode = 400; return res.end("html is required"); }
      const pdf = await render(html, landscape);
      res.setHeader("Content-Type", "application/pdf");
      res.end(pdf);
    } catch (err) {
      console.error(err);
      res.statusCode = 500;
      res.end("render failed");
    }
  });
}).listen(PORT, () => console.log(`PDF service on ${PORT}`));
