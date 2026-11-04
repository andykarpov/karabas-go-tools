#!/bin/env python3
# Merges the core.json of each board (core.json, core_mini.json, core_minig.json) into one kgo2
# core.json (docs/kgo2.md): the keys equal on all boards at the top, the rest and the bitstreams in
# "boards"; the OSD items in one list, an item that is not the same on every board with "boards".
# The items are aligned so that the list of each board is exactly its old list (the same order,
# so the same switch numbers): checked before the file is written.
# Usage: python3 merge_boards.py go=core.json mini=core_mini.json minig=core_minig.json -o out.json

import argparse
import json
import sys

BOARDS = ["go", "mini", "minig"]

parser = argparse.ArgumentParser(description="merge the core.json of the boards into one kgo2 core.json")
parser.add_argument("inputs", nargs="+", help="board=file.json")
parser.add_argument("-o", "--output", required=True)
args = parser.parse_args()

src = {}
for a in args.inputs:
    board, _, path = a.partition("=")
    if board not in BOARDS or not path:
        sys.exit("%s: expected board=file.json, board one of %s" % (a, ", ".join(BOARDS)))
    with open(path) as f:
        src[board] = json.load(f)
    if "boards" in src[board]:
        sys.exit("%s already has \"boards\"" % path)
boards = [b for b in BOARDS if b in src]


# the merged list: [item, [boards]]; each board's list is merged in by the longest common
# subsequence, so the order of every board is kept
def merge(merged, items, board):
    n, m = len(merged), len(items)
    lcs = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            lcs[i][j] = lcs[i + 1][j + 1] + 1 if merged[i][0] == items[j] else max(lcs[i + 1][j], lcs[i][j + 1])
    out, i, j = [], 0, 0
    while i < n or j < m:
        if i < n and j < m and merged[i][0] == items[j]:
            out.append([merged[i][0], merged[i][1] + [board]])
            i += 1
            j += 1
        elif j == m or (i < n and lcs[i + 1][j] >= lcs[i][j + 1]):
            out.append(merged[i])
            i += 1
        else:
            out.append([items[j], [board]])
            j += 1
    return out


merged = []
for b in boards:
    merged = merge(merged, src[b].get("osd") or [], b)
for b in boards:
    if [it for it, bs in merged if b in bs] != (src[b].get("osd") or []):
        sys.exit("internal error: the items of %s are not its old list" % b)

out = {}
per_board = {b: {} for b in boards}
keys = []
for b in boards:
    for k in src[b]:
        if k not in keys and k != "osd":
            keys.append(k)
for k in keys:
    vals = [src[b].get(k, None) for b in boards]
    present = [k in src[b] for b in boards]
    if k != "bitstream" and all(present) and all(v == vals[0] for v in vals):
        out[k] = vals[0]
    else:
        for b in boards:
            if k in src[b]:
                per_board[b][k] = src[b][k]
out["boards"] = per_board
out["osd"] = []
for it, bs in merged:
    if len(bs) != len(boards):
        it = dict(it)
        it["boards"] = [b for b in boards if b in bs]
    out["osd"].append(it)


# the layout of the core.json files: an object per line in "boards", an OSD item per line
def dump(v, indent):
    pad = " " * indent
    if isinstance(v, dict) and v:
        parts = []
        for k, x in v.items():
            if k in ("osd", "roms") and isinstance(x, list):
                items = ",\n".join(pad + "    " + json.dumps(i, ensure_ascii=False) for i in x)
                parts.append("%s%s: [\n%s\n%s]" % (pad + "    ", json.dumps(k), items, pad + "    ") if x else
                             "%s%s: []" % (pad + "    ", json.dumps(k)))
            elif k == "boards":
                rows = ",\n".join("%s%s: %s" % (pad + "        ", json.dumps(b), json.dumps(o, ensure_ascii=False))
                                  for b, o in x.items())
                parts.append("%s\"boards\": {\n%s\n%s}" % (pad + "    ", rows, pad + "    "))
            else:
                parts.append("%s%s: %s" % (pad + "    ", json.dumps(k), json.dumps(x, ensure_ascii=False)))
        return "{\n" + ",\n".join(parts) + "\n" + pad + "}"
    return json.dumps(v, ensure_ascii=False)


with open(args.output, "w") as f:
    f.write(dump(out, 0) + "\n")
shared = sum(1 for _, bs in merged if len(bs) == len(boards))
print("%s: %s, %d OSD items (%d on all boards), per board: %s" % (args.output, ", ".join(boards), len(merged), shared,
      "; ".join("%s %s" % (b, ", ".join(per_board[b])) for b in boards)))
