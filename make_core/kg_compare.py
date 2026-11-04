#!/bin/env python3
# Compares what the firmware gets from two core files: a kgo1 file (.kg1 / .kg2 / .kg3) and the
# view of one board in a kgo2 file (.kg), or two files of the same format. Checks the bitstream,
# the ROMs, the core fields, the loader, buttons, matrix, the first EEPROM content and every OSD
# item (switch number, options as positions, defaults, conditions, hotkeys, F / FL fields).
# Usage: python3 kg_compare.py <old> <new> [--board go|mini|minig] [--board-old ...]
# Exit status 0 when they match.

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import kg_model

parser = argparse.ArgumentParser(description="core file comparison")
parser.add_argument("old")
parser.add_argument("new")
parser.add_argument("--board", help="the board of a kgo2 file (both, unless --board-old)")
parser.add_argument("--board-old", help="the board of a kgo2 old file")
parser.add_argument("-q", "--quiet", action="store_true", help="only the result line")
args = parser.parse_args()

a = kg_model.read_file(args.old, args.board_old or args.board)
b = kg_model.read_file(args.new, args.board)
diffs = []


def diff(what, x, y):
    if x != y:
        if isinstance(x, (bytes, bytearray)) and isinstance(y, (bytes, bytearray)):
            first = next((i for i in range(min(len(x), len(y))) if x[i] != y[i]), min(len(x), len(y)))
            diffs.append("%s: %d / %d bytes, first difference at %d" % (what, len(x), len(y), first))
        else:
            diffs.append("%s: %r / %r" % (what, x, y))


if b is None:
    print("%s: no bitstream for board %s" % (args.new, args.board))
    sys.exit(1)

for k in a["core"]:
    diff("core " + k, a["core"][k], b["core"][k])
for k in a["loader"]:
    diff("loader " + k, a["loader"][k], b["loader"][k])
diff("buttons", a["buttons"], b["buttons"])
diff("matrix", a["matrix"], b["matrix"])
if a["core"]["eeprom_bank"] not in range(0, 4) and a["core"]["eeprom_bank"] != 255:
    diff("eeprom", a["eeprom"], b["eeprom"])
diff("bitstream", a["bitstream"], b["bitstream"])
diff("rom count", len(a["roms"]), len(b["roms"]))
for i, (x, y) in enumerate(zip(a["roms"], b["roms"])):
    for k in ("address", "external", "data"):
        diff("rom %d %s" % (i, k), x[k], y[k])
diff("osd item count", len(a["osd"]), len(b["osd"]))
for i, (x, y) in enumerate(zip(a["osd"], b["osd"])):
    w = "osd %d (%s)" % (i, x["name"] or x["type"])
    for k in ("type", "name", "options", "default", "keys", "page", "open", "cond", "flags"):
        diff("%s %s" % (w, k), x[k], y[k])
    if x["type"] not in ("M", "-"):
        diff(w + " hotkey", x["hotkey"], y["hotkey"])
    if x["type"] in ("S", "N", "T", "H") and y["type"] in ("S", "N", "T", "H"):
        diff(w + " switch", x["index"], y["index"])
    if x["type"] in ("F", "FL") and y["type"] == x["type"]:
        for k in ("slot", "autoload", "physical", "exts", "dir", "files"):
            diff("%s %s" % (w, k), x[k], y[k])

name = "%s vs %s%s" % (args.old, args.new, " (%s)" % args.board if args.board else "")
if diffs:
    print("DIFFERENT: %s, %d differences" % (name, len(diffs)))
    if not args.quiet:
        for d in diffs:
            print("  " + d)
    sys.exit(1)
print("same: %s" % name)
