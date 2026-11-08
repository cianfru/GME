// Runs the Python unit tests (test/test_*.py) as part of `npm test`, so one command checks both languages.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
test("python unit tests", () => {
  const r = spawnSync("python3", ["-m", "unittest", "discover", "-s", "test", "-p", "test_*.py"], { cwd: root, encoding: "utf8" });
  assert.equal(r.status, 0, r.stderr || r.stdout);
});
