// Builds the Vercel site into dist/: the watch dashboard (site/index.html), the full study (study.html) and
// site.json, a compact summary of data/ holding only what the dashboard shows. Run: node scripts/build-site.mjs
import { readFileSync, writeFileSync, mkdirSync, rmSync, copyFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const D = join(ROOT, "data");
const OUT = join(ROOT, "dist");
const SUPPLY = 420.69e9;
const FOCUS = "0xe14767042159e5bd2bf16f81a0fe387ab153fbb4";

const json = (p, fallback = null) => (existsSync(join(D, p)) ? JSON.parse(readFileSync(join(D, p), "utf8")) : fallback);
// Display names (same rule as scripts/groups.py): the focus wallet's group is "fbb4" (its owner's X name and the end of
// 0xe147…fbb4); every other group goes by the last four characters of the wallet it is named after ("Accumulator efdb",
// "Linked group 847d"). The watch files keep their original keys ("Your wallet's cluster", "Accumulator 0x53ee…efdb"),
// and older alerts say "Focus wallet's cluster"; the entity registry's own names win where it has the group.
const REG = Object.fromEntries(((json("entities.json", { entities: [] }) || {}).entities || []).filter((e) => e.wname).map((e) => [e.wname, e.name]));
const relabel = (s) =>
  typeof s !== "string" ? s : REG[s] ? REG[s]
    : s.replace(/\b(?:your|focus) wallet's cluster/gi, "fbb4").replace(/\b(Accumulator|Holding wallet|Sep-2025 wallet|Linked group) 0x[0-9a-fA-F]{4}…([0-9a-fA-F]{4,})/g, "$1 $2");
const pct = (t) => (100 * t) / SUPPLY;

const latest = json("alerts/latest.json", { summary: {}, alerts: [] });
const state = json("watch_state.json", { groups: {}, vaults: {} });
const stealth = json("stealth.json", { rows: [] });
const vaults = json("vaults90.json", {});
const float = json("float.json", {});
const market = json("market.json", { holders: {}, windows: [] });
const focusMembers = new Set((json("focus_cluster.json", { members: [] }).members || []).map((m) => m.a));
const cbg = new Set((json("coinbase_group.json", []) || []).map((r) => r.a));

const log = existsSync(join(D, "alerts/log.jsonl"))
  ? readFileSync(join(D, "alerts/log.jsonl"), "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l))
  : [];

const months = Object.keys(market.holders || {}).sort();
const hold = (m) => (m ? { month: m, n: market.holders[m][0], ge1m: market.holders[m][1], ge100m: market.holders[m][2], ge1b: market.holders[m][3] } : null);

const sum = latest.summary || {};
const site = {
  builtAt: new Date().toISOString(),
  asOf: sum.asOf || null,
  since: sum.since || null,
  price: sum.price ?? null,
  mcap: sum.mcap ?? null,
  pool: sum.pool ?? null,
  poolPct: sum.pool != null ? pct(sum.pool) : null,
  supply: SUPPLY,
  holders: hold(months.at(-1)),
  holders3m: hold(months.at(-4)),
  alerts: (latest.alerts || []).map((a) => ({ ...a, text: relabel(a.text), ...(a.group ? { group: relabel(a.group) } : {}) })),
  // Every past run that raised a medium or high alert, newest first.
  history: log
    .map((r) => ({
      asOf: r.summary?.asOf,
      since: r.summary?.since,
      alerts: (r.alerts || []).filter((a) => a.severity !== "info").map((a) => ({ severity: a.severity, text: relabel(a.text) })),
    }))
    .filter((r) => r.alerts.length)
    .reverse()
    .slice(0, 60),
  groups: Object.entries(state.groups || {})
    .map(([name, tok]) => ({ name: relabel(name), tok, pct: pct(tok) }))
    .sort((a, b) => b.tok - a.tok),
  accumulators: (stealth.rows || []).map((r) => {
    const ws = r.wallets || [];
    const kind = ws.includes(FOCUS) || ws.some((w) => focusMembers.has(w)) ? "focus" : ws.some((w) => cbg.has(w)) ? "coinbase" : "independent";
    return {
      owner: r.owner, kind, n: r.n, wallets: ws.slice(0, 80),
      net: r.net, netPct: r.pct, held: r.held, heldPct: r.heldPct, usd: r.usd,
      buys: r.buys, buyDays: r.buyDays, avgBuyUsd: r.avgBuyUsd, cexin: r.cexin, xin: r.xin, sold: r.sold,
      lastBuy: r.lastBuy || null, active: !!r.active, first: r.first, tags: (r.tags || []).map(relabel),
    };
  }),
  accumulatorsAsOf: stealth.asOf || null,
  vaults: Object.entries(vaults)
    .map(([a, v]) => ({
      a, feeders: v.feeders || [], tok: v.tok, usd: v.usd, first: v.first, last: v.last, sources: Object.keys(v.sources || {}),
      bal: v.bal ?? null, balPct: v.bal != null ? pct(v.bal) : null, toCex: v.toCex ?? 0, soldDex: v.soldDex ?? 0,
      other: Math.max(0, (v.sent ?? 0) - (v.toCex ?? 0) - (v.soldDex ?? 0)),
    }))
    // Still holding first (by size), then the ones whose coins have moved on.
    .sort((a, b) => (b.bal ?? 0) - (a.bal ?? 0) || b.tok - a.tok),
  relays: Object.keys(json("vaults90_relays.json", {}) || {}).length,   // bought-then-sold/passed-on, excluded
  float: Object.entries(float).map(([name, tok]) => ({ name: relabel(name), tok, pct: pct(tok) })),
  T: json("terminal.json"),                       // daily series, insider watch, watched groups, cluster, top holders
  E: json("entities.json"),                       // entity registry: cards, entity flow map, tripwires
  C: json("crowd.json"),                          // crowd behaviour (owner level)
  X: json("trades_check.json"),                   // exact trade pricing: coverage and the day-close error it removes
  H: json("ethside.json"),                        // ETH side: funding, ETH links, paid purchases, flows, other tokens
  U: json("engine/urpd-history.json"),            // weekly cost-basis distribution of held supply (engine)
  windows: (market.windows || []).map((w) => ({
    days: w.days, buyers: w.buyers, sellers: w.sellers, buyUsd: w.buyUsd, sellUsd: w.sellUsd, newBuyers: w.newBuyers, clusterNet: w.clusterNet,
  })),
};

rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });
writeFileSync(join(OUT, "site.json"), JSON.stringify(site));
copyFileSync(join(ROOT, "site/index.html"), join(OUT, "index.html"));
copyFileSync(join(ROOT, "site/logo.png"), join(OUT, "logo.png"));   // the token's logo (CoinGecko "GME (Ethereum)")
// Per-wallet histories: a separate file, fetched only when a wallet is opened.
if (existsSync(join(D, "wallets.json")))
  writeFileSync(join(OUT, "wallets.json"), relabel(readFileSync(join(D, "wallets.json"), "utf8")));

// The study was written as a page fragment (no doctype); give it a full document shell and a way back.
const study = readFileSync(join(ROOT, "report/gme-study.html"), "utf8")
  .replace(/<link rel="stylesheet" href="https:\/\/fonts\.googleapis\.com\/css2[^"]*">/, '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700;800&family=Geist+Mono:wght@400;500&display=swap">')
  + `<style>:root, :root[data-theme] { --f-display: "Geist", system-ui, sans-serif; --f-body: "Geist", system-ui, sans-serif; --f-mono: "Geist Mono", ui-monospace, monospace }
body { font-variant-numeric: tabular-nums } h1, h2, h3 { font-stretch: normal; letter-spacing: -.01em } * { border-radius: 0 !important }</style>`;
const back = `<a href="/" style="position:fixed;top:10px;right:max(16px,env(safe-area-inset-right,0px));z-index:9;font:500 12px/1 'Geist Mono',ui-monospace,monospace;letter-spacing:.1em;padding:9px 12px;border-radius:0;background:#15181b;color:#fff;text-decoration:none">← Terminal</a>`;
writeFileSync(
  join(OUT, "study.html"),
  `<!doctype html>\n<html lang="en">\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n<meta name="robots" content="noindex">\n${study}\n${back}\n</html>\n`,
);

console.log(
  `dist/: index.html, study.html, site.json (${(JSON.stringify(site).length / 1024).toFixed(0)} KB) · as of ${site.asOf} · ` +
    `${site.alerts.length} alerts · ${site.accumulators.length} accumulators · ${site.vaults.length} holding wallets`,
);
