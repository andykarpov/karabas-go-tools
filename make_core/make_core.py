#!/bin/env python3

#########################################################
# Karabas Go Core Generator v1.0                        #
#                                                       #
# (c) 2023 Andy Karpov <andy.karpov@gmail.com>          #
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

rom_size = 0
for rom in d.roms:
    r = file_read(rom.filename, "rb")
    rom_size = rom_size + len(r)

o = open(outfile, "wb")

# header
o.write("kgo1".encode("ascii")) # signature
o.write(d.id.ljust(32)[:32].encode("ascii")) # core id
o.write(d.name.ljust(32)[:32].encode("ascii")) # core name
o.write(d.build.ljust(8)[:8].encode("ascii")) # core build
o.write(b'\x01' if d.visible else b'\x00') # visible
o.write(d.order.to_bytes(1, 'big')) # order
o.write(b'\x00' if d.type == 'boot' else b'\x01' if d.type == 'osd' else b'\x02') # core type
o.write(d.eeprom_bank.to_bytes(1, 'big')) # eeprom bank
o.write(bitstream_size.to_bytes(4, 'big')) # size of bitstream in bytes
o.write((rom_size + len(d.roms)*8).to_bytes(4, 'big')) # size of roms block (file sizes + 8 bytes each file)
o.write(b'\x00' * 168) # reserved 168 bytes
o.write(b'\xFF' * 256) # eeprom 256 bytes
o.write(b'\x00' * 256) # switches 256 bytes
o.write(b'\x00' * 256) # reserved 256 bytes

# bitstream
o.write(bitstream)

# roms
for rom in d.roms:
    r = file_read(rom.filename, "rb")
    o.write(len(r).to_bytes(4, 'big'))
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
    "Y": 0x1c, "Z": 0x1d,

    "Enter": 0x28, "Esc": 0x29, "Bkspace": 0x2a, "Tab": 0x2b, "Space": 0x2c, "Caps": 0x39,
    
    "F1": 0x3a, "F2": 0x3b, "F3": 0x3c, "F4": 0x3d, "F5": 0x3e, "F6": 0x3f, "F7": 0x40,
    "F8": 0x41, "F9": 0x42, "F10": 0x43, "F11": 0x44, "F12": 0x45,

    "PtrScr": 0x46, "ScrLk": 0x47, "Pause": 0x48, "Ins": 0x49, "Del": 0x4c, "Home": 0x4a,
    "End": 0x4d, "PgUp": 0x4b, "PgDn": 0x4e, "Right": 0xf, "Left": 0x50, "Down": 0x51, "Up": 0x52
}

# parse string of hotkeys into bytearray of usb keycodes
def parse_hotkey(value):
    ret = bytearray()
    hotkeys = value.split('+', 3)
    special = 0
    for h in hotkeys:
        if h in kb_special:
            special = special + kb_special[h]
    ret.append(special)
    keys = []
    for h in hotkeys:
        if h in kb_keys:
            keys.append(kb_keys[h])
    if len(keys):
        for k in keys[:2]:
            ret.append(k)
    return ret

# osd
o.write(len(d.osd).to_bytes(1, 'big')) # count of osd parameters
for osd in d.osd:
    o.write(b'\x00' if osd.type == 'S' else b'\x01' if osd.type == 'N' else b'\x02' if osd.type == 'T' else b'\x03') # parameter type
    o.write(osd.bits.to_bytes(1, 'big')) # number of bits to transfer
    o.write(osd.name.ljust(16)[:16].encode("ascii")) # option name
    o.write(osd.default.to_bytes(1, 'big')) # default value
    o.write(len(osd.options).to_bytes(1, 'big') if osd.options else b'\x00') # number of options
    if osd.options:
        for opt in osd.options:
            o.write(opt.ljust(16)[:16].encode("ascii")) #option name
    o.write(osd.hotkey.ljust(16)[:16].encode("ascii")) # option hotkey
    o.write(parse_hotkey(osd.hotkey)) # option keycodes (parsed)
    o.write(b'\x00'*3) # reserved

#print(d.name, d.build)
#print(bitstream_size, rom_size)

o.close()

