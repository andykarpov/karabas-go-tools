#!/bin/env python3

#########################################################
# Karabas Go Spec256 snapshot convertor v1.3            #
#                                                       #
# (c) 2026 Andy Karpov <andy.karpov@gmail.com>          #
#########################################################

# NAME.SNA + NAME.GFX (+ NAME.PAL, NAME.CFG, NAME.GFB, NAME.B00..B99, any case) -> NAME.256:
#   49152    the RAM of the snapshot (4000-FFFF)
#   393216   the 8 planes of each address (bit k of plane p = bit p of the colour of pixel k)
#   28       the registers (below)
#   the extension (not with --plain), little endian:
#   0  4     "K256"
#   4  1     version 1
#   5  1     flags: 0 the ROM planes follow, 1 Paper00InkFF, 2 HideSameInkPaper, 3 BkOverFF
#   6  1     UpColorsMixed
#   7  1     DownColorsMixed
#   8  1     number of backgrounds (the highest Bnn + 1; a missing one is colour 0)
#   9  1     number of rules (up to 16)
#   10 1     the background shown first (the lowest Bnn there is), 0xFF: none
#   11 5     0
#   16 768   the palette, RGB (NAME.PAL or the standard Spec256 one)
#   784 64   16 rules: background, address (2), value: background n while the byte at the address is
#            the value (the "NN: addr=VVh" lines of the .CFG; the first one that matches)
#   848      131072 the ROM planes (NAME.GFB, the 16K of the 48K ROM), if flag 0
#   then     49152 per background: the 256x192 paper of the 320x200 picture (x 32..287, y 4..195)
# The settings and their defaults are those of ZX-Poly / ZxNextEmu (karabas-go-core-spec256
# docs/SIMD.md, section 7).

import argparse
import sys
import os
from pathlib import Path


msg = "Karabas Go Spec256 snapshot convertor v1.3"
parser = argparse.ArgumentParser(description = msg)
parser.add_argument('sna_file')
parser.add_argument('--plain', action='store_true', help='no extension (the format of v1.2)')
args = parser.parse_args()

sna_filename = Path(args.sna_file)
outfile = sna_filename.with_suffix(".256")

# the files of the game: same name, any case of the name and of the extension
def companion(ext):
    stem = sna_filename.stem.lower()
    for f in sna_filename.parent.iterdir():
        if f.is_file() and f.stem.lower() == stem and f.suffix.lower() == ext.lower() and f.stat().st_size > 0:
            return f
    return None

gfx_filename = companion(".gfx") or sna_filename.with_suffix(".GFX")

def file_check(name):
    if not os.path.isfile(name):
        print("Unable to read file ", name)
        exit(1)    

def file_read(name, mode = "r", seek=0, limit=0):
    file_check(name)
    f = open(name, mode)
    if seek:
        f.seek(seek)
    if limit:
        data = bytearray(f.read(limit))
    else:
        data = bytearray(f.read())
    f.close()
    return data

# check sna and gfx exists
sna = file_read(sna_filename, "rb", 27)
sna_size = len(sna)
gfx = file_read(gfx_filename, "rb")
gfx_size = len(gfx)
regs = file_read(sna_filename, "rb", 0, 27)
regs_size = len(regs)

if sna_size + regs_size != 49179:
    print(f"SNA size should be exactly 49179 bytes, got {sna_size}")
    exit(1)

if gfx_size != 393216:
    print(f"GFX size should be exactly 393216 bytes, got {gfx_size}")
    exit(1)

print(f"Converting {sna_filename} + {gfx_filename} into {outfile}")
o = open(outfile, "wb")

# область памяти cpu0
for i in range(49152):
    byte_sna = sna[i]
    o.write(byte_sna.to_bytes(1, 'big'))

# GFX -> 8 битовых плоскостей (как gfxram_load в GZX): бит k плоскости p = бит p цвета пикселя k.
# 0x00 и 0xFF - обычные цвета: 0xFF прозрачен только при выводе на экран, не в данных.
def planes(gfx, n):
    out = bytearray()
    for i in range(n):
        word_gfx = gfx[i*8:i*8+8]
        for ctx in range(8):
            bitmask = 1 << ctx
            accumulator = 0
            for k in range(8):
                if word_gfx[k] & bitmask != 0:
                    accumulator |= 1 << k
            out.append(accumulator)
    return bytes(out)

o.write(planes(gfx, 49152))

