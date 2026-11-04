#!/bin/env python3

#########################################################
# Karabas Go Core Generator v1.0                        #
#                                                       #
# (c) 2023, 2024 Andy Karpov <andy.karpov@gmail.com>    #
#########################################################

import json
import re
import struct
import argparse
import sys
import os
from types import SimpleNamespace

msg = "Karabas Go binary core maker v1.0"
parser = argparse.ArgumentParser(description = msg)
parser.add_argument('json_file')
parser.add_argument('output_file', help = "a .kg file: kgo2 (docs/kgo2.md), else kgo1 (.kg1 / .kg2 / .kg3)")
parser.add_argument('--boards', help = "kgo2: the boards to take bitstreams of (comma separated, default: all of the json); "
                    "the other boards keep the bitstream of an existing output file")
args = parser.parse_args()
filename = args.json_file
outfile = args.output_file

def file_check(name):
    if not os.path.isfile(name):
        print("Unable to read file ", name)
        exit(1)    

def file_read(name, mode = "r"):
    file_check(name)
    f = open(name, mode)
    data = f.read()
    f.close()
    return data    

# rom payloads: the rom data for embedded roms, the file name (on the sd card) for external ones
def rom_payload(rom):
    if hasattr(rom, "external") and rom.external:
        return rom.filename.encode("ascii")
    return file_read(rom.filename, "rb")

# on-board button actions (karabas-go-firmware, input_tick_buttons):
# core: press / release go to the core (CMD_BTN), the default
# none: ignored, osd: toggle the osd, menu: back to the boot core, reload: load the core again,
# bootsel: reboot the mcu into BOOTSEL, msc: reboot into USB mass storage,
# msc2: the same with the second SD card (the slot of the FPGA)
btn_actions = { "core": 0, "none": 1, "osd": 2, "menu": 3, "reload": 4, "bootsel": 5, "msc": 6, "msc2": 7 }
BUTTONS = 6

def btn_action(name, value):
    if value not in btn_actions:
        print("Unknown action '%s' of button %s, expected one of %s" % (value, name, ", ".join(btn_actions)))
        exit(1)
    return btn_actions[value]

# "buttons": {"btn1": "core", "btn2": {"press": "osd", "hold": "menu", "hold_ms": 3000}}
# 3 bytes per button: press action, hold action, hold time in 100 ms units; 0xFF = not set
# (press: core, no hold)
def buttons_bytes(d):
    out = bytearray(b'\xFF' * (3 * BUTTONS))
    buttons = vars(d.buttons) if hasattr(d, "buttons") else {}
    for name, b in buttons.items():
        if not name.startswith("btn") or not name[3:].isdigit() or not 1 <= int(name[3:]) <= BUTTONS:
            print("Unknown button '%s', expected btn1..btn%d" % (name, BUTTONS))
            exit(1)
        i = (int(name[3:]) - 1) * 3
        if isinstance(b, str):
            out[i] = btn_action(name, b)
            continue
        if hasattr(b, "press"):
            out[i] = btn_action(name, b.press)
        if hasattr(b, "hold"):
            hold_ms = getattr(b, "hold_ms", 2000)
            if not 100 <= hold_ms <= 25400:
                print("hold_ms of button %s must be 100..25400" % name)
                exit(1)
            out[i + 1] = btn_action(name, b.hold)
            out[i + 2] = (hold_ms + 50) // 100
    return bytes(out)

# LED matrix settings (karabas-go-firmware, lib/KarabasCommon kg_matrix.h), 256 bytes at 768:
# "matrix": "core"
# "matrix": {"mode": "scroll", "text": "NES {build}", "color": "rainbow", "step_ms": 60,
#            "repeat": 2, "then": "effect", "effect": "fire", "brightness": 6}
# "matrix": {"mode": "image", "frames": [["GGGG............", ...8 rows], ...up to 4], "step_ms": 200}
matrix_modes = { "core": 0, "scroll": 1, "effect": 2, "image": 3, "blank": 4 }
matrix_then = { "core": 0, "effect": 2, "blank": 4 }
matrix_colors = { "default": 0, "red": 1, "green": 2, "yellow": 3, "rainbow": 4, "gradient": 5 }
matrix_effects = { "clock": 0, "fire": 1, "life": 2, "scanner": 3, "rain": 4, "plasma": 5, "stars": 6, "pong": 7, "drive": 8 }
MATRIX_TEXT_LEN = 64
MATRIX_FRAMES = 4

def matrix_fail(msg):
    print("matrix: " + msg)
    exit(1)

def matrix_choice(table, key, value):
    if value not in table:
        matrix_fail("unknown %s '%s', expected one of %s" % (key, value, ", ".join(table)))
    return table[value]

