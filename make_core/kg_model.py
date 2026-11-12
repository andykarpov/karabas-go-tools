# Reads a core file of either format into one model (a dict), for kg_compare.py and kg1_to_json.py:
# kgo1 (.kg1 / .kg2 / .kg3, one board) and the view of one board of a kgo2 file (.kg, docs/kgo2.md).
# The model holds what the firmware uses, in the same form for both formats: option values as
# option positions, extensions without dots, kgo1 padding stripped.

import re
import struct

OSD_TYPES = ["S", "N", "T", "H", "P", "F", "FL", "M", "-"]
BOARDS = {"go": 1, "mini": 2, "minig": 3}
CORE_TYPES = {0: "boot", 1: "osd", 2: "fileloader", 255: "hidden"}


def norm_exts(text):
    # as the firmware reads a list: commas, semicolons or spaces between, dots dropped
    out = []
    for e in re.split(r"[,;\s]+", text):
        e = e.strip().lstrip(".").lower()
        if e:
            out.append(e)
    return out


def norm_buttons(b):
    # as the firmware takes them (read_buttons / set_buttons): press = action, or core (0) when
    # not an action; hold only with an action and a hold time 1..254, else none
    out = []
    for i in range(0, len(b), 3):
        press, hold, t = b[i], b[i + 1], b[i + 2]
        out.append((press if press < 8 else 0, (hold, t) if hold < 8 and 0 < t < 255 else None))
    return out


def _str(b):
    # a kgo1 field: up to the first NUL / FF, spaces around it dropped
    for stop in (b"\0", b"\xff"):
        i = b.find(stop)
        if i >= 0:
            b = b[:i]
    return b.decode("ascii", "replace").strip()


def read_kgo1(data):
    be32 = lambda o: struct.unpack_from(">I", data, o)[0]
    m = {"format": 1}
    m["core"] = {
        "id": _str(data[4:36]), "name": _str(data[36:68]), "build": _str(data[68:76]),
        "visible": data[76], "order": data[77], "type": data[78], "eeprom_bank": data[79],
        "rtc_mode": data[88], "spi_freq": data[185], "drives": "", "link": 1,
    }
    m["loader"] = {"dir": _str(data[89:121]), "exts": norm_exts(_str(data[153:185])),
                   "save_dir": _str(data[186:218])}
    m["buttons"] = norm_buttons(data[218:236])
    m["eeprom"] = bytes(data[256:512])
    m["matrix"] = bytes(data[768:1024])
    blen, rlen = be32(80), be32(84)
    m["bitstream"] = bytes(data[1024:1024 + blen])
    roms, p, end = [], 1024 + blen, 1024 + blen + rlen
    while p < end:
        ln, addr = be32(p), be32(p + 4)
        n = ln & 0x7FFFFFFF
        roms.append({"address": addr, "external": bool(ln >> 31), "data": bytes(data[p + 8:p + 8 + n])})
        p += 8 + n
    m["roms"] = roms
    items, p = [], end
    count = data[p]
    p += 1
    for i in range(count):
        t = OSD_TYPES[data[p]]
        it = {"type": t, "flags": data[p + 1], "name": data[p + 2:p + 18].decode("ascii").rstrip(), "index": i}
        dflt = data[p + 18]
        p += 19
        if t in ("F", "FL"):
            slot = data[p]
            it["slot"] = slot & 0x7F
            it["autoload"] = bool(slot & 0x80)
            it["physical"] = bool(it["flags"] & 1)
            it["exts"] = norm_exts(_str(data[p + 1:p + 257]))
            it["dir"] = _str(data[p + 257:p + 513])
            f = _str(data[p + 513:p + 769])
            it["files"] = [f] if f else []
            it["options"] = []
            p += 769
        else:
            n = data[p]
            it["options"] = [data[p + 1 + 16 * j:p + 17 + 16 * j].decode("ascii").rstrip() for j in range(n)]
            p += 1 + 16 * n
        hk = data[p:p + 16].decode("ascii")
        it["keys"] = bytes(data[p + 16:p + 18])
        page, cond_item, cond = data[p + 18], data[p + 19], data[p + 20]
        p += 21
        if t == "P":
            it["name"] = (it["name"].ljust(16) + hk).rstrip()
            it["hotkey"] = ""
        else:
            it["hotkey"] = hk.strip() if t not in ("M", "-") else ""
        it["page"] = page
        it["open"] = dflt if t == "M" else 0
        it["default"] = 0 if t == "M" else dflt
        it["cond"] = (cond_item, cond & 0xC0, cond & 0x3F) if cond_item else (0, 0, 0)
        if t not in ("F", "FL"):
            it["flags"] = 0
        items.append(it)
    m["osd"] = items
    return m


