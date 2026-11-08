# python3 -m unittest discover -s test -p "test_*.py"   (also run by `npm test` through test/python.test.mjs)
import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import bq_flows as B

HEAD = "f,t,n,eth,first,last,min_nonce\n"


def csvfile(d, name, body):
    p = os.path.join(d, name)
    with open(p, "w") as fh: fh.write(HEAD + body)
    return p


class MergeFlows(unittest.TestCase):
    def test_merge_adds_counts_and_keeps_extremes(self):
        with tempfile.TemporaryDirectory() as d:
            base = B.read(csvfile(d, "a.csv", "0xA,0xb,2,1.5,2024-05-01 10:00:00,2026-11-01 09:00:00,3\n0xc,0xd,1,0.1,2025-01-01 00:00:00,2025-01-01 00:00:00,\n"))
            delta = B.read(csvfile(d, "b.csv", "0xa,0xB,3,0.25,2026-11-02 08:00:00 UTC,2026-11-06 12:00:00 UTC,1\n0xe,0xf,1,2.0,2026-11-03 00:00:00,2026-11-03 00:00:00,0\n"))
            m = B.merge(base, delta)
            self.assertEqual(m[("0xa", "0xb")], [5, 1.75, "2024-05-01 10:00:00", "2026-11-06 12:00:00", 1])   # case-folded, summed, extremes
            self.assertEqual(m[("0xc", "0xd")][4], None)                                                       # a missing nonce stays missing
            self.assertEqual(m[("0xe", "0xf")], [1, 2.0, "2026-11-03 00:00:00", "2026-11-03 00:00:00", 0])     # a new pair is added
            self.assertEqual(B.cutoff(m), "2026-11-06 12:00:00")

    def test_merging_halves_equals_the_whole(self):
        # the same pair split at a cut-off and merged back gives what one query over the whole window would
        whole = [7, 3.0, "2024-04-02 00:00:00", "2026-11-07 00:00:00", 0]
        a = [4, 1.0, "2024-04-02 00:00:00", "2026-10-01 00:00:00", 0]
        b = [3, 2.0, "2026-10-02 00:00:00", "2026-11-07 00:00:00", 41]
        self.assertEqual(B.merge_row(a, b), whole)

    def test_write_is_sorted_and_reads_back(self):
        with tempfile.TemporaryDirectory() as d:
            rows = {("0xz", "0xa"): [1, 0.5, "2025-01-01 00:00:00", "2025-01-01 00:00:00", 0], ("0xa", "0xz"): [2, 1e-4, "2025-02-01 00:00:00", "2025-03-01 00:00:00", None]}
            p = os.path.join(d, "out.csv"); B.write(p, rows)
            lines = open(p).read().splitlines()
            self.assertEqual(lines[0], HEAD.strip())
            self.assertTrue(lines[1].startswith("0xa,0xz,") and lines[2].startswith("0xz,0xa,"))
            self.assertEqual(B.read(p), rows)
            self.assertFalse(os.path.exists(p + ".tmp"))


if __name__ == "__main__":
    unittest.main()
