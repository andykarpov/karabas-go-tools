#!/bin/env python3

#########################################################
# Karabas Go Spec256 snapshot convertor v1.4            #
#                                                       #
# (c) 2026 Andy Karpov <andy.karpov@gmail.com>          #
#########################################################

# NAME.EZX (a 256-colour game saved by EmuZWin) is first split into the files below, see ezx_extract.
# NAME.SNA + NAME.GFX (+ NAME.PAL, NAME.CFG, NAME.GFB, NAME.GFA, NAME.GF0..GF7, NAME.B00..B99, any
# case) -> NAME.256. The SNA is a 48K one (49179 bytes) or a 128K one (131103 or 147487 bytes).
#   49152    the RAM of 4000-FFFF: the banks 5, 2, 0 (a 128K snapshot with another bank at C000 has
#            that bank in the 128K block)
#   393216   the 8 planes of each address (bit k of plane p = bit p of the colour of pixel k)
#   28       the registers (below)
#   the extension (not with --plain), little endian:
#   0  4     "K256"
#   4  1     version: 1, 2 with flag 4 or 5 (a core of version 1 leaves the extension out)
#   5  1     flags: 0 the ROM planes follow, 1 Paper00InkFF, 2 HideSameInkPaper, 3 BkOverFF,
#            4 the planes of the ROM 0 follow those of the ROM 1 (NAME.GFA, the 128 menu ROM),
#            5 the 128K block follows the backgrounds
#   6  1     UpColorsMixed
#   7  1     DownColorsMixed
#   8  1     number of backgrounds (the highest Bnn + 1; a missing one is colour 0)
#   9  1     number of rules (up to 16)
#   10 1     the background shown first: the one of the first rule that matches the snapshot, else
#            the lowest Bnn there is; 0xFF: none
#   11 2     the rules that match the snapshot (bit n: rule n), the core starts with them (it loads the
#            RAM before it knows the rules)
#   13 3     the pages (high bytes) of the tables of reversed bytes in the RAM, 0: none. Games flip
#            their sprites with T[v] = reverse(v) (LD L,byte / LD A,(HL)); the lanes of the core read
#            those tables at the address of their own L, every other table at the address of the main
#            CPU (a mask must be the same in every lane).
#   16 768   the palette, RGB (NAME.PAL or the standard Spec256 one)
#   784 64   16 rules: background, address (2), value: background n while the byte at the address is
#            the value (the "NN: addr=VVh" lines of the .CFG; the first one that matches)
#   848      131072 the ROM planes (NAME.GFB, the 16K of the 48K ROM, the ROM 1 of the 128K), if flag 0;
#            the core reads a word of 0 as the ROM byte (a .GFB colours the font and leaves the rest 0)
#   then     131072 the planes of the ROM 0 (NAME.GFA), if flag 4 (flag 0 then too: a .GFB of 0)
#   then     49152 per background: the 256x192 paper of the 320x200 picture (x 32..287, y 4..195)
#   then     the 128K block, if flag 5: 8 bytes (#7FFD of the snapshot, 7 reserved), then the banks
#            1, 3, 4, 6, 7, each 16384 bytes of RAM and 131072 of planes
# The planes of a 128K bank (as ZX-Poly): NAME.GFn, else its part of NAME.GFX (the banks 5, 2 and the
# one at C000 in the snapshot), else the bank itself in every plane (not coloured). The registers of a
# 128K snapshot: its PC, IFF1 = IFF2; of a 48K one: PC 0072 (a RETN in the ROM) pops the PC.
# The settings and their defaults are those of ZX-Poly / ZxNextEmu (karabas-go-core-spec256
# docs/SIMD.md, section 7).

import argparse
import struct
import sys
import os
import tempfile
import shutil
import atexit
from pathlib import Path


