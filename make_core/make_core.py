#!/bin/env python3

#########################################################
# Karabas Go Core Generator v1.0                        #
#                                                       #
# (c) 2023, 2024 Andy Karpov <andy.karpov@gmail.com>    #
#########################################################

import json
import argparse
import sys
import os
from types import SimpleNamespace

msg = "Karabas Go binary core maker v1.0"
parser = argparse.ArgumentParser(description = msg)
parser.add_argument('json_file')
parser.add_argument('output_file')
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

d = json.loads(file_read(filename), object_hook=lambda d: SimpleNamespace(**d))

# check bitstream and roms exists
bitstream = file_read(d.bitstream, "rb")
bitstream_size = len(bitstream)

# rom payloads: the rom data for embedded roms, the file name (on the sd card) for external ones
def rom_payload(rom):
    if hasattr(rom, "external") and rom.external:
        return rom.filename.encode("ascii")
    return file_read(rom.filename, "rb")

# total rom size
rom_size = 0
for rom in d.roms:
    rom_size = rom_size + len(rom_payload(rom))

# on-board button actions (karabas-go-firmware, input_tick_buttons):
# core: press / release go to the core (CMD_BTN), the default
# none: ignored, osd: toggle the osd, menu: back to the boot core, reload: load the core again,
# bootsel: reboot the mcu into BOOTSEL, msc: reboot into USB mass storage
btn_actions = { "core": 0, "none": 1, "osd": 2, "menu": 3, "reload": 4, "bootsel": 5, "msc": 6 }
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
matrix_effects = { "clock": 0, "fire": 1, "life": 2, "scanner": 3 }
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
    o.write(osd.default.to_bytes(1, 'big') if hasattr(osd, "default") else b'\x00')
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

# osd
o.write(len(d.osd).to_bytes(1, 'big')) # count of osd parameters
for osd in d.osd:
    o.write(b'\x00' if osd.type == 'S' else b'\x01' if osd.type == 'N' else b'\x02' if osd.type == 'T' else b'\x03' if osd.type == 'H' else b'\x04' if osd.type == 'P' else b'\x05' if osd.type =='F' else b'\x06' if osd.type == 'FL' else b'\xFF') # parameter type
    # flags: bit 0 = an F item that can be a physical floppy drive ("physical": 1, Karabas Go)
    flags = 1 if osd.type == 'F' and getattr(osd, "physical", 0) else 0
    o.write(flags.to_bytes(1, 'big'))
    o.write(osd.name.ljust(16)[:16].encode("ascii")) # option name
    o.write(osd.default.to_bytes(1, 'big') if hasattr(osd, "default") else b'\x00') # default value
    
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
    else:
        o.write(osd.hotkey.ljust(16)[:16].encode("ascii") if hasattr(osd, "hotkey") else "                ".encode("ascii")) # option hotkey
    o.write(parse_hotkey(osd.hotkey) if hasattr(osd, "hotkey") else b'\x00' * 2) # option keycodes (parsed)
    o.write(b'\x00'*3) # reserved

#print(d.name, d.build)
#print(bitstream_size, rom_size)

o.close()

