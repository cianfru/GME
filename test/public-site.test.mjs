// The public bundle must never carry the owner desk's attribution: checked on a synthetic site and, when a build
// exists, on the real dist/.
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { publicSite, publicIndexFile, privateSets, mentionsPrivate } from "../scripts/public-site.mjs";

const F = "0xe14767042159e5bd2bf16f81a0fe387ab153fbb4", A = "0x" + "a".repeat(40), B = "0x" + "b".repeat(40), C = "0x" + "c".repeat(40), W = "0x" + "d".repeat(40);
const site = {
  supply: 100, float: [{ name: "Burned", tok: 2, pct: 2 }, { name: "fbb4 (70)", tok: 15, pct: 15 }, { name: "Its looser extension (123 more)", tok: 5, pct: 5 }, { name: "Other multi-wallet groups", tok: 10, pct: 10 }],
  alerts: [{ severity: "high", text: "fbb4: sent 1B to an exchange" }, { severity: "info", text: "Accumulator cccc: bought 1B" }, { severity: "info", text: "Linked group aaaa: sold" }],
  history: [], groups: [{ name: "fbb4" }, { name: "Accumulator cccc" }],
  accumulators: [{ kind: "focus", wallets: [F] }, { kind: "independent", wallets: [C], tags: [] }, { kind: "independent", wallets: [A], tags: [] }],
  vaults: [{ a: C, feeders: [] }, { a: B, feeders: [] }], windows: [{ days: 30, buyers: 1, clusterNet: 5 }],
  T: { daily: { d: ["x"], price: [1], cluster: [9], focus: [9], clusterToCexUsd: [1] }, insider: { status: "HOLDING" }, cluster: {}, mon: {}, top: [{ a: F, group: "fbb4" }, { a: C, group: "Accumulator cccc" }],
    moves: [{ fg: "Linked group aaaa", tg: null }], groups: [{ name: "fbb4" }, { name: "Accumulator cccc" }] },
  E: { entities: [{ id: "e1", kind: "focus", name: "fbb4", members: [F, B], attached: [] }, { id: "e2", kind: "linked", name: "Linked group aaaa", members: [A], attached: [], near: { focus: {} } },
    { id: "e3", kind: "watched", name: "Accumulator cccc", members: [C], attached: [] }], edges: [[]], alerts: [], events: [{ text: "fbb4 is forming", entity: "e1" }, { text: "Accumulator cccc is forming", entity: "e3" }] },
  NET: { networks: [{ id: "net-fbb4", name: "fbb4 network", groups: ["e1", "e2"], members: [F, B, A], map: { wallets: [[W, 0, 0, 1]], groups: [{ name: "Lone web wallets", kind: "lone" }] } }] },
  C: { smart: { rows: [{ eid: "e2", name: "Linked group aaaa" }, { eid: "e3", name: "Accumulator cccc" }, { u: W, name: null }] } }, H: { any: 1 }, MV: { windows: {} },
};

test("private sets cover the focus entity, the network's groups and the linked web", () => {
  const P = privateSets(site);
  assert.deepEqual([...P.ids].sort(), ["e1", "e2", "net-fbb4"]);
  for (const a of [F, B, A, W]) assert.ok(P.wallets.has(a));
  assert.ok(!P.wallets.has(C));
});

test("an address ending in fbb4 is not a name; the name is", () => {
  assert.equal(mentionsPrivate("0xe147…fbb4 bought", new Set()), false);
  assert.equal(mentionsPrivate(F, new Set()), false);
  assert.equal(mentionsPrivate("fbb4 bought", new Set()), true);
  assert.equal(mentionsPrivate("Linked group aaaa sold", new Set(["Linked group aaaa"])), true);
});

test("the public bundle drops every attribution and keeps the rest", () => {
  const p = publicSite(site, { windows: {} }), s = JSON.stringify(p);
  assert.ok(!/(?<![0-9a-fA-Fx…])fbb4/.test(s), "no fbb4 name"); assert.ok(!/cluster|network|Linked group aaaa/i.test(s));
  for (const k of ["NET", "H"]) assert.equal(p[k], undefined);
  for (const k of ["insider", "cluster", "mon"]) assert.equal(p.T[k], undefined);
  assert.deepEqual(Object.keys(p.T.daily), ["d", "price"]);
  assert.deepEqual(p.E.entities.map((e) => e.id), ["e3"]);
  assert.deepEqual(p.accumulators.map((a) => a.wallets[0]), [C]);
  assert.deepEqual(p.vaults.map((v) => v.a), [C]);
  assert.deepEqual(p.C.smart.rows.map((r) => r.eid), ["e3"]);
  assert.equal(p.float.find((f) => f.name === "Other multi-wallet groups").tok, 30);          // 15 + 5 folded into 10
  assert.equal(p.float.reduce((a, f) => a + f.tok, 0), 32);                                    // nothing lost
  assert.equal(p.T.top[0].group, null); assert.equal(p.T.top[1].group, "Accumulator cccc");
  assert.equal(p.E.events.length, 1);
});

