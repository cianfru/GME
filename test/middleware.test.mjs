import { test } from "node:test";
import assert from "node:assert/strict";
import middleware, { checkAuth } from "../middleware.js";

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

test("middleware lets everything through when no password is configured", () => {
  delete process.env.SITE_PASSWORD;
  assert.equal(middleware(req(null)).headers.get("x-middleware-next"), "1");
});

test("middleware asks for the password (401) and lets the right one through", () => {
  process.env.SITE_PASSWORD = "s3cret";
  const no = middleware(req(null));
  assert.equal(no.status, 401);
  assert.match(no.headers.get("www-authenticate"), /^Basic /);
  assert.equal(middleware(req(basic("gme", "wrong"))).status, 401);
  const ok = middleware(req(basic("gme", "s3cret")));
  assert.equal(ok.headers.get("x-middleware-next"), "1");
  delete process.env.SITE_PASSWORD;
});
