# Minimal Blockscout v2 pager (keyless). Caches each address+endpoint to data/bs/*.json.
import os, ssl, json, sys, time, urllib.request, urllib.parse, urllib.error
_CA = "/root/.ccr/ca-bundle.crt"
_CTX = ssl.create_default_context(cafile=_CA) if os.path.exists(_CA) else ssl.create_default_context()
_PXY = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
_OP = urllib.request.build_opener(urllib.request.ProxyHandler({"https": _PXY, "http": _PXY} if _PXY else {}),
                                  urllib.request.HTTPSHandler(context=_CTX))
BASE = "https://eth.blockscout.com/api/v2"
CACHE = os.path.join(os.path.dirname(__file__), "..", "data", "bs")

def get(path, params=None, tries=6):
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    for t in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8.5.0", "accept": "application/json"})
            with _OP.open(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            time.sleep(1.5 * (t + 1))
        except Exception:
            time.sleep(1.5 * (t + 1))
    print("WARN blockscout failed:", url, file=sys.stderr); return None

def pages(path, params=None, max_pages=400, key=None):
    """All items of a paginated endpoint, cached on disk under key."""
    if key:
        fp = os.path.join(CACHE, key + ".json")
        if os.path.exists(fp):
            return json.load(open(fp))
    out, p, n = [], dict(params or {}), 0
    while n < max_pages:
        d = get(path, p)
        if not d: break
        out += d.get("items", [])
        nxt = d.get("next_page_params")
        n += 1
        if not nxt: break
        p = dict(params or {}); p.update({k: v for k, v in nxt.items() if v is not None})
        time.sleep(0.15)
    if key:
        json.dump(out, open(os.path.join(CACHE, key + ".json"), "w"))
    return out