"""
SNA header:

; 0        1        Регистр I.
; 1        2        Регистровая пара HL'.
; 3        2        Регистровая пара DE'.
; 5        2        Регистровая пара BC'.
; 7        2        Регистровая пара AF'.
; 9        2        Регистровая пара HL.
; 11       2        Регистровая пара DE.
; 13       2        Регистровая пара BC.
; 15       2        Регистровая пара IY.
; 17       2        Регистровая пара IX.
; 19       1        Состояние прерываний. Бит 2 содержит состояние
;                   триггера IFF2, бит 1 - IFF1 (0=DI, 1=EI).
; 20       1        Регистр R.
; 21       2        Регистровая пара AF.
; 23       2        Указатель на вершину стэка (SP).
; 25       1        Режим прерываний: 0=IM0, 1=IM1, 2=IM2.
; 26       1        Цвет бордюра, 0-7.

порядок регистров T80 (для восстановления через DIR / DIRSet):
IFF2(1 bit), IFF1(1 bit), IM(2 bits), IY, HL', DE', BC', IX, HL, DE, BC, PC, SP, R, I, F', A', F, A
"""

def write_reg(reg):
    o.write(regs[reg].to_bytes(1, 'big'))

write_reg(21)      # [7:0]   A
write_reg(22)      # [15:8]  F
write_reg(7)       # [23:15] A'
write_reg(8)       # [31:16] F'
write_reg(0)       # [39:32] I
write_reg(20)      # [47:40] R
write_reg(23)      # [55:48] SP l
write_reg(24)      # [63:56] SP h
o.write((0x72).to_bytes(1, 'big'))     # [71:64] PC l # RETN
o.write((0x00).to_bytes(1, 'big'))     # [79:72] PC h
write_reg(13)      # [87:80] C
write_reg(14)      # [95:88] B
write_reg(11)      # [103:96]  E
write_reg(12)      # [111:104] D
write_reg(9)       # [119:112] L
write_reg(10)      # [127:120] H
write_reg(17)      # [135:128] X l
write_reg(18)      # [143:136] X h
write_reg(5)       # [151:144] C'
write_reg(6)       # [159:152] B'
write_reg(3)       # [167:160] E'
write_reg(4)       # [175:168] D'
write_reg(1)       # [183:176] L'
write_reg(2)       # [191:184] H'
write_reg(15)      # [199:192] Y l
write_reg(16)      # [207:200] Y h

iff = 2 if regs[19] & 0x04 else 0
im_iff = regs[25] + (iff << 2)
print(f"IM={regs[25]}, IFF={iff}, im+iff={im_iff}")
o.write(im_iff.to_bytes(1, 'big'))      # [215:208] {4'b0000, IFF[1:0], IM[1:0]}

write_reg(26) # [223:216] border
# total: 28 bytes

if args.plain:
    o.close()
    exit(0)

# the standard Spec256 palette (sp256.pal of GZX, colour 255 white)
DEFAULT_PALETTE = bytes.fromhex(
    "00000000009b172fab3763bb5b93cb83bfdbb3e3ebe7ffffb70000bf1717cb3333d35353df7777e79b9bf3c3c3ffefef"
    "00372307533b176f532f8b734fa78f73c3b39fdfd3d3fff7ff4b00ff771fff9f3fffbf63ffdb83ffeba7fff7c7ffffeb"
    "672b007b3b0b8f4f23a7673bbb835bd39f7fe7bfa7ffe7d77f004b8f135ba32b73b34b8bc76fa3d79bbfebcbdfffffff"
    "0b23731b33872f479b4b63af677fc38b9fd7b3bfebdfe7ff337f23438f1f53a31f6bb31b87c717abd70fcfeb07ffff00"
    "c30000af1700bb3300c75300d77b00e3a300efcf00ffff004b4b336363477b7b5b979773afaf8bcbcba3e3e3bfffffdb"
    "0000004343436363637f7f7f9f9f9fbbbbbbdbdbdbfbfbfba36f57af7f63bb8f6fc7a37bd7b78be3c79befdbabffefbb"
    "00abcb17b3cf33bbd74fc7df6bcfe38bdbebafe7f3d3f3fb00d30017d7172fdf2f4be34b67eb6783ef83a3f7a3c3ffc3"
    "4f4f675f5f7b73738f8b8ba79f9fbbb7b7d3cbcbe7e7e7ff8b83009b930faba323bbb33bcbc353dbd773ebe793fffbbb"
    "3757573b6f6f3b87873b9f9f33b7b727cfcf17e7e707ffff00000000001b00003700004f00006b0000870000a30000bf"
    "0000001b00003700004f00006b0000870000a30000bf00000000001b001b3700374f004f6b006b870087a300a3bf00bf"
    "000000001b00003700004f00006b0000870000a30000bf00000000001b1b003737004f4f006b6b00878700a3a300bfbf"
    "0000001b1b003737004f4f006b6b00878700a3a300bfbf000000001b1b1b3737374f4f4f6b6b6b878787a3a3a3bfbfbf"
    "00000000000000000000000000000000000000000000000000003f00005700007300008f0000ab0000c70000e30000ff"
    "3f00005700007300008f0000ab0000c70000e30000ff00003f003f5700577300738f008fab00abc700c7e300e3ff00ff"
    "003f00005700007300008f0000ab0000c70000e30000ff00000000002323004747006b6b008f8f00b3b300dbdb00ffff"
    "3f3f005757007373008f8f00abab00c7c700e3e300ffff003f3f3f5757577373738f8f8fabababc7c7c7e3e3e3ffffff"
)

