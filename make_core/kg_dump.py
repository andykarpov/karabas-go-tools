#!/bin/env python3
# Prints a kgo2 core file (.kg, docs/kgo2.md): the sections and what they hold.
# Usage: python3 kg_dump.py <file.kg> [--board go|mini|minig]

import argparse
import struct

BOARDS = { 1: "go", 2: "mini", 3: "minig" }
NAMES = { 1: "STRINGS", 2: "CORE", 3: "LOADER", 4: "OSD", 5: "BUTTONS", 6: "MATRIX", 7: "EEPROM_INIT",
          8: "ROMS", 9: "BITSTREAM" }
TYPES = ["S", "N", "T", "H", "P", "F", "FL", "M", "-"]

parser = argparse.ArgumentParser(description = "kgo2 core file dump")
parser.add_argument('file')
parser.add_argument('--board', help = "only the sections of this board")
args = parser.parse_args()

data = open(args.file, "rb").read()
sig, version, _, hsize, count, esize, mask = struct.unpack_from('<4sBBHHHH', data, 0)
if sig != b"kgo2":
    raise SystemExit("not a kgo2 file")

def boards(m):
    return ",".join(BOARDS.get(b, str(b)) for b in range(16) if m & (1 << b))

print("kgo2 version %d, boards %s, %d sections, %d bytes" % (version, boards(mask), count, len(data)))
table = [struct.unpack_from('<HHII', data, hsize + i * esize) for i in range(count)]
strings = next(data[o:o + n] for t, m, o, n in table if t == 1)

def s(ofs):
    return strings[ofs:strings.index(b'\0', ofs)].decode('utf-8')

want = None
if args.board:
    want = 1 << next(k for k, v in BOARDS.items() if v == args.board)

for t, m, ofs, n in table:
    if want and not m & want:
        continue
    sec = data[ofs:ofs + n]
    print("\n[%s] boards %s, offset %d, %d bytes" % (NAMES.get(t, "type %d" % t), boards(m), ofs, n))
    if t == 2:
        size, i, nm, b, typ, vis, order, rtc, eep, spi, drv = struct.unpack_from('<HHHHBBBBBBH', sec, 0)
        print("  id %r name %r build %r type %d visible %d order %d rtc %d eeprom %d spi %d drives %r" %
              (s(i), s(nm), s(b), typ, vis, order, rtc, eep, spi, s(drv)))
    elif t == 3:
        size, d, e, sd, flags, nf, fo = struct.unpack_from('<HHHHBBH', sec, 0)
        files = [s(struct.unpack_from('<H', sec, fo + 2 * k)[0]) for k in range(nf)]
        print("  dir %r exts %r save_dir %r autoload %d files %r" % (s(d), s(e), s(sd), flags & 1, files))
    elif t == 4:
        cnt, isize, _ = struct.unpack_from('<HHI', sec, 0)
        for k in range(cnt):
            r = 8 + k * isize
            f = struct.unpack_from('<14BH', sec, r)
            key, name, hk, exts, d, oo, fo = struct.unpack_from('<7H', sec, r + 16)
            typ, flags, index, page, opn, ci, cf, cv, dflt, slot, hm, hkk, no, nf, _ = f
            line = "  %2d %-2s %-16s key %-16s" % (k, TYPES[typ] if typ < len(TYPES) else typ, s(name), s(key))
            if index != 255: line += " index %d" % index
            if page: line += " page %d" % page
            if opn: line += " opens %d" % opn
            if ci: line += " %s item %d %s%d" % ("enable_if" if cf & 0x80 else "show_if", ci - 1, "not " if cf & 0x40 else "", cv)
            if s(hk): line += " hotkey %s (%02x %02x)" % (s(hk), hm, hkk)
            if typ in (5, 6):
                files = [s(struct.unpack_from('<H', sec, fo + 2 * j)[0]) for j in range(nf)]
                line += " slot %d exts %r dir %r files %r flags %d" % (slot, s(exts), s(d), files, flags)
            print(line)
            if no:
                opts = []
                for j in range(no):
                    ok, on, ov = struct.unpack_from('<HHB', sec, oo + 8 * j)
                    opts.append("%s%s=%d" % ("*" if ov == dflt else "", s(ok), ov))
                print("       options: " + " ".join(opts) + "   (%r)" % [s(struct.unpack_from('<HHB', sec, oo + 8 * j)[1]) for j in range(no)])
    elif t == 5:
        print("  " + sec.hex(" "))
    elif t == 8:
        p = 0
        while p < n:
            ln, addr = struct.unpack_from('<II', sec, p)
            size = ln & 0x7FFFFFFF
            ext = ln >> 31
            print("  addr %08x %s" % (addr, ("external %r" % sec[p + 8:p + 8 + size].decode()) if ext else "%d bytes" % size))
            p += 8 + size
    elif t == 1:
        print("  %d strings" % sec.count(b'\0'))