# UCL NRV2E with an 8-bit bit buffer (the decompressor of UCL n2e_d.c): the compression of EZX
def nrv2e_decompress(src, ilen):
    dst = bytearray()
    bb = 0
    def getbit():
        nonlocal bb, ilen
        if bb & 0x7F:
            bb = bb * 2
        else:
            bb = src[ilen] * 2 + 1
            ilen += 1
        return (bb >> 8) & 1
    last_m_off = 1
    while True:
        while getbit():
            dst.append(src[ilen])
            ilen += 1
        m_off = 1
        while True:
            m_off = m_off * 2 + getbit()
            if getbit():
                break
            m_off = (m_off - 1) * 2 + getbit()
        if m_off == 2:
            m_off = last_m_off
            m_len = getbit()
        else:
            m_off = ((m_off - 3) * 256 + src[ilen]) & 0xFFFFFFFF
            ilen += 1
            if m_off == 0xFFFFFFFF:
                break
            m_len = (m_off ^ 0xFFFFFFFF) & 1
            m_off = (m_off >> 1) + 1
            last_m_off = m_off
        if m_len:
            m_len = 1 + getbit()
        elif getbit():
            m_len = 3 + getbit()
        else:
            m_len = 1
            while True:
                m_len = m_len * 2 + getbit()
                if getbit():
                    break
            m_len += 3
        m_len += m_off > 0x500
        pos = len(dst) - m_off
        if pos < 0:
            raise ValueError("EZX: a match before the start")
        for i in range(m_len + 1):
            dst.append(dst[pos + i])
    return bytes(dst), ilen

