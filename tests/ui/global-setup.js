// Generates the reports under test with the real CLI, into a temporary directory.
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const root = path.resolve(__dirname, "..", "..");
const fixtures = path.join(root, "tests", "fixtures");
const ACTION = "action:tj-actions/changed-files@v45";

function python() {
  if (process.env.NHB_PYTHON) return process.env.NHB_PYTHON;
  const venv = process.platform === "win32"
    ? path.join(root, ".venv", "Scripts", "python.exe")
    : path.join(root, ".venv", "bin", "python");
  return fs.existsSync(venv) ? venv : "python";
}

function scan(name, fixture, extra) {
  const out = path.join(process.env.NHB_UI_REPORT_DIR, name);
  fs.rmSync(out, { recursive: true, force: true });
  const args = [
    "-c", "from nhi_blast.cli.app import app; app()",
    "scan", path.join(fixtures, fixture), "--format", "html", "--out", out,
    "--repo-slug", "acme/app", ...extra,
  ];
  const result = spawnSync(python(), args, {
    cwd: root,
    encoding: "utf8",
    env: { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8" },
  });
  if (result.status !== 0) {
    throw new Error("nhi-blast scan failed for " + fixture + ": " + result.stdout + result.stderr);
  }
}

module.exports = async () => {
  process.env.NHB_UI_REPORT_DIR = process.env.NHB_UI_REPORT_DIR
    || fs.mkdtempSync(path.join(os.tmpdir(), "nhb-ui-reports-"));
  scan("fx07", "fx07-incident", ["--simulate-compromise", ACTION]);
  scan("fx14", "fx14-hostile", []);
  scan("fx01", "fx01-minimal", []);
};
