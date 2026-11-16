# python3 -m unittest discover -s test -p "test_*.py"   (also run by `npm test` through test/python.test.mjs)
# The Wallet page's index: how a transfer is classified from a wallet's side, who seeded whom, and the venue labels
# (venues.py, shared with the Visualizer). Synthetic data only: the real archive is not in git.
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import wallet_index as W
from venues import deposits, node
from txlib import PAIR, V3POOL, NULL, DEAD, TOKEN

ROUTER = "0x66a9893cc07d91d95644aedd05d03f95e1dba8af"           # Uniswap app
BOT = "0x00000000000000000000000000000000000b0b07"
MEXC = "0x9642b23ed1e01df1092b92641051881a322f5d4e"
EX = {PAIR: {"kind": "lp", "name": "pair"}, V3POOL: {"kind": "lp", "name": "v3"}, ROUTER: {"kind": "mm", "name": "UniversalRouter"},
      BOT: {"kind": "mm", "name": "MEV bot"}, MEXC: {"kind": "cex", "name": "MEXC 2"}, NULL: {"kind": "null"}, DEAD: {"kind": "burn"}}
A, B, C, DEPADDR = "0x" + "a" * 40, "0x" + "b" * 40, "0x" + "c" * 40, "0x" + "d" * 40
CEX = {MEXC}; infra = set(EX)


def tr(s, r, ts, v): return (s, r, ts, float(v), 1)


class Venues(unittest.TestCase):
    def test_deposit_address_is_named_after_its_exchange(self):
        T = [tr(A, DEPADDR, "2025-01-01T00:00:00Z", 100), tr(DEPADDR, MEXC, "2025-01-01T00:05:00Z", 100), tr(A, B, "2025-01-02T00:00:00Z", 5)]
        dep = deposits(T, EX)
        self.assertEqual(dep, {DEPADDR: MEXC})                   # DEPADDR forwarded all its GME to MEXC; A sent none to an exchange
        self.assertEqual(node(DEPADDR, EX, dep), (DEPADDR, "deposit", "MEXC 2 deposit"))

    def test_mostly_but_not_95pct_to_an_exchange_is_not_a_deposit(self):
        T = [tr(C, MEXC, "2025-01-01T00:00:00Z", 90), tr(C, B, "2025-01-01T00:00:00Z", 10)]
        self.assertEqual(deposits(T, EX), {})

    def test_labels(self):
        self.assertEqual(node(PAIR, EX, {})[1:], ("dex", "Uniswap V2 · GME/WETH"))
        self.assertEqual(node(ROUTER, EX, {})[1:], ("dex", "Uniswap app"))
        self.assertEqual(node(BOT, EX, {})[1:], ("dex", "Other routers & bots"))
        self.assertEqual(node(MEXC, EX, {})[1:], ("cex", "MEXC 2"))
        self.assertEqual(node(A, EX, {}, {A: "contract"})[1:], ("contract", ""))


class Classify(unittest.TestCase):
    k = staticmethod(lambda other, out, dep={}: W.kind(other, out, infra, CEX, dep))

    def test_kinds(self):
        self.assertEqual(self.k(ROUTER, False), "b")             # from a router = a DEX buy
        self.assertEqual(self.k(PAIR, True), "s")                # into the V2 pair = a DEX sale
        self.assertEqual(self.k(MEXC, True), "co")
        self.assertEqual(self.k(DEPADDR, True, {DEPADDR: MEXC}), "co")   # a deposit address counts as the exchange
        self.assertEqual(self.k(V3POOL, True), "la")             # V3 pool sends are liquidity, not trades
        self.assertEqual(self.k(TOKEN, True), "o")               # a send to the token contract is not a sale
        self.assertEqual(self.k(DEAD, True), "x")
        self.assertEqual(self.k(B, False), "i")


class Build(unittest.TestCase):
    def test_rows_seed_and_deposit_users(self):
        T = [tr(ROUTER, A, "2025-01-01T00:00:00Z", 1000),         # A buys
             tr(A, B, "2025-01-02T00:00:00Z", 400),               # A seeds B
             tr(A, A, "2025-01-02T00:00:00Z", 1),                 # self-transfer: skipped
             tr(C, B, "2025-01-03T00:00:00Z", 0),                 # zero-value spam: skipped, and not B's seed
             tr(B, DEPADDR, "2025-01-04T00:00:00Z", 100), tr(A, DEPADDR, "2025-01-05T00:00:00Z", 50)]
        PX = [2.0] * len(T); KEYS = [(1, i) for i in range(len(T))]; TX = ["0xt%d" % i for i in range(len(T))]
        rows, seed, seeded, dep_users, bal = W.build(T, PX, KEYS, TX, {(1, 0): 2.0}, infra, CEX, {DEPADDR: MEXC})
        self.assertNotIn(ROUTER, rows)                           # infrastructure gets no record
        self.assertEqual([r[3] for r in rows[A]], ["b", "o", "co"])
        self.assertEqual(rows[A][0][7], 1)                       # the buy has an exact price, the others don't
        self.assertEqual(rows[A][1][:3], ("2025-01-02T00:00:00Z", -400.0, 800.0))
        self.assertEqual(seed[B][0], A)
        self.assertEqual([x[0] for x in seeded[A]], [B])
        self.assertEqual([x[0] for x in seeded[B]], [DEPADDR])        # the deposit address's first GME came from B
        self.assertEqual(dep_users[DEPADDR], {A, B})
        self.assertEqual(bal[A], 550); self.assertEqual(bal[B], 300)

    def test_seeded_lists_keep_the_2k_bar_and_drop_deposit_addresses(self):
        sd = [(B, "2025-01-02T00:00:00Z", 1e9, 5000.0), (C, "2025-01-03T00:00:00Z", 1e6, 12.0), (DEPADDR, "2025-01-04T00:00:00Z", 1e9, 9000.0)]
        listed, more = W.seeded_lists(sd, {DEPADDR: MEXC})
        self.assertEqual([x[0] for x in listed], [B])
        self.assertEqual(more, [0, 1])                           # nothing beyond the cap, one small first send


class Groups(unittest.TestCase):
    def test_group_pnl_skips_moves_between_its_own_wallets(self):
        T = [tr(ROUTER, A, "2025-01-01T00:00:00Z", 1000),        # the group buys 1000 at $1
             tr(A, B, "2025-01-02T00:00:00Z", 1000),              # internal: A → B, same owner
             tr(B, PAIR, "2025-01-03T00:00:00Z", 400),            # the group sells 400 at $3
             tr(B, C, "2025-01-04T00:00:00Z", 100)]               # sent to an outsider: leaves at cost, no P/L
        PX = [1.0, 2.0, 3.0, 4.0]
        pl = W.group_books(T, PX, {A: "g1", B: "g1"}, infra, CEX, {}, "2025-01-01")["g1"]
        last = pl["track"][-1]                                    # [day, holdB, cost, realized, bought, sold]
        self.assertEqual(last[1], round(500 / 1e9, 4))
        self.assertEqual(last[2:], [500, 800, 1000, 1200])        # cost of the 500 held, realized (3-1)×400, bought, sold
        self.assertEqual(sorted(m[1] for m in pl["marks"]), [])   # marks need ≥1e6 GME: none at this scale


if __name__ == "__main__":
    unittest.main()