def read_kgo2(data, board):
    le16 = lambda o: struct.unpack_from("<H", data, o)[0]
    sig, version, _, hsize, count, esize, mask = struct.unpack_from("<4sBBHHHH", data, 0)
    if sig != b"kgo2":
        raise ValueError("not a kgo2 file")
    bit = 1 << BOARDS[board]
    sec = {}
    for i in range(count):
        t, bm, ofs, ln = struct.unpack_from("<HHII", data, hsize + i * esize)
        if bm & bit:
            sec[t] = data[ofs:ofs + ln]
    if 9 not in sec and 10 not in sec:
        return None
    strings = sec[1]

    def s(ref):
        return strings[ref:strings.index(b"\0", ref)].decode("utf-8")

    m = {"format": 2}
    c = sec[2]
    csize, i, n, b, typ, vis, order, rtc, eep, spi, drv = struct.unpack_from("<HHHHBBBBBBH", c, 0)
    m["core"] = {"id": s(i), "name": s(n), "build": s(b), "visible": vis, "order": order, "type": typ,
                 "eeprom_bank": eep, "rtc_mode": rtc, "spi_freq": spi, "drives": s(drv),
                 "link": c[16] if csize > 16 else 1}
    m["loader"] = {"dir": "", "exts": [], "save_dir": ""}
    m["loader_files"] = []
    if 3 in sec:
        ld = sec[3]
        _, d, e, sd, flags, nf, fo = struct.unpack_from("<HHHHBBH", ld, 0)
        m["loader"] = {"dir": s(d), "exts": norm_exts(s(e)), "save_dir": s(sd)}
        m["loader_files"] = [s(struct.unpack_from("<H", ld, fo + 2 * k)[0]) for k in range(nf)]
    bt = sec.get(5)
    m["buttons"] = norm_buttons(bytes(bt[1:19]) if bt else b"\xff" * 18)
    m["eeprom"] = bytes(sec[7]) if 7 in sec else b"\xff" * 256
    m["matrix"] = bytes(sec[6]) if 6 in sec else bytes(256)
    m["bitstream"] = bytes(sec[9] if 9 in sec else sec[10])
    roms, r, p = [], sec.get(8, b""), 0
    while p < len(r):
        ln, addr = struct.unpack_from("<II", r, p)
        n = ln & 0x7FFFFFFF
        roms.append({"address": addr, "external": bool(ln >> 31), "data": bytes(r[p + 8:p + 8 + n])})
        p += 8 + n
    m["roms"] = roms
    items = []
    if 4 in sec:
        o = sec[4]
        cnt, isize, _ = struct.unpack_from("<HHI", o, 0)
        raw = []
        for k in range(cnt):
            r0 = 8 + k * isize
            f = struct.unpack_from("<14BH", o, r0)
            key, name, hk, exts, d, oo, fo, hko = struct.unpack_from("<8H", o, r0 + 16)
            typ, flags, index, page, opn, ci, cf, cv, dflt, slot, hm, hkk, no, nf, _ = f
            opts = [struct.unpack_from("<HHB", o, oo + 8 * j) for j in range(no)]
            hks = [struct.unpack_from("<BBH", o, hko + 4 * j) for j in range(no)] if hko else []
            raw.append((typ, flags, index, page, opn, ci, cf, cv, dflt, slot, hm, hkk, opts, nf, fo, key, name, hk, exts, d, hks))
        values = [[ov for _, _, ov in r[12]] for r in raw]
        for k, (typ, flags, index, page, opn, ci, cf, cv, dflt, slot, hm, hkk, opts, nf, fo, key, name, hk, exts, d, hks) in enumerate(raw):
            t = OSD_TYPES[typ]
            it = {"type": t, "name": s(name), "key": s(key), "index": index if index != 255 else None,
                  "options": [s(on) for _, on, _ in opts], "option_keys": [s(ok) for ok, _, _ in opts],
                  "option_values": values[k], "keys": bytes([hm, hkk]), "page": page,
                  "open": opn if t == "M" else 0, "hotkey": s(hk), "flags": 0,
                  "radio": bool(flags & 8), "option_hotkeys": [(bytes([h[0], h[1]]), s(h[2])) for h in hks]}
            it["default"] = values[k].index(dflt) if dflt in values[k] else (dflt if not opts else 0)
            if ci:
                cvals = values[ci - 1]
                it["cond"] = (ci, cf & 0xC0, cvals.index(cv) if cv in cvals else 0x3F)
            else:
                it["cond"] = (0, 0, 0)
            if t in ("F", "FL"):
                it["slot"] = slot
                it["autoload"] = bool(flags & 4)
                it["physical"] = bool(flags & 1)
                it["readonly"] = bool(flags & 2)
                it["exts"] = norm_exts(s(exts))
                it["dir"] = s(d)
                it["files"] = [s(struct.unpack_from("<H", o, fo + 2 * j)[0]) for j in range(nf)]
                it["flags"] = flags & 1
            items.append(it)
    m["osd"] = items
    return m


def read_file(path, board=None):
    data = open(path, "rb").read()
    if data[:4] == b"kgo2":
        if board is None:
            raise ValueError("%s: kgo2, give a board" % path)
        return read_kgo2(data, board)
    return read_kgo1(data)
