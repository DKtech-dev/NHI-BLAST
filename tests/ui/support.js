const path = require("node:path");
const { pathToFileURL } = require("node:url");

function reportUrl(name) {
  return pathToFileURL(path.join(process.env.NHB_UI_REPORT_DIR, name, "report.html")).href;
}

// Records uncaught page errors, console errors and every request the page makes.
function watch(page) {
  const seen = { errors: [], consoleErrors: [], requests: [], dialogs: [] };
  page.on("pageerror", (error) => seen.errors.push(String(error)));
  page.on("console", (message) => {
    if (message.type() === "error") seen.consoleErrors.push(message.text());
  });
  page.on("request", (request) => seen.requests.push(request.url()));
  page.on("dialog", (dialog) => { seen.dialogs.push(dialog.message()); dialog.dismiss(); });
  return seen;
}

async function open(page, name) {
  await page.goto(reportUrl(name));
  await page.waitForSelector("html:not(.booting)", { state: "attached" });
  await page.waitForSelector(".theme-switch");
}

const theme = (page) => page.evaluate(() => ({
  theme: document.documentElement.getAttribute("data-theme"),
  choice: document.documentElement.getAttribute("data-theme-choice"),
}));

module.exports = { open, reportUrl, theme, watch };