# 16x8 rows of G (green), R (red), Y (yellow), . or space (off) -> red plane, green plane
def matrix_frame(n, rows):
    if not isinstance(rows, list) or len(rows) != 8:
        matrix_fail("frame %d must have 8 rows" % n)
    out = bytearray(32)
    for y, row in enumerate(rows):
        if not isinstance(row, str) or len(row) != 16:
            matrix_fail("row %d of frame %d must have 16 chars" % (y, n))
        for x, c in enumerate(row):
            if c not in "GRY. ":
                matrix_fail("frame %d row %d: unknown pixel '%s', expected G, R, Y or ." % (n, y, c))
            bit = 0x80 >> (x % 8)
            if c in "RY":
                out[y * 2 + x // 8] |= bit
            if c in "GY":
                out[16 + y * 2 + x // 8] |= bit
    return out

def matrix_bytes(d):
    out = bytearray(256)
    if not hasattr(d, "matrix"):
        return bytes(out)
    m = d.matrix
    if isinstance(m, str):
        m = SimpleNamespace(mode = m)
    mode = matrix_choice(matrix_modes, "mode", getattr(m, "mode", "core"))
    out[0] = mode
    out[1] = matrix_choice(matrix_colors, "color", getattr(m, "color", "default"))
    if hasattr(m, "step_ms"):
        if not 20 <= m.step_ms <= 5100:
            matrix_fail("step_ms must be 20..5100")
        out[2] = (m.step_ms + 10) // 20
    repeat = getattr(m, "repeat", 0)
    if not 0 <= repeat <= 255:
        matrix_fail("repeat must be 0..255")
    out[3] = repeat
    out[4] = matrix_choice(matrix_then, "then", getattr(m, "then", "core"))
    effect = getattr(m, "effect", None)
    if effect is None and (mode == matrix_modes["effect"] or out[4] == matrix_modes["effect"]):
        matrix_fail("effect is not set")
    out[5] = matrix_choice(matrix_effects, "effect", effect) if effect is not None else 0
    if hasattr(m, "brightness"):
        if not 1 <= m.brightness <= 16:
            matrix_fail("brightness must be 1..16")
        out[6] = m.brightness
    text = getattr(m, "text", "")
    if len(text) > MATRIX_TEXT_LEN or not all(0x20 <= ord(c) < 0x7F for c in text):
        matrix_fail("text must be up to %d ASCII chars" % MATRIX_TEXT_LEN)
    if mode == matrix_modes["scroll"] and text == "":
        matrix_fail("text is not set")
    out[16:16 + len(text)] = text.encode("ascii")
    frames = getattr(m, "frames", None)
    if hasattr(m, "image"):
        frames = [m.image]
    if mode == matrix_modes["image"] and not frames:
        matrix_fail("image or frames is not set")
    if frames:
        if len(frames) > MATRIX_FRAMES:
            matrix_fail("up to %d frames" % MATRIX_FRAMES)
        out[7] = len(frames)
        for n, rows in enumerate(frames):
            out[80 + n * 32:80 + (n + 1) * 32] = matrix_frame(n, rows)
    return bytes(out)

# OSD item types; M (a page entry: opens the items of its page) and - (a separator line) are
# shown as plain rows by firmware older than the tree menus
osd_types = { "S": 0, "N": 1, "T": 2, "H": 3, "P": 4, "F": 5, "FL": 6, "M": 7, "-": 8 }
MAX_OSD_ITEMS = 64    # the firmware reads at most 64 items (older firmware: 32)
MAX_OSD_OPTIONS = 16  # and 16 options of an item (older firmware: 8)
COND_VALUE_MAX = 63

def osd_fail(i, osd, msg):
    print("OSD item %d (%s): %s" % (i, getattr(osd, "name", osd.type), msg))
    exit(1)

# the item a condition names: its index, or its name (unique)
def osd_find(i, osd, ref):
    if isinstance(ref, int):
        if 0 <= ref < len(d.osd): return ref
        osd_fail(i, osd, "condition item %d does not exist" % ref)
    found = [j for j, o in enumerate(d.osd) if getattr(o, "name", None) == ref]
    if len(found) != 1:
        osd_fail(i, osd, "condition item '%s': %s" % (ref, "not found" if not found else "the name is not unique"))
    return found[0]

# the pages: every page an item is on is opened by exactly one M item, and its parents lead to the
# main page (0) without a loop
def osd_check_tree():
    opens = {}
    for i, osd in enumerate(d.osd):
        if osd.type not in osd_types:
            osd_fail(i, osd, "unknown type '%s'" % osd.type)
        page = getattr(osd, "page", 0)
        if not isinstance(page, int) or not 0 <= page <= 255:
            osd_fail(i, osd, "page must be 0..255")
        if osd.type == 'M':
            p = getattr(osd, "open", None)
            if not isinstance(p, int) or not 1 <= p <= 255:
                osd_fail(i, osd, "a page entry needs \"open\": 1..255")
            if p in opens:
                osd_fail(i, osd, "page %d is opened by item %d too" % (p, opens[p]))
            opens[p] = i
        if hasattr(osd, "options") and osd.options and len(osd.options) > MAX_OSD_OPTIONS:
            print("Warning: OSD item %d has %d options, the firmware shows %d" % (i, len(osd.options), MAX_OSD_OPTIONS))
    for i, osd in enumerate(d.osd):
        page = getattr(osd, "page", 0)
        seen = set()
        while page != 0:
            if page not in opens:
                osd_fail(i, osd, "page %d is not opened by any M item" % page)
            if page in seen:
                osd_fail(i, osd, "the pages make a loop")
            seen.add(page)
            page = getattr(d.osd[opens[page]], "page", 0)
    if len(d.osd) > MAX_OSD_ITEMS:
        print("Warning: %d OSD items, the firmware reads %d" % (len(d.osd), MAX_OSD_ITEMS))

# 3 bytes after the hotkey: the page of the item (0 main), the condition item + 1 (0 none), the
# condition: bit 7 disable (else hide), bit 6 invert, bits 0-5 the value. The item is shown /
# enabled when (the value of the condition item == value) xor invert.
def osd_tree_bytes(i, osd):
    page = getattr(osd, "page", 0)
    cond = getattr(osd, "show_if", None)
    disable = False
    if hasattr(osd, "enable_if"):
        if cond is not None:
            osd_fail(i, osd, "show_if and enable_if together")
        cond = osd.enable_if
        disable = True
    if cond is None:
        return bytes([page, 0, 0])
    j = osd_find(i, osd, cond.item)
    if j == i:
        osd_fail(i, osd, "a condition on the item itself")
    other = d.osd[j]
    if other.type not in ('S', 'N') or not getattr(other, "options", None):
        osd_fail(i, osd, "the condition item %d is not a switch with options" % j)
    value = cond.value
    if isinstance(value, str):
        if value not in other.options:
            osd_fail(i, osd, "'%s' is not an option of item %d" % (value, j))
        value = other.options.index(value)
    if not 0 <= value <= COND_VALUE_MAX or value >= len(other.options):
        osd_fail(i, osd, "condition value %d out of range" % value)
    flags = (0x80 if disable else 0) | (0x40 if getattr(cond, "not", False) else 0) | value
    return bytes([page, j + 1, flags])

# usb key map

# special keys (both left+right)
kb_special = { "Ctrl": 0x11, "Shift": 0x22, "Alt": 0x44, "Menu":0x88 }

# normal keys (not all)
kb_keys = {
    "A": 0x04, "B": 0x05, "C": 0x06, "D": 0x07, "E": 0x08, "F": 0x09, "G": 0x0a, "H": 0x0b,
    "I": 0x0c, "J": 0x0d, "K": 0x0e, "L": 0x0f, "M": 0x10, "N": 0x11, "O": 0x12, "P": 0x13,
    "Q": 0x14, "R": 0x15, "S": 0x16, "T": 0x17, "U": 0x18, "V": 0x19, "W": 0x1a, "X": 0x1b,
    "Y": 0x1c, "Z": 0x1d, "1": 0x1e, "2": 0x1f, "3": 0x20, "4": 0x21, "5": 0x22, "6": 0x23,
    "7": 0x24, "8": 0x25, "9": 0x26, "0": 0x27,

    "Enter": 0x28, "Esc": 0x29, "Bkspace": 0x2a, "Tab": 0x2b, "Space": 0x2c, "Caps": 0x39,
    
    "F1": 0x3a, "F2": 0x3b, "F3": 0x3c, "F4": 0x3d, "F5": 0x3e, "F6": 0x3f, "F7": 0x40,
    "F8": 0x41, "F9": 0x42, "F10": 0x43, "F11": 0x44, "F12": 0x45,

    "PtrScr": 0x46, "ScrLk": 0x47, "Pause": 0x48, "Ins": 0x49, "Del": 0x4c, "Home": 0x4a,
    "End": 0x4d, "PgUp": 0x4b, "PgDn": 0x4e, "Right": 0x4f, "Left": 0x50, "Down": 0x51, "Up": 0x52
}

# parse a hotkey ("Menu+F6", "Ctrl+Alt+Del", "F12") into the 2 bytes the firmware reads:
# the modifier mask and the usb keycode. Exactly one non-modifier key is allowed: any other
# length would shift every following osd item in the core file.
def parse_hotkey(value):
    if value.strip() == "":
        return bytearray(2) # no hotkey
    special = 0
    keys = []
    for h in value.split('+'):
        if h in kb_special:
            special = special | kb_special[h]
        elif h in kb_keys:
            keys.append(kb_keys[h])
        else:
            print("Unknown key '%s' in hotkey '%s'" % (h, value))
            exit(1)
    if len(keys) != 1:
        print("Hotkey '%s' must have exactly one key besides Ctrl / Shift / Alt / Menu" % value)
        exit(1)
    return bytearray([special, keys[0]])

# kgo1: one board per file, the user's state is written into the file by the firmware
def kgo1_write():
    global d
    d = json.loads(file_read(filename), object_hook=lambda d: SimpleNamespace(**d))

    # check bitstream and roms exists
    bitstream = file_read(d.bitstream, "rb")
    bitstream_size = len(bitstream)

    # total rom size
    rom_size = 0
    for rom in d.roms:
        rom_size = rom_size + len(rom_payload(rom))

    osd_check_tree()

    o = open(outfile, "wb")

    # header block
    o.write("kgo1".encode("ascii")) # signature
    o.write(d.id.ljust(32)[:32].encode("ascii")) # core id
    o.write(d.name.ljust(32)[:32].encode("ascii")) # core name
    o.write(d.build.ljust(8)[:8].encode("ascii")) # core build
    o.write(b'\x01' if d.visible else b'\x00') # visible (in the list of cores in boot mode)
    o.write(d.order.to_bytes(1, 'big')) # order number 0-255
    # core type
    # 0 - boot (boot mode, osd is a file browser to choose a core from SD1)
    # 1 - osd (normal osd mode, toggled by menu+esc)
    # 2 - fileloader (file loader mode. osd started on core load, on menu+esc it is possible to choose another file to load)
    # 255 - none (osd is hidden)
    o.write(b'\x00' if d.type == 'boot' else b'\x01' if d.type == 'osd' else b'\x02' if d.type == 'fileloader' else b'\xff')
    o.write(d.eeprom_bank.to_bytes(1, 'big')) # eeprom bank (0-3 - 24c08, 255 - no eeprom, 4-254 - in the core file)
    o.write(bitstream_size.to_bytes(4, 'big')) # size of bitstream in bytes
    o.write((rom_size + len(d.roms)*8).to_bytes(4, 'big')) # size of roms block (file sizes + 8 bytes each file)
    o.write(d.rtc_mode.to_bytes(1, 'big') if hasattr(d, "rtc_mode") else b'\x00') # rtc mode 0=mc146818a, 1=ds1307, 2=zx evolution, 3=msm6242b (amiga)
    o.write(d.dir.ljust(32)[:32].encode('ascii') if hasattr(d, "dir") else b'\x00' * 32) # 32 bytes initial dir in fileloader mode
    o.write(d.filename.ljust(32)[:32].encode('ascii') if hasattr(d, "filename") else b'\x00' * 32) # 32 bytes last selected filename in fileloader mode
    o.write(d.extensions.ljust(32)[:32].encode('ascii') if hasattr(d, "extensions") else b'\x00' * 32) # 32 bytes allowed file extensions (comma separated string) 
    o.write(d.spi_freq.to_bytes(1, 'big') if hasattr(d, "spi_freq") else b'\x00') # spi freq
    # 32 bytes: the dir of the backup RAM files (.sav) of the core (karabas-go-firmware docs/protocol.md "Backup RAM");
    # not set: 0xFF (reserved), the firmware takes <dir>/saves then
    o.write(d.save_dir.ljust(32)[:32].encode('ascii') if hasattr(d, "save_dir") else b'\xFF' * 32)
    # 6 x 3 bytes: the on-board buttons (btn1, btn2; btn3..btn6 reserved for the Mini G extra buttons),
    # see buttons_bytes()
    o.write(buttons_bytes(d))
    o.write(b'\xFF' * 20) # reserved 20 bytes
    o.write(b'\xFF' * 256) # eeprom 256 bytes
    for osd in d.osd: # write defaults to switches
        o.write(osd.default.to_bytes(1, 'big') if hasattr(osd, "default") and osd.type != 'M' else b'\x00')
    o.write(b'\x00' * (256 - len(d.osd))) # switches 256 bytes
    # 256 bytes: the LED matrix settings, see matrix_bytes()
    o.write(matrix_bytes(d))

    # bitstream block
    o.write(bitstream)

    # roms block
    for rom in d.roms:
        r = rom_payload(rom)
        rom_is_external = hasattr(rom, "external") and rom.external
        # bit 31 of the length marks an external rom (the payload is its file name)
        r_size = len(r) | (1 << 31) if rom_is_external else len(r)
        o.write(r_size.to_bytes(4, 'big'))
        o.write(rom.address.to_bytes(4, 'big'))
        o.write(r)

    # osd
    o.write(len(d.osd).to_bytes(1, 'big')) # count of osd parameters
    for i, osd in enumerate(d.osd):
        o.write(osd_types[osd.type].to_bytes(1, 'big') if osd.type in osd_types else b'\xFF') # parameter type
        # flags: bit 0 = an F item that can be a physical floppy drive ("physical": 1, Karabas Go)
        flags = 1 if osd.type == 'F' and getattr(osd, "physical", 0) else 0
        o.write(flags.to_bytes(1, 'big'))
        o.write(getattr(osd, "name", "").ljust(16)[:16].encode("ascii")) # option name
        # default value; a page entry (M): the page it opens
        o.write(osd.open.to_bytes(1, 'big') if osd.type == 'M' else osd.default.to_bytes(1, 'big') if hasattr(osd, "default") else b'\x00')
    
        # file mounter struct
        if osd.type=='F' or osd.type=='FL':
            slot = osd.slot if hasattr(osd, "slot") else 0
            autoload = osd.autoload if hasattr(osd, "autoload") else 0
            if autoload: # write autoload bit as 7th bit of slot value
                slot = slot | (1 << 7)
            o.write(slot.to_bytes(1, 'big'))
            o.write(osd.extensions.ljust(256)[:256].encode('ascii') if hasattr(osd, "extensions") else b'\x00' * 256)
            # dir and filename are padded with NULs: the firmware uses them as they are, and a dir
            # padded with spaces ("/amiga" + 250 spaces) does not exist
            o.write(osd.dir.ljust(256, '\0')[:256].encode('ascii') if hasattr(osd, "dir") else b'\x00' * 256)
            o.write(osd.filename.ljust(256, '\0')[:256].encode('ascii') if hasattr(osd, "filename") else b'\x00' * 256)
        # osd options struct
        else:
            o.write(len(osd.options).to_bytes(1, 'big') if hasattr(osd, "options") and osd.options and len(osd.options) > 0 else b'\x00') # number of options
            if hasattr(osd, "options") and osd.options and len(osd.options) > 0:
                for opt in osd.options:
                    o.write(opt.ljust(16)[:16].encode("ascii")) #option name

        # hotkey or second line of text
        if (osd.type == 'P'):
            o.write(osd.name.ljust(32)[16:32].encode("ascii")) # second part of text line as hotkey
        elif osd.type in ('M', '-'):
            o.write(b' ' * 16) # no hotkey
        else:
            o.write(osd.hotkey.ljust(16)[:16].encode("ascii") if hasattr(osd, "hotkey") else "                ".encode("ascii")) # option hotkey
        o.write(parse_hotkey(osd.hotkey) if hasattr(osd, "hotkey") and osd.type not in ('M', '-') else b'\x00' * 2) # option keycodes (parsed)
        o.write(osd_tree_bytes(i, osd)) # the page and the condition of the item (0 0 0: main page, always shown)

    o.close()

#########################################################
# kgo2 (.kg): one file for all boards, docs/kgo2.md     #
#########################################################

KG2_BOARDS = { "go": 1, "mini": 2, "minig": 3 } # the HW_ID of each board: bit HW_ID of the masks
KG2_VERSION = 1
SEC_STRINGS, SEC_CORE, SEC_LOADER, SEC_OSD, SEC_BUTTONS, SEC_MATRIX, SEC_EEPROM, SEC_ROMS, SEC_BITSTREAM = range(1, 10)
KG2_SEC_NAMES = { SEC_STRINGS: "STRINGS", SEC_CORE: "CORE", SEC_LOADER: "LOADER", SEC_OSD: "OSD",
                  SEC_BUTTONS: "BUTTONS", SEC_MATRIX: "MATRIX", SEC_EEPROM: "EEPROM_INIT",
                  SEC_ROMS: "ROMS", SEC_BITSTREAM: "BITSTREAM" }
KG2_ITEM_SIZE = 48
KG2_STATE_TYPES = ('S', 'F', 'FL')       # the items whose value is kept in /config/<id>.ini
KG2_SWITCH_TYPES = ('S', 'N', 'T', 'H')  # the items sent with CMD_SWITCHES
KG2_TEXT_MAX = 16  # an item / option name in the OSD column (P: 32)
KG2_PATH_MAX = 255
MAX_FILE_SLOTS = 8

def fail(msg):
    print(msg)
    exit(1)

# a key from a text: lower case, other chars -> '_', up to 16 ("FM (MSX-MUSIC)" -> "fm_msx_music")
def kg2_slug(text):
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')[:16].strip('_')

def kg2_check_key(where, key):
    if not isinstance(key, str) or not re.fullmatch(r'[a-z0-9_]{1,16}', key):
        fail("%s: key '%s' must be 1..16 chars of a-z, 0-9, _" % (where, key))

def kg2_ascii(where, text, maxlen):
    if not isinstance(text, str) or len(text) > maxlen or not all(0x20 <= ord(c) < 0x7F for c in text):
        fail("%s: '%s' must be up to %d ASCII chars" % (where, text, maxlen))

# the string pool: every distinct string once, NUL-terminated; offset 0 is the empty string
class Kg2Strings:
    def __init__(self):
        self.data = bytearray(b'\0')
        self.offsets = { "": 0 }

    def ref(self, text):
        if text is None:
            return 0
        if text not in self.offsets:
            b = text.encode('utf-8')
            if b'\0' in b:
                fail("a string with a NUL: '%s'" % text)
            self.offsets[text] = len(self.data)
            self.data += b + b'\0'
            if len(self.data) > 0xFFFF:
                fail("the strings take more than 64 KB")
        return self.offsets[text]

# the board part over the common one: objects key by key, the rest replaced
def kg2_merge(base, over):
    out = dict(base)
    for k, v in over.items():
        out[k] = kg2_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out

def kg2_ns(obj):
    return json.loads(json.dumps(obj), object_hook = lambda x: SimpleNamespace(**x))

# extensions: a list (["dsk", "img"]) or the kgo1 string (".dsk,.img") -> "dsk,img"
def kg2_exts(where, exts):
    if exts is None:
        return ""
    items = exts if isinstance(exts, list) else exts.split(',')
    out = []
    for e in items:
        e = e.strip().lstrip('.')
        if e:
            kg2_ascii(where + " extension", e, 16)
            out.append(e.lower())
    return ",".join(out)

# a path (a dir, a file): a string up to 255 bytes
def kg2_path(where, path):
    if path is None:
        return None
    if not isinstance(path, str) or len(path.encode('utf-8')) > KG2_PATH_MAX:
        fail("%s: the path must be a string up to %d bytes" % (where, KG2_PATH_MAX))
    return path

# file candidates: a string or a list, the first one that exists is used
def kg2_files(where, files):
    if files is None or files == "":
        return []
    files = files if isinstance(files, list) else [files]
    if len(files) > 255:
        fail("%s: up to 255 file candidates" % where)
    return [kg2_path(where, f) for f in files]

# the configuration of each board: the common keys with its "boards" part merged over them;
# a json without "boards" (kgo1) is the board of --boards
def kg2_configs(raw, boards_arg):
    common = { k: v for k, v in raw.items() if k != "boards" }
    boards = raw.get("boards")
    if boards is None:
        if not boards_arg or len(boards_arg) != 1:
            fail("the json has no \"boards\": give its board with --boards (one of %s)" % ", ".join(KG2_BOARDS))
        boards = { boards_arg[0]: {} }
    if not isinstance(boards, dict) or not boards:
        fail("\"boards\" must be an object with at least one board")
    configs = {}
    for name, over in boards.items():
        if name not in KG2_BOARDS:
            fail("unknown board '%s', expected one of %s" % (name, ", ".join(KG2_BOARDS)))
        configs[name] = kg2_merge(common, over or {})
    return configs

def kg2_core(cfg, strings):
    for k in ("id", "name", "build", "type"):
        if k not in cfg:
            fail("\"%s\" is not set" % k)
    kg2_ascii("id", cfg["id"], 32)
    kg2_ascii("name", cfg["name"], 32)
    kg2_ascii("build", cfg["build"], 8)
    types = { "boot": 0, "osd": 1, "fileloader": 2, "hidden": 255 }
    if cfg["type"] not in types:
        fail("unknown type '%s', expected one of %s" % (cfg["type"], ", ".join(types)))
    def byte(k, default):
        v = cfg.get(k, default)
        if isinstance(v, bool):
            v = int(v)
        if not isinstance(v, int) or not 0 <= v <= 255:
            fail("\"%s\" must be 0..255" % k)
        return v
    return struct.pack('<HHHHBBBBBBH', 16, strings.ref(cfg["id"]), strings.ref(cfg["name"]), strings.ref(cfg["build"]),
                       types[cfg["type"]], byte("visible", 1), byte("order", 0), byte("rtc_mode", 0),
                       byte("eeprom_bank", 255), byte("spi_freq", 0), 0)

# "loader", or the kgo1 top-level keys dir / extensions / filename / save_dir
def kg2_loader(cfg, strings):
    loader = cfg.get("loader")
    if loader is None:
        if cfg["type"] != "fileloader":
            return None
        loader = { k2: cfg[k1] for k1, k2 in (("dir", "dir"), ("extensions", "exts"), ("filename", "file"),
                                               ("save_dir", "save_dir")) if k1 in cfg }
    unknown = set(loader) - { "dir", "exts", "extensions", "file", "filename", "autoload", "save_dir" }
    if unknown:
        fail("loader: unknown keys %s" % ", ".join(sorted(unknown)))
    files = kg2_files("loader file", loader.get("file", loader.get("filename")))
    head = struct.pack('<HHHHBBH', 12, strings.ref(kg2_path("loader dir", loader.get("dir", ""))),
                       strings.ref(kg2_exts("loader", loader.get("exts", loader.get("extensions")))),
                       strings.ref(kg2_path("loader save_dir", loader.get("save_dir", ""))),
                       1 if loader.get("autoload", True) else 0, len(files), 12)
    return head + b''.join(struct.pack('<H', strings.ref(f)) for f in files)

def kg2_option_list(where, item):
    opts = item.get("options") or []
    if len(opts) > MAX_OSD_OPTIONS:
        fail("%s: %d options, up to %d" % (where, len(opts), MAX_OSD_OPTIONS))
    out = []
    for n, opt in enumerate(opts):
        if isinstance(opt, str):
            opt = { "name": opt }
        if not isinstance(opt, dict) or "name" not in opt:
            fail("%s: option %d must be a string or an object with a name" % (where, n))
        kg2_ascii("%s option %d" % (where, n), opt["name"], KG2_TEXT_MAX)
        key = opt.get("key", kg2_slug(opt["name"]))
        kg2_check_key("%s option '%s'" % (where, opt["name"]), key)
        value = opt.get("value", n)
        if not isinstance(value, int) or not 0 <= value <= 255:
            fail("%s option '%s': value must be 0..255" % (where, opt["name"]))
        out.append({ "name": opt["name"], "key": key, "value": value })
    if len({ o["key"] for o in out }) != len(out):
        fail("%s: option keys are not unique" % where)
    if len({ o["value"] for o in out }) != len(out):
        fail("%s: option values are not unique" % where)
    return out

# an option of an item: by key, by text, or by position (a number, as kgo1)
def kg2_find_option(where, opts, ref):
    if isinstance(ref, bool) or not isinstance(ref, (int, str)):
        fail("%s: an option is named by its key, text or position" % where)
    if isinstance(ref, int):
        if 0 <= ref < len(opts):
            return opts[ref]
        fail("%s: option %d does not exist" % (where, ref))
    for o in opts:
        if o["key"] == ref:
            return o
    for o in opts:
        if o["name"] == ref:
            return o
    fail("%s: no option '%s'" % (where, ref))

def kg2_osd(cfg, board, strings):
    all_items = cfg.get("osd") or []
    items = []  # (position in the json, item) of this board
    for pos, item in enumerate(all_items):
        if not isinstance(item, dict) or "type" not in item:
            fail("OSD item %d: an object with a type" % pos)
        boards = item.get("boards")
        if boards is not None:
            if not isinstance(boards, list) or any(b not in KG2_BOARDS for b in boards):
                fail("OSD item %d: \"boards\" must be a list of %s" % (pos, ", ".join(KG2_BOARDS)))
            if board not in boards:
                continue
        items.append((pos, item))
    if not items:
        return None
    if len(items) > MAX_OSD_ITEMS:
        fail("%s: %d OSD items, up to %d" % (board, len(items), MAX_OSD_ITEMS))

    # the parts of each item, checked
    parts = []
    keys = {}
    indexes = {}
    opens = {}
    for n, (pos, item) in enumerate(items):
        t = item["type"]
        name = item.get("name", "")
        where = "%s: OSD item %d (%s)" % (board, pos, name or t)
        if t not in osd_types:
            fail("%s: unknown type '%s'" % (where, t))
        kg2_ascii(where + " name", name, 32 if t == 'P' else KG2_TEXT_MAX)
        p = { "type": t, "item": item, "where": where, "name": name }
        # the key: given, else made from the name (the items with a state need one)
        key = item.get("key")
        if key is None and t in KG2_STATE_TYPES:
            key = kg2_slug(name)
        if key is not None:
            kg2_check_key(where, key)
            if t in KG2_STATE_TYPES:
                if key in keys:
                    fail("%s: key '%s' is used by OSD item %d too" % (where, key, keys[key]))
                keys[key] = pos
        p["key"] = key
        # the switch number: given, else the position in the list of the board (as kgo1)
        index = 255
        if t in KG2_SWITCH_TYPES:
            index = item.get("index", n)
            if not isinstance(index, int) or not 0 <= index <= 254:
                fail("%s: index must be 0..254" % where)
            if index in indexes:
                fail("%s: index %d is used by OSD item %d too" % (where, index, indexes[index]))
            indexes[index] = pos
        elif "index" in item:
            fail("%s: only %s items have an index" % (where, "/".join(KG2_SWITCH_TYPES)))
        p["index"] = index
        p["opts"] = kg2_option_list(where, item) if t in ('S', 'N') else []
        if t not in ('S', 'N') and item.get("options"):
            fail("%s: only S / N items have options" % where)
        default = 0
        if t in ('S', 'N') and p["opts"]:
            default = kg2_find_option(where + " default", p["opts"], item.get("default", 0))["value"]
        p["default"] = default
        page = item.get("page", 0)
        if not isinstance(page, int) or not 0 <= page <= 255:
            fail("%s: page must be 0..255" % where)
        p["page"] = page
        p["open"] = 0
        if t == 'M':
            o = item.get("open")
            if not isinstance(o, int) or not 1 <= o <= 255:
                fail("%s: a page entry needs \"open\": 1..255" % where)
            if o in opens:
                fail("%s: page %d is opened by OSD item %d too" % (where, o, items[opens[o]][0]))
            opens[o] = n
            p["open"] = o
        flags = 0
        p["slot"] = 0
        p["files"] = []
        p["exts"] = ""
        p["dir"] = None
        if t in ('F', 'FL'):
            slot = item.get("slot", 0)
            if not isinstance(slot, int) or not 0 <= slot < MAX_FILE_SLOTS:
                fail("%s: slot must be 0..%d" % (where, MAX_FILE_SLOTS - 1))
            p["slot"] = slot
            p["exts"] = kg2_exts(where, item.get("exts", item.get("extensions")))
            p["dir"] = kg2_path(where + " dir", item.get("dir"))
            p["files"] = kg2_files(where + " file", item.get("file", item.get("filename")))
            if item.get("physical"):
                if t != 'F':
                    fail("%s: only F items can be physical" % where)
                flags |= 1
            if item.get("readonly"):
                if t != 'F':
                    fail("%s: only F items can be read-only" % where)
                flags |= 2
            if item.get("autoload"):
                flags |= 4
        else:
            for k in ("slot", "exts", "extensions", "dir", "file", "filename", "physical", "readonly", "autoload"):
                if k in item:
                    fail("%s: \"%s\" is for F / FL items" % (where, k))
        p["flags"] = flags
        hotkey = item.get("hotkey", "") if t not in ('M', '-', 'P') else ""
        kg2_ascii(where + " hotkey", hotkey, KG2_TEXT_MAX)
        p["hotkey"] = hotkey
        p["hk"] = parse_hotkey(hotkey) if hotkey else bytes(2)
        parts.append(p)

    # the pages: every page is opened by one M item, its parents lead to the main page
    for p in parts:
        page = p["page"]
        seen = set()
        while page != 0:
            if page not in opens:
                fail("%s: page %d is not opened by any M item" % (p["where"], page))
            if page in seen:
                fail("%s: the pages make a loop" % p["where"])
            seen.add(page)
            page = parts[opens[page]]["page"]

    # the conditions: the item by key, name or position in the json, on this board
    def find_item(where, ref):
        if isinstance(ref, int) and not isinstance(ref, bool):
            found = [n for n, (pos, _) in enumerate(items) if pos == ref]
            if not found:
                fail("%s: condition item %d is not on board %s" % (where, ref, board))
            return found[0]
        found = [n for n, p in enumerate(parts) if p["key"] == ref]
        if not found:
            found = [n for n, p in enumerate(parts) if p["name"] == ref]
        if len(found) != 1:
            fail("%s: condition item '%s': %s" % (where, ref, "not found" if not found else "not unique"))
        return found[0]

    for n, p in enumerate(parts):
        item = p["item"]
        cond = item.get("show_if")
        disable = False
        if "enable_if" in item:
            if cond is not None:
                fail("%s: show_if and enable_if together" % p["where"])
            cond = item["enable_if"]
            disable = True
        p["cond"] = (0, 0, 0)
        if cond is None:
            continue
        if not isinstance(cond, dict) or "item" not in cond or "value" not in cond:
            fail("%s: a condition is {\"item\": ..., \"value\": ...}" % p["where"])
        j = find_item(p["where"], cond["item"])
        if j == n:
            fail("%s: a condition on the item itself" % p["where"])
        other = parts[j]
        if other["type"] not in ('S', 'N') or not other["opts"]:
            fail("%s: the condition item is not a switch with options" % p["where"])
        value = kg2_find_option(p["where"] + " condition", other["opts"], cond["value"])["value"]
        p["cond"] = (j + 1, (0x80 if disable else 0) | (0x40 if cond.get("not") else 0), value)

    # the records, then the options and the file candidates they point to
    tail = bytearray()
    base = 8 + KG2_ITEM_SIZE * len(parts)
    records = bytearray()
    for p in parts:
        opts_ofs = base + len(tail) if p["opts"] else 0
        for o in p["opts"]:
            tail += struct.pack('<HHB3x', strings.ref(o["key"]), strings.ref(o["name"]), o["value"])
        files_ofs = base + len(tail) if p["files"] else 0
        for f in p["files"]:
            tail += struct.pack('<H', strings.ref(f))
        rec = struct.pack('<14BH', osd_types[p["type"]], p["flags"], p["index"], p["page"], p["open"],
                          p["cond"][0], p["cond"][1], p["cond"][2], p["default"], p["slot"], p["hk"][0], p["hk"][1],
                          len(p["opts"]), len(p["files"]), 0)
        rec += struct.pack('<7H', strings.ref(p["key"]), strings.ref(p["name"]), strings.ref(p["hotkey"]),
                           strings.ref(p["exts"]), strings.ref(p["dir"]), opts_ofs, files_ofs)
        rec += bytes(KG2_ITEM_SIZE - len(rec))
        records += rec
    section = struct.pack('<HHI', len(parts), KG2_ITEM_SIZE, 0) + records + tail
    if len(section) > 0xFFFF:
        fail("%s: the OSD section takes more than 64 KB" % board)
    return bytes(section)

def kg2_roms(cfg):
    out = bytearray()
    for rom in cfg.get("roms") or []:
        r = kg2_ns(rom)
        data = rom_payload(r)
        external = bool(getattr(r, "external", False))
        out += struct.pack('<II', len(data) | (1 << 31 if external else 0), r.address) + data
    return bytes(out) if out else None

def kg2_eeprom(cfg):
    name = cfg.get("eeprom_init")
    if name is None:
        return None
    data = file_read(name, "rb")
    if len(data) > 256:
        fail("eeprom_init: %s has %d bytes, up to 256" % (name, len(data)))
    return data + b'\xFF' * (256 - len(data))

# the sections of a .kg: {type: [(mask, data)]}
def kg2_read(name):
    with open(name, "rb") as f:
        data = f.read()
    if len(data) < 32 or data[0:4] != b"kgo2":
        fail("%s is not a kgo2 file" % name)
    _, version, _, hsize, count, esize, mask = struct.unpack_from('<4sBBHHHH', data, 0)
    sections = {}
    for i in range(count):
        t, m, ofs, ln = struct.unpack_from('<HHII', data, hsize + i * esize)
        sections.setdefault(t, []).append((m, data[ofs:ofs + ln]))
    return sections

def kg2_write():
    raw = json.loads(file_read(filename))
    boards_arg = [b.strip() for b in args.boards.split(',')] if args.boards else None
    configs = kg2_configs(raw, boards_arg)
    if boards_arg:
        for b in boards_arg:
            if b not in configs:
                fail("--boards: '%s' is not a board of the json (%s)" % (b, ", ".join(configs)))
    take = boards_arg or list(configs)
    old = kg2_read(outfile) if os.path.isfile(outfile) and set(take) != set(configs) else {}

    strings = Kg2Strings()
    per_board = {}  # board -> {type: data}
    for board, cfg in configs.items():
        bit = 1 << KG2_BOARDS[board]
        if board in take:
            if "bitstream" not in cfg:
                fail("%s: \"bitstream\" is not set" % board)
            bitstream = file_read(cfg["bitstream"], "rb")
        else:
            kept = [d for m, d in old.get(SEC_BITSTREAM, []) if m & bit]
            if not kept:
                print("%s: no bitstream (not in --boards, not in %s): the board is left out" % (board, outfile))
                continue
            bitstream = kept[0]
        cfg_ns = kg2_ns(cfg)
        secs = { SEC_CORE: kg2_core(cfg, strings), SEC_BITSTREAM: bitstream }
        loader = kg2_loader(cfg, strings)
        if loader is not None:
            secs[SEC_LOADER] = loader
        osd = kg2_osd(cfg, board, strings)
        if osd is not None:
            secs[SEC_OSD] = osd
        if "buttons" in cfg:
            secs[SEC_BUTTONS] = bytes([BUTTONS]) + buttons_bytes(cfg_ns)
        if "matrix" in cfg:
            secs[SEC_MATRIX] = matrix_bytes(cfg_ns)
        eeprom = kg2_eeprom(cfg)
        if eeprom is not None:
            secs[SEC_EEPROM] = eeprom
        roms = kg2_roms(cfg)
        if roms is not None:
            secs[SEC_ROMS] = roms
        per_board[board] = secs
    if not per_board:
        fail("no board to write")

    # a section the same for several boards is written once, with their bits
    all_mask = 0
    for board in per_board:
        all_mask |= 1 << KG2_BOARDS[board]
    table = [(SEC_STRINGS, all_mask, bytes(strings.data))]
    for t in sorted(KG2_SEC_NAMES):
        groups = []  # [mask, data]
        for board, secs in per_board.items():
            if t not in secs:
                continue
            for g in groups:
                if g[1] == secs[t]:
                    g[0] |= 1 << KG2_BOARDS[board]
                    break
            else:
                groups.append([1 << KG2_BOARDS[board], secs[t]])
        table += [(t, m, data) for m, data in groups]

    pos = 32 + 16 * len(table)
    entries = bytearray()
    body = bytearray()
    for t, m, data in table:
        pad = (-(pos + len(body))) % 4
        body += bytes(pad)
        entries += struct.pack('<HHII4x', t, m, pos + len(body), len(data))
        body += data
    header = struct.pack('<4sBBHHHH18x', b"kgo2", KG2_VERSION, 0, 32, len(table), 16, all_mask)
    with open(outfile, "wb") as o:
        o.write(header + entries + body)
    print("%s: %s, boards %s" % (outfile, raw.get("id", ""), ", ".join(per_board)))

if outfile.lower().endswith(".kg"):
    kg2_write()
else:
    if args.boards:
        fail("--boards is for kgo2 (.kg) files")
    kgo1_write()
