// Decides what an hourly tick of daily.yml does: a full run, a light run, or nothing.
//
// Why: GitHub runs scheduled workflows late or drops them under load. Measured 2026-10-31 → 11-08 on this repo, the
// 06:23 UTC full run started between 12:46 and 14:43 UTC every day, and the 4-hourly light runs were often dropped
// (3 of 6 on 6 Nov, with an 11h20m gap). So instead of trusting one exact time, the workflow checks every hour and
// this script decides from what actually happened, read from the data commits:
//   full  — once a day: the first tick after 06:00 UTC on a day with no full run since 06:00 UTC;
//   light — when the newest data commit (full or light) is at least LIGHT_EVERY_MIN old;
//   skip  — otherwise, or when another run of the workflow is still going (it would queue behind it anyway).
// A dropped tick is covered by the next one, so the data is never more than about LIGHT_EVERY_MIN + 1 h old.
//
// CLI: node scripts/plan-run.mjs commits.json runs.json <this run id>   → prints "mode=…" (for $GITHUB_OUTPUT)
//   commits.json = GET /repos/{repo}/commits?path=data/terminal.json   (every data commit touches terminal.json)
//   runs.json    = GET /repos/{repo}/actions/workflows/daily.yml/runs
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

export const FULL_HOUR_UTC = 6;
export const LIGHT_EVERY_MIN = 225; // 3h45m: with hourly ticks, a light run lands about every 4 hours

const isFull = (msg) => /^data: daily refresh/.test(msg);
const isData = (msg) => /^data: (daily refresh|refresh )/.test(msg);

export function decide({ now, commits, busy }) {
  if (busy) return { mode: "skip", why: "another run of this workflow is still going" };
  const data = commits.filter((c) => isData(c.message)).map((c) => ({ ...c, t: Date.parse(c.date) })).sort((a, b) => b.t - a.t);
  const lastFull = data.find((c) => isFull(c.message));
  const slot = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), FULL_HOUR_UTC);
  if (now.getTime() >= slot && (!lastFull || lastFull.t < slot))
    return { mode: "full", why: lastFull ? `last full run ${lastFull.date}, before today's ${FULL_HOUR_UTC}:00 UTC` : "no full run found" };
  const last = data[0];
  const age = last ? (now.getTime() - last.t) / 60000 : Infinity;
  if (age >= LIGHT_EVERY_MIN) return { mode: "light", why: last ? `newest data is ${Math.round(age)} min old` : "no data commit found" };
  return { mode: "skip", why: `newest data is ${Math.round(age)} min old (light runs every ${LIGHT_EVERY_MIN} min)` };
}

// GitHub API shapes → decide()'s inputs
export const fromApi = (commitsJson, runsJson, runId) => ({
  commits: commitsJson.map((c) => ({ message: (c.commit?.message || "").split("\n")[0], date: c.commit?.committer?.date || c.commit?.author?.date })),
  busy: (runsJson.workflow_runs || []).some((r) => String(r.id) !== String(runId) && r.status !== "completed"),
});

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const [commitsFile, runsFile, runId] = process.argv.slice(2);
  const input = fromApi(JSON.parse(readFileSync(commitsFile, "utf8")), JSON.parse(readFileSync(runsFile, "utf8")), runId);
  const d = decide({ now: new Date(), ...input });
  console.error(`plan: ${d.mode} (${d.why})`);
  console.log(`mode=${d.mode}`);
}
