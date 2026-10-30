# Transfer-archive helpers (stdlib only).
#   python3 scripts/archive_tools.py maxblock data/transfers.csv          → prints the highest block ("" if none)
#   python3 scripts/archive_tools.py merge data/transfers.csv data/delta.csv
# The delta pull starts AT the archive's max block, so the merge keeps archive rows strictly below the
# delta's first block and takes the delta from there on. The boundary block is replaced whole, which can
# never duplicate or drop a row at the seam (same rule as the pepecoin and SPX pipelines).
import sys, os

def block_col(header):
    return header.strip().lower().split(",").index("block")

def maxblock(path):
    if not os.path.exists(path): return None
    m = None
    with open(path) as f:
        bi = block_col(next(f, "sender,receiver,time,value,block"))
        for line in f:
            if line.strip():
                b = int(line.split(",")[bi]); m = b if m is None or b > m else m
    return m

def merge(archive, delta):
    with open(delta) as f:
        lines = [l for l in f if l.strip()]
    if len(lines) <= 1:
        print("delta empty, archive unchanged"); return
    bi = block_col(lines[0])
    cutoff = min(int(l.split(",")[bi]) for l in lines[1:])
    tmp = archive + ".tmp"; kept = dropped = 0
    with open(archive) as src, open(tmp, "w") as out:
        out.write(next(src))
        for line in src:
            if not line.strip(): continue
            if int(line.split(",")[bi]) < cutoff: out.write(line); kept += 1
            else: dropped += 1
        out.writelines(lines[1:])
    os.replace(tmp, archive)
    print(f"merged: cutoff block {cutoff}, kept {kept}, replaced {dropped}, added {len(lines)-1} → {kept+len(lines)-1} rows")

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "maxblock":
        m = maxblock(sys.argv[2]); print("" if m is None else m)
    elif cmd == "merge":
        merge(sys.argv[2], sys.argv[3])