# EZX of EmuZWin 2.4 (spec256/EZX.md, from EZXFormat_Eng.htm of EmuZWin_Addons.zip): "Emuz", ROM 0, ROM 1, the RAM banks
# 0..7, Lock7FFD, the registers, the AY, the tape, then chunks (name, length, data). Compressed: "EZX",
# then blocks of a length (4 bytes) and NRV2E data. The chunks of the 256 colours:
#   GFXM  bank (0..7 RAM, 16 the ROM 0, 17 the ROM 1, 18 TR-DOS) + 131072 bytes, as a .GFX
#   GFXB  number, width, height (320x200 or 256x192), the pixels
#   GFXP  number, 768 bytes RGB
#   GFXC  the text of the .CFG
# Writes NAME.SNA (48K if Lock7FFD, else 128K), NAME.GFX (the banks 5, 2 and the one at C000), NAME.GFn
# (the other banks of a 128K), NAME.GFA / .GFB (the ROMs), NAME.CFG, NAME.Bnn, NAME.PAL into outdir; a
# bank without GFXM gets the planes of the bank itself (not coloured). Returns the path of the SNA.
def ezx_extract(path, outdir, overwrite=True):
    f = open(path, "rb").read()
    if f[:4] == b"Emuz":
        d = f
    elif f[:3] == b"EZX":
        d = b""
        p = 3
        while p < len(f):
            n = struct.unpack_from("<I", f, p)[0]
            block, end = nrv2e_decompress(f, p + 4)
            if end != p + 4 + n:
                print(f"{path}: a compressed block of {n} bytes ends at {end - p - 4}")
                exit(1)
            d += block
            p = end
    else:
        print(f"{path}: not an EZX file")
        exit(1)
    if d[:4] != b"Emuz":
        print(f"{path}: no Emuz after unpacking")
        exit(1)
    rom = [d[4 + 16384 * i:4 + 16384 * (i + 1)] for i in range(2)]
    ram = [bytearray(d[4 + 16384 * (2 + i):4 + 16384 * (3 + i)]) for i in range(8)]
    p = 4 + 16384 * 10
    lock = d[p]
    st = d[p + 1:p + 44]            # TSpecState, 43 bytes
    af, bc, de, hl, ix, iy, af_, bc_, de_, hl_, pc, sp = struct.unpack_from("<12H", st, 0)
    reg_i, reg_r, _, iff1, iff2, _, im = st[24:31]
    bank_rom, bank_ram, bank_video, border = st[35:39]
    p += 1 + 43 + 17 + 4 + 30          # Lock7FFD, TSpecState, TSoundChipState, ReleaseDescriptor, TTapeData
    gfxm, bkgs, pals, cfg = {}, {}, {}, None
    while p + 8 <= len(d):
        name = d[p:p + 4]
        n = struct.unpack_from("<I", d, p + 4)[0]
        data = d[p + 8:p + 8 + n]
        if name == b"GFXM":
            gfxm[data[0]] = data[1:]
        elif name == b"GFXB":
            num, w, h = struct.unpack_from("<HHH", data, 0)
            pix = data[6:6 + w * h]
            if (w, h) == (256, 192):    # into the middle of 320x200, as a .Bnn
                b = bytearray(64000)
                for y in range(192):
                    b[(y + 4) * 320 + 32:(y + 4) * 320 + 288] = pix[y * 256:(y + 1) * 256]
                pix = bytes(b)
            elif (w, h) != (320, 200):
                print(f"{path}: a background of {w}x{h}")
                exit(1)
            bkgs[num] = pix
        elif name == b"GFXP":
            pals[struct.unpack_from("<H", data, 0)[0]] = data[2:770]
        elif name == b"GFXC":
            cfg = data
        p += 8 + n
    if bank_rom > 1:
        print(f"{path}: saved with the ROM {bank_rom} paged in (TR-DOS / IF1): not supported")
        exit(1)
    if bank_video:
        print(f"{path}: the shadow screen is shown: not supported")
    for i, name in ((0, "128_0.rom"), (1, "82.rom")):
        mine = Path(__file__).absolute().parent.parent / "roms" / name   # src/roms of the core (src/games/spec256.py)
        if mine.is_file() and open(mine, "rb").read() != rom[i] and (i == 1 or not lock):
            print(f"{path}: the ROM {i} differs from {name}")
    stem = Path(path).stem
    out = Path(outdir)
    def put(ext, data):
        target = out / (stem + ext)
        if target.exists() and not overwrite:
            print(f"{target}: exists, not written")
        else:
            open(target, "wb").write(data)
    def gfx_of(n):      # the GFXM of a bank, else the bank not coloured (bit k of b: colour FF or 00)
        if n in gfxm:
            return gfxm[n]
        return bytes(0xFF if b >> k & 1 else 0 for b in ram[n] for k in range(8))
    iff = 4 if iff1 else 0
    if lock:    # 48K: the PC on the stack, as a SNA
        sp = (sp - 2) & 0xFFFF
        if sp < 0x4000 or sp == 0xFFFF:
            print(f"{path}: the stack (SP {sp + 2:04X}) is not in the RAM, no place for the PC")
            exit(1)
        ram48 = ram[5] + ram[2] + ram[bank_ram]
        ram48[sp - 0x4000:sp - 0x4000 + 2] = bytes([pc & 0xFF, pc >> 8])
    hdr = bytes([reg_i]) + struct.pack("<4H", hl_, de_, bc_, af_) + struct.pack("<5H", hl, de, bc, iy, ix) + \
        bytes([iff, reg_r]) + struct.pack("<2H", af, sp) + bytes([im, border & 7])
    if lock:
        put(".SNA", hdr + bytes(ram48))
    else:
        p7ffd = bank_ram | (bank_video << 3) | (0x10 if bank_rom else 0)
        rest = b"".join(ram[n] for n in range(8) if n not in (5, 2, bank_ram))
        put(".SNA", hdr + ram[5] + ram[2] + ram[bank_ram] + struct.pack("<H", pc) + bytes([p7ffd, 0]) + rest)
        for n in sorted(gfxm):
            if n < 8 and n not in (5, 2, bank_ram):
                put(".GF%d" % n, gfxm[n])
    put(".GFX", gfx_of(5) + gfx_of(2) + gfx_of(bank_ram))
    if 16 in gfxm:
        put(".GFA", gfxm[16])
    if 17 in gfxm:
        put(".GFB", gfxm[17])
    if cfg is not None:
        put(".CFG", cfg)
    for n, pix in bkgs.items():
        if n < 100:
            put(".B%02d" % n, pix)
    if pals:
        put(".PAL", pals[min(pals)])
    print(f"{path}: {'48K' if lock else '128K'}, PC={pc:04X}, GFX banks {sorted(gfxm)}, backgrounds {sorted(bkgs)}, "
          f"palettes {sorted(pals)}")
    return out / (stem + ".SNA")


