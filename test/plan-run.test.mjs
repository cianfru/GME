import { test } from "node:test";
import assert from "node:assert/strict";
import { decide, fromApi } from "../scripts/plan-run.mjs";

const at = (s) => new Date(s);
const full = (date) => ({ message: "data: daily refresh " + date.slice(0, 10), date });
const light = (date) => ({ message: `data: refresh ${date.slice(0, 16)} UTC (light)`, date });

test("first tick after 06:00 UTC runs the full refresh when today has none", () => {
  const commits = [light("2026-11-08T04:20:00Z"), full("2026-11-07T13:18:00Z")];
  assert.equal(decide({ now: at("2026-11-08T06:41:00Z"), commits, busy: false }).mode, "full");
});

test("no second full run on the same day, even if the first was manual", () => {
  const commits = [full("2026-11-08T10:03:00Z")];
  assert.equal(decide({ now: at("2026-11-08T11:41:00Z"), commits, busy: false }).mode, "skip");
  assert.equal(decide({ now: at("2026-11-08T14:41:00Z"), commits, busy: false }).mode, "light");
});

test("before 06:00 UTC only light runs, and only when the data is old enough", () => {
  const commits = [light("2026-11-08T01:45:00Z"), full("2026-11-07T07:00:00Z")];
  assert.equal(decide({ now: at("2026-11-08T03:41:00Z"), commits, busy: false }).mode, "skip");
  assert.equal(decide({ now: at("2026-11-08T05:41:00Z"), commits, busy: false }).mode, "light");
});

test("a dropped tick is covered by the next one", () => {
  const commits = [full("2026-11-08T06:45:00Z")];
  // 10:41 dropped by GitHub; 11:41 still finds the data old enough
  assert.equal(decide({ now: at("2026-11-08T11:41:00Z"), commits, busy: false }).mode, "light");
});

test("skips while another run is going, and ignores commits that are not data refreshes", () => {
  const commits = [{ message: "Visualizer: something", date: "2026-11-08T11:00:00Z" }, { message: "data: BigQuery study (eth_flows_delta)", date: "2026-11-08T10:00:00Z" }, light("2026-11-08T05:00:00Z"), full("2026-11-08T06:50:00Z")];
  assert.equal(decide({ now: at("2026-11-08T10:41:00Z"), commits, busy: true }).mode, "skip");
  assert.equal(decide({ now: at("2026-11-08T10:41:00Z"), commits, busy: false }).mode, "light");
});

test("an empty history runs a full refresh after 06:00 and a light one before", () => {
  assert.equal(decide({ now: at("2026-11-08T07:41:00Z"), commits: [], busy: false }).mode, "full");
  assert.equal(decide({ now: at("2026-11-08T02:41:00Z"), commits: [], busy: false }).mode, "light");
});

test("reads the GitHub API shapes", () => {
  const c = [{ commit: { message: "data: daily refresh 2026-11-08\n\nbody", committer: { date: "2026-11-08T07:00:00Z" } } }];
  const r = { workflow_runs: [{ id: 5, status: "in_progress" }, { id: 4, status: "completed" }] };
  assert.deepEqual(fromApi(c, r, 5), { commits: [{ message: "data: daily refresh 2026-11-08", date: "2026-11-08T07:00:00Z" }], busy: false });
  assert.equal(fromApi(c, { workflow_runs: [{ id: 4, status: "queued" }] }, 5).busy, true);
});

test("only an older run (or a manual one) counts as busy, so ticks released together do not all skip", () => {
  const c = [];
  assert.equal(fromApi(c, { workflow_runs: [{ id: 6, status: "in_progress", event: "schedule" }] }, 5).busy, false);
  assert.equal(fromApi(c, { workflow_runs: [{ id: 4, status: "in_progress", event: "schedule" }] }, 5).busy, true);
  assert.equal(fromApi(c, { workflow_runs: [{ id: 6, status: "in_progress", event: "workflow_dispatch" }] }, 5).busy, true);
});
