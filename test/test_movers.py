# python3 -m unittest discover -s test -p "test_*.py"   (also run by `npm test` through test/python.test.mjs)
# movers.py: one window's summary by owner. Synthetic rows only.
import os, sys, unittest, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import movers as MV

A, B, C, X = "0x" + "a" * 40, "0x" + "b" * 40, "0x" + "c" * 40, "0x" + "e" * 40
ROUTER = "0x" + "9" * 40


T0 = MV.sec("2026-11-19T10:00:00Z")
def row(ts, s, g, u, k, cp): return (ts, T0 + s, g * 1e9, u, k, cp, "0xtx")


class Summary(unittest.TestCase):
    def test_owner_level_flows_and_internal_moves(self):
        own = {A: ("e1", "entity", "Accumulator aaaa"), B: ("e1", "entity", "Accumulator aaaa")}
        rows = {A: [row("2026-11-19T10:16:40Z", 1000, 2.0, 200, "b", ROUTER),     # the group buys 2B for $200
                    row("2026-11-19T11:16:40Z", 4600, -1.0, 100, "o", B)],         # internal: A → B, left out
                B: [row("2026-11-19T11:16:40Z", 4600, 1.0, 100, "i", A),
                    row("2026-11-19T12:16:40Z", 8200, -0.5, 60, "s", ROUTER)],     # sells 0.5B for $60
                C: [row("2026-11-19T12:46:40Z", 10000, 3.0, 300, "b", ROUTER),     # a lone wallet buys and keeps it
                    row("2026-11-18T12:30:00Z", -5000, 9.0, 900, "b", ROUTER)]}    # before the window: ignored
        hold = collections.Counter({"e1": 1.5e9, C: 3e9})
        W = MV.summarise(rows, own, {"e1": "2026-01-01T00:00:00Z", C: "2026-11-19T12:46:40Z"}, hold, T0, T0 + 14400, 3600)
        o = {x["k"]: x for x in W["owners"]}
        self.assertEqual(o["e1"]["net"], 1.5)                    # +2 bought −0.5 sold; the A→B move cancels
        self.assertEqual(o["e1"]["b"], [2.0, 200, 1]); self.assertEqual(o["e1"]["s"], [0.5, 60, 1])
        self.assertEqual(o["e1"]["i"][0], 0); self.assertEqual(o["e1"]["o"][0], 0)
        self.assertFalse(o["e1"]["new"]); self.assertTrue(o[C]["new"])
        self.assertEqual(W["tot"]["buy"], 500); self.assertEqual(W["tot"]["sell"], 60)
        self.assertEqual(W["tot"]["buyers"], 2); self.assertEqual(W["tot"]["sellers"], 1)
        self.assertEqual([b[0] for b in W["bars"]], [200, 0, 300, 0])      # per hour: buys at 1000 s and 10000 s
        self.assertEqual(W["bars"][2][1], 60)
        self.assertEqual(W["trades"][0][4], 300)                          # largest trade first

    def test_dust_owner_is_dropped(self):
        W = MV.summarise({X: [row("2026-11-19T10:00:00Z", 10, 0.0001, 0.4, "b", ROUTER)]}, {}, {}, collections.Counter(), T0, T0 + 3600, 3600)
        self.assertEqual(W["owners"], [])


if __name__ == "__main__":
    unittest.main()
