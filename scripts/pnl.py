# Profit and loss over time for one owner: an entity (entities.py) or a single wallet (terminal.py). One method for both.
#
#   FIFO lots. Every GME that arrives opens a lot at its price: the exact execution price for a DEX buy (trades.py),
#   that day's close for anything else (exchange withdrawal, transfer from another wallet, liquidity removed).
#   A SALE is GME going to the DEX or to an exchange (an exchange deposit is treated as a sale). It closes the oldest
#   lots first and realizes (sale price − lot price) × amount.
#   Anything else that leaves (to another wallet, liquidity added, burned, sent to the token contract) closes the
#   oldest lots AT COST: no profit or loss, because nothing was sold.
#   Unrealized P/L on a given day = holdings × that day's price − cost of the lots still held (computed by the page).
#
# Output, compact so a page can draw it:
#   track — one row per day that changed: [day index, holdings B, cost of held $, realized $ (cumulative),
#           bought $ (DEX buys + exchange withdrawals, cumulative), sold $ (DEX sales + exchange deposits, cumulative)]
#   marks — trades per day and kind: [day index, kind, GME B, $]; kinds b = DEX buy, s = DEX sale,
#           ci = from an exchange, co = to an exchange. $/GME of a DEX mark is the day's average execution price.
import collections, datetime

KINDS = ("b", "s", "ci", "co")


class Book:
    def __init__(self, day0):
        self.day0 = datetime.date.fromisoformat(day0)
        self.lots = collections.deque()            # [qty, price, source D/C/W]
        self.hold = self.cost = self.realized = self.bought = self.sold = 0.0
        self.track, self.marks = [], collections.OrderedDict()
        self._day = None

    def _di(self, ts):
        return (datetime.date.fromisoformat(ts[:10]) - self.day0).days

    def _close_day(self):
        if self._day is None: return
        row = [self._day, round(self.hold / 1e9, 4), round(self.cost), round(self.realized), round(self.bought), round(self.sold)]
        if self.track and self.track[-1][0] == self._day: self.track[-1] = row
        else: self.track.append(row)

    def _at(self, ts):
        d = self._di(ts)
        if d != self._day: self._close_day(); self._day = d
        return d

    def _mark(self, d, k, v, usd):
        x = self.marks.setdefault((d, k), [0.0, 0.0]); x[0] += v; x[1] += usd

    def inflow(self, ts, v, px, src):
        """src: 'D' DEX buy, 'C' exchange withdrawal, 'W' anything else."""
        d = self._at(ts)
        self.lots.append([v, px, src]); self.hold += v; self.cost += v * px
        if src in ("D", "C"):
            self.bought += v * px; self._mark(d, "b" if src == "D" else "ci", v, v * px)

    def outflow(self, ts, v, px, sale, dest=None):
        """sale: GME went to the DEX ('D') or an exchange ('C'); otherwise it leaves at cost."""
        d = self._at(ts)
        q, c = v, 0.0
        while q > 1e-9 and self.lots:
            lot = self.lots[0]; t = min(q, lot[0]); c += t * lot[1]; lot[0] -= t; q -= t
            if lot[0] <= 1e-9: self.lots.popleft()
        taken = v - q                              # never more than was held (q > 0 only if lots ran out)
        self.hold = max(0.0, self.hold - v); self.cost = max(0.0, self.cost - c)
        if sale:
            self.realized += taken * px - c; self.sold += v * px
            self._mark(d, "s" if sale == "D" else "co", v, v * px)

    def finish(self):
        self._close_day()
        marks = [[d, k, round(v / 1e9, 4), round(u)] for (d, k), (v, u) in self.marks.items() if v >= 1e6]
        return dict(track=self.track, marks=marks)

    def source_mix(self):
        held = sum(l[0] for l in self.lots)
        if held <= 1: return {}
        mix = collections.Counter()
        for l in self.lots: mix[l[2]] += l[0]
        return {k: round(100 * v / held, 1) for k, v in mix.items()}
