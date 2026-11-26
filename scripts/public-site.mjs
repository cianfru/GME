// The public bundle. The site is two products from one pipeline:
//   - the PUBLIC terminal (dist/site.json, dist/w/, dist/pnl.json): market-wide facts, accumulators, wallet lookup;
//   - the OWNER DESK (dist/desk/…, behind DESK_PASSWORD in middleware.js): everything, including the fbb4 network.
// This module decides what the public bundle may contain. The rule: nothing that attributes wallets to fbb4 or to
// the groups of its network, and nothing derived from that attribution (insider watch, cluster series, the network,
// the ETH side, ties, the entity flow map). Wallet-level chain facts stay public. test/public-site.test.mjs fails the
// build's tests if a private name or key ever reaches the public bundle.

/** What is private: the focus entity, every group of an owner-reviewed network, and every wallet of those groups
 *  plus the rest of the linked web they came from (the network map's wallets). */
export function privateSets(site) {
  const ents = (site.E && site.E.entities) || [], nets = (site.NET && site.NET.networks) || [];
  const ids = new Set(), wallets = new Set(), names = new Set();
  for (const e of ents) if (e.kind === "focus") ids.add(e.id);
  for (const n of nets) {
    ids.add(n.id); names.add(n.name);
    for (const g of n.groups || []) ids.add(g);
    for (const a of n.members || []) wallets.add(a);
    for (const w of (n.map && n.map.wallets) || []) wallets.add(w[0]);
    for (const g of (n.map && n.map.groups) || []) if (g.kind !== "net") names.add(g.name);
  }
  for (const e of ents) {
    const all = [...(e.members || []), ...((e.attached || []).map((x) => x.a))];
    if (ids.has(e.id) || all.some((a) => wallets.has(a))) { ids.add(e.id); names.add(e.name); if (e.wname) names.add(e.wname); for (const a of all) wallets.add(a); }
  }
  names.add("fbb4");
  return { ids, wallets, names };
}

/** True when a text names a private group ("fbb4" as a word, "Linked group a8c8", "cluster"). An address that merely
 *  ends in fbb4 (0xe147…fbb4) is a chain fact, not a name. */
export function mentionsPrivate(text, names) {
  if (typeof text !== "string") return false;
  if (/(?<![0-9a-fA-Fx…])fbb4\b/.test(text) || /\b(focus|your) wallet|\bcluster\b|\bnetwork\b/i.test(text)) return true;
  for (const n of names) if (n && n !== "fbb4" && text.includes(n)) return true;
  return false;
}

const PRIVATE_DAILY = ["focus", "cluster", "clusterToCex", "clusterToCexUsd", "clusterDexBuy", "clusterDexSell", "clusterFromCex", "focusDexSell"];

export function publicSite(site, moversPublic) {
  const P = privateSets(site), bad = (t) => mentionsPrivate(t, P.names);
  const T = site.T || {};
  const daily = Object.fromEntries(Object.entries(T.daily || {}).filter(([k]) => !PRIVATE_DAILY.includes(k)));
  // supply by holder type: the attributed rows fold into one "other wallets" row
  const float = []; let folded = 0;
  for (const f of site.float || []) { if (bad(f.name) || /extension/i.test(f.name)) folded += f.tok; else float.push(f); }
  if (folded) { const i = float.findIndex((f) => /Other multi-wallet groups/.test(f.name)); const row = { name: "Other multi-wallet groups", tok: folded, pct: (100 * folded) / site.supply };
    if (i >= 0) { float[i] = { ...float[i], tok: float[i].tok + folded, pct: float[i].pct + row.pct }; } else float.push(row); }
  const ents = ((site.E && site.E.entities) || []).filter((e) => !P.ids.has(e.id)).map((e) => ({ ...e, near: null, direct: null }));
  const keep = new Set(ents.map((e) => e.id));
  const E = site.E ? { asOf: site.E.asOf, since: site.E.since, spot: site.E.spot, windows: site.E.windows, channels: site.E.channels, entities: ents, edges: null,
    alerts: (site.E.alerts || []).filter((a) => !bad(a.text) && (!a.entity || keep.has(a.entity))),
    events: (site.E.events || []).filter((a) => !bad(a.text) && (!a.entity || keep.has(a.entity))) } : null;
  const C = site.C ? { ...site.C, smart: site.C.smart ? { ...site.C.smart, rows: (site.C.smart.rows || []).filter((r) => !(r.eid && P.ids.has(r.eid)) && !(r.u && P.wallets.has(r.u)) && !bad(r.name)) } : site.C.smart } : null;
  return {
    public: true,
    builtAt: site.builtAt, asOf: site.asOf, since: site.since, price: site.price, mcap: site.mcap, pool: site.pool, poolPct: site.poolPct, supply: site.supply,
    holders: site.holders, holders3m: site.holders3m,
    alerts: (site.alerts || []).filter((a) => !bad(a.text) && !bad(a.group)),
    history: (site.history || []).map((r) => ({ ...r, alerts: r.alerts.filter((a) => !bad(a.text)) })).filter((r) => r.alerts.length),
    groups: (site.groups || []).filter((g) => !bad(g.name)),
    accumulators: (site.accumulators || []).filter((a) => a.kind !== "focus" && !(a.wallets || []).some((w) => P.wallets.has(w)) && !(a.tags || []).some(bad)),
    accumulatorsAsOf: site.accumulatorsAsOf,
    vaults: (site.vaults || []).filter((v) => !P.wallets.has(v.a) && !(v.feeders || []).some((w) => P.wallets.has(w))),
    relays: site.relays, float,
    T: { asOf: T.asOf, index: T.index, daily, pool: T.pool, urpd: T.urpd, cohorts: T.cohorts, runs: T.runs,
      moves: (T.moves || []).map((m) => ({ ...m, fg: bad(m.fg) ? null : m.fg, tg: bad(m.tg) ? null : m.tg })),
      top: (T.top || []).map((t) => ({ ...t, group: bad(t.group) ? null : t.group })),
      groups: (T.groups || []).filter((g) => !bad(g.name)) },
    E, C, MV: moversPublic || null, X: site.X,
    windows: (site.windows || []).map(({ clusterNet, ...w }) => w),
  };
}