msg = "Karabas Go Spec256 snapshot convertor v1.4"
parser = argparse.ArgumentParser(description = msg)
parser.add_argument('sna_file', help='NAME.SNA, or NAME.EZX of EmuZWin')
parser.add_argument('--plain', action='store_true', help='no extension (the format of v1.2)')
parser.add_argument('--extract', action='store_true', help='NAME.EZX: only write its files (SNA, GFX, ...) next to it, '
                    'keeping the files there')
args = parser.parse_args()

sna_filename = Path(args.sna_file)
outfile = sna_filename.with_suffix(".256")
if sna_filename.suffix.lower() == ".ezx":
    if args.extract:
        ezx_extract(sna_filename, sna_filename.parent, overwrite=False)
        exit(0)
    tmp = tempfile.mkdtemp(prefix="spec256_")
    atexit.register(shutil.rmtree, tmp, True)
    sna_filename = ezx_extract(sna_filename, tmp)

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
sna_all = file_read(sna_filename, "rb")
regs = sna_all[:27]
sna = sna_all[27:49179]     # the RAM 4000-FFFF as the snapshot has it paged
gfx = file_read(gfx_filename, "rb")
gfx_size = len(gfx)

if len(sna_all) not in (49179, 131103, 147487):
    print(f"SNA size should be 49179 (48K), 131103 or 147487 (128K) bytes, got {len(sna_all)}")
    exit(1)
is128 = len(sna_all) != 49179
if is128 and args.plain:
    print("a 128K snapshot needs the extension (no --plain)")
    exit(1)

if gfx_size != 393216:
    print(f"GFX size should be exactly 393216 bytes, got {gfx_size}")
    exit(1)

print(f"Converting {sna_filename} + {gfx_filename} into {outfile} ({'128K' if is128 else '48K'})")
o = open(outfile, "wb")

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

# the banks of the 128K: RAM and planes
def plain(ram):
    return bytes(b for b in ram for _ in range(8))

if is128:
    pc128 = sna_all[49179] | sna_all[49180] << 8
    p7ffd = sna_all[49181]
    if sna_all[49182]:
        print("the snapshot was taken in TR-DOS: not supported")
        exit(1)
    top = p7ffd & 7
    bank_ram = {5: sna[0:16384], 2: sna[16384:32768], top: sna[32768:49152]}
    rest = sna_all[49183:]
    for i, n in enumerate(b for b in range(8) if b not in (5, 2, top)):
        bank_ram[n] = rest[i * 16384:(i + 1) * 16384]
    # the parts of the .GFX first (ZX-Poly: 5, 2, then the one at C000 if it is neither), a .GFn over them
    bank_gfx = {}
    for i, n in enumerate((5, 2, top)):
        if n not in bank_gfx:
            bank_gfx[n] = gfx[i * 131072:(i + 1) * 131072]
    for n in range(8):
        f = companion(".gf%d" % n)
        if f:
            data = file_read(f, "rb")
            if len(data) != 131072:
                print(f"{f}: the planes of a bank are 131072 bytes, got {len(data)}")
                exit(1)
            bank_gfx[n] = data
    bank_planes = {n: planes(bank_gfx[n], 16384) if n in bank_gfx else plain(bank_ram[n]) for n in range(8)}
    print(f"128K: #7FFD={p7ffd:02X}, PC={pc128:04X}, banks with planes: {sorted(bank_gfx)}")
    o.write(bank_ram[5] + bank_ram[2] + bank_ram[0])
    o.write(bank_planes[5] + bank_planes[2] + bank_planes[0])
else:
    o.write(sna)
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
if is128:
    o.write(bytes([pc128 & 0xFF, pc128 >> 8]))   # [79:64] PC of the 128K snapshot
else:
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

