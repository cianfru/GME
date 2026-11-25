import { test } from "node:test";
import assert from "node:assert/strict";
import middleware, { checkAuth, deskToken, isDesk } from "../middleware.js";

const basic = (u, p) => "Basic " + btoa(`${u}:${p}`);
const req = (auth) => new Request("https://example.com/site.json", { headers: auth ? { authorization: auth } : {} });

test("checkAuth accepts any username with the right password, including passwords with colons", () => {
  assert.equal(checkAuth(basic("gme", "s3cret"), "s3cret"), true);
  assert.equal(checkAuth(basic("", "s3cret"), "s3cret"), true);
  assert.equal(checkAuth(basic("x", "a:b:c"), "a:b:c"), true);
});

test("checkAuth rejects wrong, partial, longer, missing and malformed credentials", () => {
  for (const h of [basic("gme", "s3cre"), basic("gme", "s3cret!"), basic("gme", "S3CRET"), null, "", "Bearer abc", "Basic %%%", "Basic " + btoa("nocolon")])
    assert.equal(checkAuth(h, "s3cret"), false, String(h));
  assert.equal(checkAuth(basic("gme", ""), ""), false);
});

test("middleware lets everything through when no password is configured", async () => {
  delete process.env.SITE_PASSWORD; delete process.env.DESK_PASSWORD;
  assert.equal((await middleware(req(null))).headers.get("x-middleware-next"), "1");
});

test("middleware asks for the site password (401) and lets the right one through", async () => {
  process.env.SITE_PASSWORD = "s3cret";
  const no = await middleware(req(null));
  assert.equal(no.status, 401);
  assert.match(no.headers.get("www-authenticate"), /^Basic /);
  assert.equal((await middleware(req(basic("gme", "wrong")))).status, 401);
  assert.equal((await middleware(req(basic("gme", "s3cret")))).headers.get("x-middleware-next"), "1");
  delete process.env.SITE_PASSWORD;
});

const dreq = (path, h = {}) => new Request("https://example.com" + path, { headers: h });

test("the desk does not exist without DESK_PASSWORD (fails closed)", async () => {
  delete process.env.DESK_PASSWORD;
  for (const p of ["/desk/site.json", "/desk", "/desk/w/abc.json", "/desk/unlock"]) assert.equal((await middleware(dreq(p))).status, 404, p);
  assert.equal(isDesk("/desktop.json"), false); assert.equal(isDesk("/site.json"), false);
});

test("the desk needs its own password; the right one sets a cookie that then opens it", async () => {
  process.env.DESK_PASSWORD = "owner-pw";
  assert.equal((await middleware(dreq("/desk/site.json"))).status, 401);
  assert.equal((await middleware(dreq("/desk/site.json", { authorization: basic("x", "nope") }))).status, 401);
  const ok = await middleware(dreq("/desk/unlock", { authorization: basic("x", "owner-pw") }));
  assert.equal(ok.headers.get("x-middleware-next"), "1");
  const token = await deskToken("owner-pw");
  assert.match(ok.headers.get("set-cookie") || ok.headers.get("x-middleware-set-cookie") || "", new RegExp("gme_desk=" + token + ".*HttpOnly.*Secure"));
  assert.equal((await middleware(dreq("/desk/site.json", { cookie: "a=b; gme_desk=" + token }))).headers.get("x-middleware-next"), "1");
  assert.equal((await middleware(dreq("/desk/site.json", { cookie: "gme_desk=" + token.slice(0, -1) + "0" }))).status, 401);
  // the public site stays open with only the desk locked
  assert.equal((await middleware(dreq("/site.json"))).headers.get("x-middleware-next"), "1");
  delete process.env.DESK_PASSWORD;
});