# games that want colour 0 and 0xFF drawn from the palette (ZX-Poly's spec256appbase.txt)
PLAIN_00_FF = ("booty", "cybernoid_ii256", "eaglesns", "rene256")

def read_palette(name):
    data = file_read(name, "rb")
    if len(data) == 768:
        return bytes(data)
    values = [int(v) for v in data.decode("ascii", "replace").split() if v.isdigit()]   # GZX: 768 numbers
    if len(values) != 768 or max(values) > 255:
        print(f"{name}: not a palette of 768 bytes or 768 numbers")
        exit(1)
    return bytes(values)

cfg = {}
rules = []
cfg_filename = companion(".cfg")
if cfg_filename:
    for line in file_read(cfg_filename, "rb").decode("ascii", "replace").splitlines():
        line = line.strip()
        if "=" not in line:
            continue
        key, value = [x.strip() for x in line.split("=", 1)]
        if len(key) > 3 and key[:2].isdigit() and key[2] == ":":    # "NN: addr=VVh"
            v = value.lower()
            val = int(v[:-1], 16) if v.endswith("h") else int(v)
            rules.append((int(key[:2]), int(key[3:].strip()), val))
        else:
            try:
                cfg[key] = int(value)
            except ValueError:
                pass
if len(rules) > 16:
    print(f"{cfg_filename}: {len(rules)} background rules, the core takes 16")
    exit(1)

backgrounds = {}
for n in range(100):
    b = companion(".b%02d" % n)
    if b:
        data = file_read(b, "rb")
        if len(data) != 64000:
            print(f"{b}: a background is 320x200 bytes, got {len(data)}")
            exit(1)
        backgrounds[n] = data
bkg_count = max(backgrounds) + 1 if backgrounds else 0
for n, _, _ in rules:
    if n not in backgrounds:
        print(f"{cfg_filename}: a rule shows background {n}, there is no such file")
        exit(1)

gfb_filename = companion(".gfb")
rom_planes = None
if gfb_filename:
    gfb = file_read(gfb_filename, "rb")
    if len(gfb) < 131072:
        print(f"{gfb_filename}: ROM graphics are 131072 bytes, got {len(gfb)}")
        exit(1)
    rom_planes = planes(gfb[:131072], 16384)

pal_filename = companion(".pal")
palette = read_palette(pal_filename) if pal_filename else DEFAULT_PALETTE

if "Paper00InkFF" in cfg:
    paper00inkff = cfg["Paper00InkFF"] != 0
elif sna_filename.stem.lower() in PLAIN_00_FF:
    paper00inkff = False
else:
    paper00inkff = not backgrounds      # on unless there is a background
hide_same = cfg.get("HideSameInkPaper", 1) != 0
bk_over_ff = cfg.get("BkOverFF", 0) != 0
up_mixed = cfg.get("UpColorsMixed", 64)
down_mixed = cfg.get("DownColorsMixed", 0)

flags = (1 if rom_planes else 0) | (2 if paper00inkff else 0) | (4 if hide_same else 0) | (8 if bk_over_ff else 0)
o.write(b"K256")
o.write(bytes([1, flags, up_mixed & 0xFF, down_mixed & 0xFF, bkg_count, len(rules),
               min(backgrounds) if backgrounds else 0xFF, 0, 0, 0, 0, 0]))
o.write(palette)
for i in range(16):
    if i < len(rules):
        n, addr, val = rules[i]
        o.write(bytes([n, addr & 0xFF, addr >> 8, val]))
    else:
        o.write(bytes([0xFF, 0, 0, 0]))
if rom_planes:
    o.write(rom_planes)
for n in range(bkg_count):
    b = backgrounds.get(n, bytes(64000))
    for y in range(4, 196):
        o.write(b[y * 320 + 32 : y * 320 + 288])
o.close()

print(f"palette: {pal_filename or 'standard'}, cfg: {cfg_filename or 'none'}, ROM graphics: {gfb_filename or 'none'}, "
      f"backgrounds: {sorted(backgrounds)}, rules: {len(rules)}")
print(f"Paper00InkFF={int(paper00inkff)} HideSameInkPaper={int(hide_same)} BkOverFF={int(bk_over_ff)} "
      f"UpColorsMixed={up_mixed} DownColorsMixed={down_mixed}")