# {IFF2, IFF1}: the RETN of a 48K snapshot sets IFF1 from IFF2, a 128K one starts at its PC
iff = (3 if is128 else 2) if regs[19] & 0x04 else 0
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
    # a .GFB colours a part of the ROM (the font); the rest is 0, which the core reads as the ROM itself.
    # One that is 0 everywhere (Renegade, Scooby Doo) is left out.
    if not any(rom_planes):
        print(f"{gfb_filename}: all 0, not used")
        rom_planes = None
        gfb_filename = None

# the ROM 0 of the 128K (NAME.GFA): only a 128K game can page it in (a 48K one runs with #7FFD locked)
gfa_filename = companion(".gfa")
rom0_planes = None
if gfa_filename:
    gfa = file_read(gfa_filename, "rb")
    if len(gfa) < 131072:
        print(f"{gfa_filename}: ROM graphics are 131072 bytes, got {len(gfa)}")
        exit(1)
    rom0_planes = planes(gfa[:131072], 16384)
    if not any(rom0_planes) or not is128:
        print(f"{gfa_filename}: {'all 0' if is128 else 'a 48K game'}, not used")
        rom0_planes = None
        gfa_filename = None
    elif not rom_planes:
        rom_planes = bytes(131072)      # the ROM 1 itself

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

flags = (1 if rom_planes else 0) | (2 if paper00inkff else 0) | (4 if hide_same else 0) | (8 if bk_over_ff else 0) | \
        (16 if rom0_planes else 0) | (32 if is128 else 0)
o.write(b"K256")
# the rules against the RAM of the snapshot (4000-FFFF)
match = 0
first = min(backgrounds) if backgrounds else 0xFF
for i, (n, addr, val) in enumerate(rules):
    if 0x4000 <= addr and sna[addr - 0x4000] == val:
        if not match:
            first = n
        match |= 1 << i
# the tables of reversed bytes: 256-byte aligned in 4000-FFFF
REVERSE = bytes(int("{:08b}".format(i)[::-1], 2) for i in range(256))
pages = [0x40 + p for p in range(192) if sna[p * 256:(p + 1) * 256] == REVERSE]
if is128:   # the other banks at C000
    for n in range(8):
        pages += [0xC0 + p for p in range(64) if bank_ram[n][p * 256:(p + 1) * 256] == REVERSE]
pages = sorted(set(pages))[:3]
pages += [0] * (3 - len(pages))
o.write(bytes([2 if flags & 0x30 else 1, flags, up_mixed & 0xFF, down_mixed & 0xFF, bkg_count, len(rules),
               first, match & 0xFF, match >> 8] + pages))
o.write(palette)
for i in range(16):
    if i < len(rules):
        n, addr, val = rules[i]
        o.write(bytes([n, addr & 0xFF, addr >> 8, val]))
    else:
        o.write(bytes([0xFF, 0, 0, 0]))
if rom_planes:
    o.write(rom_planes)
if rom0_planes:
    o.write(rom0_planes)
for n in range(bkg_count):
    b = backgrounds.get(n, bytes(64000))
    for y in range(4, 196):
        o.write(b[y * 320 + 32 : y * 320 + 288])
if is128:
    o.write(bytes([p7ffd, 0, 0, 0, 0, 0, 0, 0]))
    for n in (1, 3, 4, 6, 7):
        o.write(bank_ram[n])
        o.write(bank_planes[n])
o.close()

print(f"palette: {pal_filename or 'standard'}, cfg: {cfg_filename or 'none'}, ROM graphics: {gfb_filename or 'none'}, "
      f"ROM 0 graphics: {gfa_filename or 'none'}, "
      f"backgrounds: {sorted(backgrounds)}, rules: {len(rules)}")
print(f"tables of reversed bytes: {['%02X00' % p for p in pages if p]}")
print(f"Paper00InkFF={int(paper00inkff)} HideSameInkPaper={int(hide_same)} BkOverFF={int(bk_over_ff)} "
      f"UpColorsMixed={up_mixed} DownColorsMixed={down_mixed}")
