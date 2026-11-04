#!/bin/env python3
# Turns a kgo1 core file (.kg1 / .kg2 / .kg3) back into a core.json with its bitstream and
# embedded ROMs as files next to it, for a core whose sources are gone: make_core.py then packs
# it as kgo2 (python3 make_core.py core.json name.kg --boards <board>). kg_compare.py checks the
# result against the old file.
# Usage: python3 kg1_to_json.py <file.kgN> <out dir>

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import kg_model

KEYS = {0x11: "Ctrl", 0x22: "Shift", 0x44: "Alt", 0x88: "Menu"}

parser = argparse.ArgumentParser(description="kgo1 core file -> core.json + files")
parser.add_argument("file")
parser.add_argument("out_dir")
args = parser.parse_args()

m = kg_model.read_file(args.file)
os.makedirs(args.out_dir, exist_ok=True)
base = os.path.splitext(os.path.basename(args.file))[0]
c = m["core"]
d = {"id": c["id"], "name": c["name"], "build": c["build"], "visible": bool(c["visible"]), "order": c["order"],
     "type": kg_model.CORE_TYPES.get(c["type"], "none"), "eeprom_bank": c["eeprom_bank"], "rtc_mode": c["rtc_mode"]}
if c["spi_freq"]:
    d["spi_freq"] = c["spi_freq"]
ld = m["loader"]
if ld["dir"] or ld["exts"] or ld["save_dir"]:
    d["loader"] = {"dir": ld["dir"], "exts": ld["exts"]}
    if ld["save_dir"]:
        d["loader"]["save_dir"] = ld["save_dir"]

bit = base + ".bin"
with open(os.path.join(args.out_dir, bit), "wb") as f:
    f.write(m["bitstream"])
d["bitstream"] = bit
d["roms"] = []
for i, r in enumerate(m["roms"]):
    if r["external"]:
        d["roms"].append({"filename": r["data"].decode("ascii"), "address": r["address"], "external": True})
    else:
        name = "%s_rom%d.bin" % (base, i)
        with open(os.path.join(args.out_dir, name), "wb") as f:
            f.write(r["data"])
        d["roms"].append({"filename": name, "address": r["address"]})

# buttons and matrix: the raw blocks are not json; kept only when set
if any(p != 0 or h for p, h in m["buttons"]):
    print("warning: buttons %s are not converted" % m["buttons"])
if m["matrix"] != bytes(256):
    print("warning: the matrix block is not converted")

osd = []
for it in m["osd"]:
    t = it["type"]
    o = {"type": t}
    if t != "-":
        o["name"] = it["name"]
    if t in ("S", "N"):
        o["options"] = it["options"]
        o["default"] = it["default"]
    if t == "M":
        o["open"] = it["open"]
    if t in ("F", "FL"):
        o["slot"] = it["slot"]
        o["exts"] = it["exts"]
        if it["dir"]:
            o["dir"] = it["dir"]
        if it["files"]:
            o["file"] = it["files"][0]
        if it["autoload"]:
            o["autoload"] = 1
        if it["physical"]:
            o["physical"] = 1
    if it["hotkey"] and t not in ("M", "-", "P"):
        o["hotkey"] = it["hotkey"]
    if it["page"]:
        o["page"] = it["page"]
    ci, cf, cv = it["cond"]
    if ci:
        o["enable_if" if cf & 0x80 else "show_if"] = dict({"item": ci - 1, "value": cv}, **({"not": True} if cf & 0x40 else {}))
    osd.append(o)
d["osd"] = osd
with open(os.path.join(args.out_dir, "core.json"), "w") as f:
    json.dump(d, f, indent=4)
print("%s: core.json, %s, %d ROM(s), %d OSD items" % (args.out_dir, bit, len(d["roms"]), len(osd)))
