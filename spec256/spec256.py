#!/bin/env python3

#########################################################
# Karabas Go Spec256 snapshot convertor v1.0            #
#                                                       #
# (c) 2026 Andy Karpov <andy.karpov@gmail.com>          #
#########################################################

import argparse
import sys
import os
import numpy as np


msg = "Karabas Go Spec256 snapshot convertor v1.0"
parser = argparse.ArgumentParser(description = msg)
parser.add_argument('sna_file')
parser.add_argument('gfx_file')
parser.add_argument('output_file')
args = parser.parse_args()

sna_filename = args.sna_file
gfx_filename = args.gfx_file
outfile = args.output_file

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

o = open(outfile, "wb")

for i in range(49152):
    byte_sna = sna[i]
    word_gfx = gfx[i*8:i*8+8]
    # если все 0 или один из байтов FF - берем за основу байт из sna
    if word_gfx == bytearray([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]) or 0xFF in word_gfx:
        byte_res = byte_sna
        o.write(byte_res.to_bytes(1, 'big'))
        o.write(byte_res.to_bytes(1, 'big'))
        o.write(byte_res.to_bytes(1, 'big'))
        o.write(byte_res.to_bytes(1, 'big'))
        o.write(byte_res.to_bytes(1, 'big'))
        o.write(byte_res.to_bytes(1, 'big'))
        o.write(byte_res.to_bytes(1, 'big'))
        o.write(byte_res.to_bytes(1, 'big'))
    else:
        """ 
        zxpoly emul on java:
        for (int offset = 0; offset < dataLen; offset += 8) {
              for (int ctx = 0; ctx < 8; ctx++) {
                final int bitMask = 1 << ctx;
                int accumulator = 0;
                for (int i = 0; i < 8; i++) {
                  if ((from.getGfxData()[offset + i] & bitMask) != 0) {
                    accumulator |= 1 << i;
                  }
                }
                result[offset + ctx] = (byte) accumulator;
              }
            }
        """
        for ctx in range(8):
            bitmask = 1 << ctx
            accumulator = 0
            for k in range(8):
                byte_gfx = gfx[i*8+k]
                if byte_gfx & bitmask != 0:
                    accumulator |= 1 << k;
            o.write(accumulator.to_bytes(1, 'big'))

"""
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
"""

# todo: записать в порядке восстановления T80:
# -- IFF2(1 bit), IFF1(1 bit), IM(2 bits), IY, HL', DE', BC', IX, HL, DE, BC, PC, SP, R, I, F', A', F, A

def write_reg(reg):
    o.write(regs[reg].to_bytes(1, 'big'))

def get_pc():
    sp = regs[23] + regs[24]*256
    if sp >= 16384:
        pc = file_read(sna_filename, "rb", sp - 16384, 2)
        return pc
    else:
        return [0x00, 0x00]

def get_sp():
    sp = regs[23] + regs[24]*256
    sp = sp + 2
    return (sp & 0xFFFF).to_bytes(2, 'big')

sp = get_sp()
print (f"SP={sp}")
pc = get_pc()
print (f"PC={pc}")

write_reg(21)      # [7:0]   A
write_reg(22)      # [15:8]  F
write_reg(7)       # [23:15] A'
write_reg(8)       # [31:16] F'
write_reg(0)       # [39:32] I
write_reg(20)      # [47:40] R

write_reg(23)      # [55:48] SP l
write_reg(24)      # [63:56] SP h
#o.write(sp[1].to_bytes(1, 'big'))     # [55:48] SP l
#o.write(sp[0].to_bytes(1, 'big'))     # [63:56] SP h

o.write((0x72).to_bytes(1, 'big'))     # [71:64] PC l # RETN
o.write((0x00).to_bytes(1, 'big'))     # [79:72] PC h
#o.write(pc[1].to_bytes(1, 'big'))     # [71:64] PC l # RETN
#o.write(pc[0].to_bytes(1, 'big'))     # [79:72] PC h

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

# from MIST snap_loader
# 25: snap_REG[209:208] <= ioctl_data[1:0]; //im
# 19: snap_REG[211:210] <= {ioctl_data[2], 1'b0}; //iff2,iff1

iff = 2 if regs[19] & 0x04 else 0
print(f"reg19 = {regs[19]}")
print(f"IFF = {iff}")
print(f"IM = {regs[25]}")
im_iff = regs[25] + (iff << 2)
print(f"IMIFF = {im_iff}")
o.write(im_iff.to_bytes(1, 'big'))      # [215:208] {4'b0000, IFF[1:0], IM[1:0]}

write_reg(26) # [223:216] border
# total: 28 bytes
o.close()