/** One line of the wallet index for the public copy, or null to drop it. Wallet records keep their transfers, P&L and
 *  watch tags; the evidence that ties wallets together (group membership of private groups, who seeded whom, shared
 *  deposit addresses, ETH links) is the desk's. */
export function publicIndexFile(key, d, P) {
  if (key === "_ties") return null;
  if (key === "_groups") return Object.fromEntries(Object.entries(d).filter(([, g]) => g.kind !== "web" && !(g.ents || []).some((id) => P.ids.has(id)) && !(g.members || []).some(([a]) => P.wallets.has(a))));
  if (key[0] === "_") return d;
  const out = {};
  for (const [a, r] of Object.entries(d)) {
    const { seed, seeded, seededMore, shared, ethl, eth, ...rec } = r;
    if (P.wallets.has(a)) { delete rec.ent; delete rec.grp; if (rec.tags) { const { watch, acc, vault, ...t } = rec.tags; rec.tags = t; } }
    else {
      if (rec.ent && P.ids.has(rec.ent[0])) delete rec.ent;
      if (rec.grp && (rec.grp.web || rec.grp.flagged)) delete rec.grp;
    }
    out[a] = rec;
  }
  return out;
}

/** The page is one source (site/index.html) with the owner's code between marker lines: `//@desk` … `//@end` (and
 *  `<!--@desk-->` … `<!--@end-->` inside templates); `//@pub` … `//@end` is what the public page gets instead.
 *  The desk page keeps the owner code; the public page loses it, and every top-level name declared there becomes an
 *  empty stub so a stray reference can never throw. */
export function splitPage(src) {
  const desk = [], pub = [], stubs = [];
  let mode = null;
  for (const line of src.split("\n")) {
    const t = line.trim();
    if (t === "//@desk" || t === "//@pub") { if (mode) throw new Error("nested marker: " + line); mode = t.slice(3); continue; }
    if (t === "//@end") { if (!mode) throw new Error("stray //@end"); mode = null; continue; }
    if (mode !== "pub") desk.push(line);
    if (mode !== "desk") pub.push(line);
    else for (const m of line.matchAll(/^(?:async function|function) ([A-Za-z_$][\w$]*)|^(?:const|let) ([A-Za-z_$][\w$]*)/g)) {
      if (m[1]) stubs.push(`function ${m[1]}() { return ""; }`);
      else stubs.push(/^(?:const|let) [\w$]+ = (?:async )?(?:\([^)]*\)|[\w$]+) =>/.test(line) ? `const ${m[2]} = () => "";` : `const ${m[2]} = {};`);
      for (const x of line.matchAll(/, ([A-Za-z_$][\w$]*) = /g)) if (/^(?:const|let) /.test(line) && !line.includes("=>")) stubs.push(`const ${x[1]} = {};`);
    }
  }
  if (mode) throw new Error("unclosed marker");
  const inline = /<!--@desk-->[\s\S]*?<!--@end-->/g;
  let pubHtml = pub.join("\n").replace(inline, "");
  const declared = new Set();
  const uniq = stubs.filter((x) => { const n = x.match(/(?:function|const) ([\w$]+)/)[1]; if (declared.has(n) || new RegExp("^(?:async function|function|const|let) " + n.replace(/\$/g, "\\$") + "\\b", "m").test(pubHtml)) return false; declared.add(n); return true; });
  const at = pubHtml.lastIndexOf("</script>");
  pubHtml = pubHtml.slice(0, at) + uniq.join("\n") + "\n" + pubHtml.slice(at);
  return { desk: desk.join("\n").replace(/<!--@(desk|end)-->/g, ""), pub: pubHtml };
}

/** The Explorer's transfer graph for the public page: the same wallets and transfers (chain facts), but the private
 *  groups are not groups there: their wallets are plain wallets and their names are gone. */
export function publicGraph(g, P) {
  const map = new Map(), entities = [];
  g.entities.forEach((e, i) => { if (P.ids.has(e[0]) || mentionsPrivate(e[1], P.names)) return; map.set(i, entities.length); entities.push(e); });
  const nodes = g.nodes.map((n) => { const m = n.slice(); m[3] = map.has(n[3]) ? map.get(n[3]) : -1; if (mentionsPrivate(m[2], P.names)) m[2] = ""; return m; });
  return { ...g, entities, nodes };
}