test("the public wallet index keeps transfers and drops attribution and linking evidence", () => {
  const P = privateSets(site);
  const rec = { t: [[1, 2]], pl: {}, ent: ["e1", "m"], grp: { gid: "w1", web: true }, tags: { watch: "x", acc: {}, smart: {} }, seed: [A], seeded: [[B]], shared: { x: [B] }, ethl: [[B]], eth: {} };
  const out = publicIndexFile("abc", { [F]: rec, [C]: { ...rec, ent: ["e3", "m"], grp: { gid: "g1" }, tags: { acc: {} } } }, P);
  assert.deepEqual(Object.keys(out[F]).sort(), ["pl", "t", "tags"]); assert.deepEqual(out[F].tags, { smart: {} });
  assert.deepEqual(out[C].ent, ["e3", "m"]); assert.deepEqual(out[C].tags, { acc: {} }); assert.equal(out[C].seed, undefined);
  assert.equal(publicIndexFile("_ties", [], P), null);
  assert.deepEqual(Object.keys(publicIndexFile("_groups", { w1: { kind: "web", members: [] }, g1: { kind: "group", ents: ["e1"], members: [] }, g2: { kind: "group", ents: [], members: [[C, 1]] } }, P)), ["g2"]);
});

test("the built public files carry no private name or member list (when dist/ exists)", { skip: !existsSync("dist/desk/site.json") }, () => {
  const full = JSON.parse(readFileSync("dist/desk/site.json", "utf8")), P = privateSets(full);
  const pub = readFileSync("dist/site.json", "utf8");
  assert.ok(!/(?<![0-9a-fA-Fx…])fbb4/.test(pub)); assert.ok(!/"(NET|H|insider|cluster|mon)":/.test(pub));
  for (const n of P.names) assert.ok(!pub.includes(`"${n}"`), n);
  for (const f of ["wallets.json", "graph.json", "graph_tx.json", "study.html"]) assert.ok(!existsSync("dist/" + f), f + " must be desk-only");
  if (existsSync("dist/w")) {
    assert.ok(!existsSync("dist/w/_ties.json"));
    const priv = [...P.wallets][0], shard = `dist/w/${priv.slice(2, 5)}.json`;
    if (existsSync(shard)) { const r = JSON.parse(readFileSync(shard, "utf8"))[priv]; if (r) for (const k of ["ent", "grp", "seed", "seeded", "shared", "ethl"]) assert.equal(r[k], undefined, k); }
    assert.ok(readdirSync("dist/w").length > 4000);
  }
});

import { splitPage } from "../scripts/public-site.mjs";
test("splitPage: the public page loses owner code and gets stubs; the desk page keeps it", () => {
  const src = ["<script>", "const A = 1;", "//@desk", "function secret(x) {", "  return 'fbb4';", "}", "const NAMES = { a: 1 };", "const f2 = (x) => x;", "//@end", "//@pub", "const NAMES2 = [];", "//@end", "const t = `<p>ok</p><!--@desk--><p>owner</p><!--@end-->`;", "</script>"].join("\n");
  const { pub, desk } = splitPage(src);
  assert.ok(!/fbb4|owner|@desk|@end/.test(pub));
  assert.match(pub, /function secret\(\) \{ return ""; \}/); assert.match(pub, /const NAMES = \{\};/); assert.match(pub, /const f2 = \(\) => "";/); assert.match(pub, /const NAMES2 = \[\];/);
  assert.match(desk, /return 'fbb4'/); assert.match(desk, /<p>owner<\/p>/); assert.ok(!/NAMES2|@desk|@pub/.test(desk));
  assert.throws(() => splitPage("//@desk\nx"));
});
test("the built public page has no private name; the desk page is behind /desk/", () => {
  if (!existsSync(new URL("../dist/index.html", import.meta.url))) return;
  assert.ok(!/fbb4/i.test(readFileSync(new URL("../dist/index.html", import.meta.url), "utf8")));
  assert.ok(existsSync(new URL("../dist/desk/index.html", import.meta.url)));
});
