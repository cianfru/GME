// Optional password gate for every page and data file on the Vercel site (HTTP Basic auth: any username, the password
// is the SITE_PASSWORD environment variable). With no SITE_PASSWORD set the site is open; set it in Vercel and redeploy to lock it.
import { next } from "@vercel/functions";

const REALM = 'Basic realm="GME daily watch", charset="UTF-8"';

export function checkAuth(header, password) {
  if (!password || !header || !header.startsWith("Basic ")) return false;
  let decoded;
  try { decoded = atob(header.slice(6).trim()); } catch { return false; }
  const i = decoded.indexOf(":");
  if (i < 0) return false;
  const given = decoded.slice(i + 1);
  // Compare every character so the time taken doesn't reveal how much of the password matched.
  let diff = given.length ^ password.length;
  for (let k = 0; k < password.length; k++) diff |= password.charCodeAt(k) ^ (given.charCodeAt(k) || 0);
  return diff === 0;
}

export default function middleware(request) {
  const password = process.env.SITE_PASSWORD;
  if (password && !checkAuth(request.headers.get("authorization"), password)) {
    return new Response("Password required.", {
      status: 401, headers: { "WWW-Authenticate": REALM, "Content-Type": "text/plain; charset=utf-8", "X-Robots-Tag": "noindex", "Cache-Control": "no-store" },
    });
  }
  return next({ headers: { "X-Robots-Tag": "noindex", "Cache-Control": "private, no-store" } });
}
