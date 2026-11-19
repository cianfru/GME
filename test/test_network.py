# python3 -m unittest discover -s test -p "test_*.py"   (also run by `npm test` through test/python.test.mjs)
# network.py: resolving a network's groups, and the evidence between them. Synthetic data only.
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import network as N

A, B, C, X, DEP, EXC, POOL = ("0x" + c * 40 for c in "abcdef9")


def tr(s, r, ts, v): return (s, r, ts, float(v), 1)


class Resolve(unittest.TestCase):
    def test_by_id_then_anchor_and_missing(self):
        ents = [dict(id="g1", members=[A], attached=[]), dict(id="g2new", members=[B], attached=[])]
        found, missing = N.resolve(dict(groups=[{"id": "g1"}, {"id": "g2", "anchor": B}, {"id": "g3", "anchor": C, "tag": "gone"}]), ents)
        self.assertEqual([e["id"] for e in found], ["g1", "g2new"])          # g2's id changed: found by its anchor
        self.assertEqual([g["tag"] for g in missing], ["gone"])              # never guessed


class Evidence(unittest.TestCase):
    def test_pairs_shared_wallet_and_deposit(self):
        gof = {A: "g1", B: "g2", C: "g3"}
        T = [tr(A, B, "2025-01-01T00:00:00Z", 100),     # g1 → g2: a GME link
             tr(A, X, "2025-01-02T00:00:00Z", 50),      # g1 and g2 both pay outside wallet X: a shared wallet
             tr(B, X, "2025-01-03T00:00:00Z", 30),
             tr(X, EXC, "2025-01-03T00:05:00Z", 80),    # X sends it all to an exchange
             tr(A, DEP, "2025-01-04T00:00:00Z", 5), tr(C, DEP, "2025-01-05T00:00:00Z", 5)]   # g1 and g3 share a deposit address
        PX = [1.0] * len(T); TX = ["0x%d" % i for i in range(len(T))]
        eth = [dict(f=C, t=A, eth="2.5", n="3", first="2024-05-01 00:00:00", last="2024-06-01 00:00:00")]
        ev = N.evidence(T, PX, TX, gof, {EXC, POOL}, {DEP}, {EXC}, eth, {"g1": "One", "g2": "Two", "g3": "Three"})
        g = [p for p in ev["pairs"] if p["kind"] == "gme"]
        self.assertEqual([(p["a"], p["b"], p["usd"], p["n"]) for p in g], [("g1", "g2", 100, 1)])
        e = [p for p in ev["pairs"] if p["kind"] == "eth"]
        self.assertEqual([(p["a"], p["b"], p["eth"], p["n"]) for p in e], [("g3", "g1", 2.5, 3)])
        self.assertEqual([(s["a"], s["senders"], s["out"]) for s in ev["shared"]], [(X, {"g1": 50, "g2": 30}, {"exchange": 80})])
        self.assertEqual(ev["deposits"], [dict(a=DEP, groups=["g1", "g3"])])

    def test_paying_into_its_own_group_is_not_shared(self):
        gof = {A: "g1", B: "g2", C: "g1"}
        T = [tr(A, C, "2025-01-01T00:00:00Z", 10), tr(B, C, "2025-01-02T00:00:00Z", 10)]   # C (g1) got coins from g1 and g2: only one OTHER group
        ev = N.evidence(T, [1.0, 1.0], ["", ""], gof, set(), set(), set(), [], {})
        self.assertEqual(ev["shared"], [])


if __name__ == "__main__":
    unittest.main()
