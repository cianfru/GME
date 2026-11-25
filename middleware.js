// Two gates, both HTTP Basic auth (any username):
//   - the OWNER DESK: every path under /desk/ (the full data bundle: fbb4's network, entities, evidence, the full
//     wallet index) needs DESK_PASSWORD. With no DESK_PASSWORD set, /desk/ does not exist (404): it fails closed.
//     Open /desk/unlock once: the browser asks for the password, a cookie remembers it for 30 days and the site then
//     loads the desk bundle instead of the public one.
//   - the whole site: optional, only when SITE_PASSWORD is set (pre-launch lock).
import { next } from "@vercel/functions";

const REALM = 'Basic realm="GME terminal", charset="UTF-8"';
const COOKIE = "gme_desk";

export function checkAuth(header, password) {
  if (!password || !header || !header.startsWith("Basic ")) return false;
  let decoded;
  try { decoded = atob(header.slice(6).trim()); } catch { return false; }
  const i = decoded.indexOf(":");
  if (i < 0) return false;
  return same(decoded.slice(i + 1), password);
}
// Compare every character so the time taken doesn't reveal how much matched.
function same(given, want) {
  let diff = given.length ^ want.length;
  for (let k = 0; k < want.length; k++) diff |= want.charCodeAt(k) ^ (given.charCodeAt(k) || 0);
  return diff === 0;
}
export async function deskToken(password) {
  const h = await crypto.subtle.digest("SHA-256", new TextEncoder().encode("gme-desk:" + password));
  return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
export function cookieOf(header, name) {
  for (const part of (header || "").split(";")) { const [k, ...v] = part.trim().split("="); if (k === name) return v.join("="); }
  return "";
}
export const isDesk = (pathname) => pathname === "/desk" || pathname.startsWith("/desk/");

const deny = (status, body, extra = {}) => new Response(body, { status, headers: { "Content-Type": "text/plain; charset=utf-8", "X-Robots-Tag": "noindex", "Cache-Control": "no-store", ...extra } });

export default async function middleware(request) {
  const site = process.env.SITE_PASSWORD, desk = process.env.DESK_PASSWORD, auth = request.headers.get("authorization");
  const headers = { "X-Robots-Tag": "noindex", "Cache-Control": "private, no-store" };
  if (isDesk(new URL(request.url).pathname)) {
    if (!desk) return deny(404, "Not found.");
    const token = await deskToken(desk);
    if (!same(cookieOf(request.headers.get("cookie"), COOKIE), token)) {
      if (!checkAuth(auth, desk)) return deny(401, "Password required.", { "WWW-Authenticate": REALM });
      headers["Set-Cookie"] = `${COOKIE}=${token}; Path=/desk; Max-Age=2592000; HttpOnly; Secure; SameSite=Strict`;
    }
    return next({ headers });
  }
  if (site && !checkAuth(auth, site) && !(desk && checkAuth(auth, desk))) return deny(401, "Password required.", { "WWW-Authenticate": REALM });
  return next({ headers });
}
