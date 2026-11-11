# spec256.py — Spec256 games to `.256` for the Karabas Go core

`spec256.py` converts a 256-colour game (Spec256 / EmuZWin) into one `.256` file, which the
[karabas-go-core-spec256](https://github.com/andykarpov/karabas-go-core-spec256) core loads from the OSD
(`Snapshot`, Menu+T). The core is described in its `docs/SIMD.md` (Russian); the file format is defined by
this script and the loader of `src/rtl/spec256.vhd`, which go together.

## Usage

```
python3 spec256.py GAME.SNA            # GAME.SNA + GAME.GFX (+ the files below) -> GAME.256
python3 spec256.py GAME.ezx            # an EmuZWin state with GFX -> GAME.256 (EZX.md)
python3 spec256.py GAME.ezx --extract  # only write GAME.SNA, GAME.GFX, ... next to GAME.ezx
python3 spec256.py GAME.SNA --plain    # 48K only: no extension (the format of v1.2)
```

The `.256` is written next to the input. The companion files are found by the name of the snapshot,
in any case of the name and of the extension (`SinkFeel.gfx`, `AticAtac.sna`); an empty file counts as
missing.

## Input files

| File | Size | What |
|---|---|---|
| `.SNA` | 49179 (48K), 131103 / 147487 (128K) | the snapshot; 48K or 128K by the size |
| `.GFX` | 393216 | the colours of the RAM: 8 bytes per byte of the Spectrum (byte k = colour of the pixel of bit k), for the banks 5, 2 and the one at C000 |
| `.GF0`–`.GF7` | 131072 | 128K: the colours of bank n, over its part of the `.GFX` |
| `.GFB` | 131072 | the colours of the ROM 1 (the 48K ROM); a word of 0 = not coloured |
| `.GFA` | 131072 | 128K: the colours of the ROM 0 (the 128 menu ROM) |
| `.PAL` | 768 bytes RGB, or 768 numbers as text (GZX) | the palette; else the standard one of Spec256 |
| `.CFG` | text | the settings and the background rules (below) |
| `.B00`–`.B99` | 64000 | backgrounds 320×200, a palette index per pixel; the core shows x 32..287, y 4..195 |

Notes on the collections:
- The original Spec256 packs (Spec256 v1.2 site: `Knlore.zip`, `Underw.zip`, `Armymov2.zip`, …) are the
  most complete source of the 12 Spec256 games: some collections miss files (`UNDERW.B00`, all of Army
  Moves 2). `ARMYMOV1.B01` and `GAMEOV1.B01`, which their background routines ask for, are in no pack.
- `ROM0.GFX` of the original Spec256 games (Jetpac, Sabre Wulf) is the `.GFB` of the game: rename it to
  `NAME.GFB` (the name is the same in several games, so it can not be found by the name of the snapshot).
- A `.GFA` / `.GF7` next to a 48K game is not used: a 48K game runs with `#7FFD` locked (ROM 1, banks 5, 2, 0).
- A `.GFB` or `.GFA` of 0 everywhere is left out.

### 128K

As ZX-Poly does (GZX shows the colours in 48K only):
- the `.GFX` holds the banks 5, 2 and the bank at C000 (`#7FFD & 7` of the snapshot); a `.GFn` is used
  instead of that part;
- a bank with neither gets its own bytes in every plane (not coloured: the ordinary Spectrum picture;
  ZX-Poly leaves it 0);
- the registers get the PC of the snapshot and IFF1 = IFF2. A 48K snapshot starts at PC `0072` (a RETN of the
  ROM), which pops its PC from the stack.

### `.CFG`

`key=value` lines; the defaults are those of ZX-Poly:

| Key | Default | |
|---|---|---|
| `Paper00InkFF` | 1 without backgrounds, 0 with; 0 for Booty, Cybernoid II, Eagle's Nest, Renegade | colour 0 is the PAPER of the attribute, 0xFF the INK |
| `HideSameInkPaper` | 1 | INK = PAPER: show that colour (hidden graphics) |
| `UpColorsMixed` | 64 | colours above 255 − n mixed 50/50 with the INK / PAPER of the pixel |
| `DownColorsMixed` | 0 | the same for the colours below n |
| `BkOverFF` | 0 | with a background, 0xFF is transparent too |
| `NN: addr=VVh` | | background NN while the byte at addr is VV (up to 16 rules, the first that matches) |

### The games of Spec256 DOS

The 12 games of Spec256 v1.2 (Army Moves 1 and 2, Cybernoid, Game Over 1 and 2, Jetpac, Knight Lore,
Phantis, Abu Simbel Profanation, Sabre Wulf, Solomon's Key, Underwurlde; known by the name of the 48K
snapshot) have no `.CFG`: the program chose their backgrounds with routines of its own and drew them in
its own way. As the Spec256 core for MiSTer (albconde/SPEC256_MISTER) read them from `SPEC256.EXE`, the
converter writes for them the block of the rules (below): the background routine of the game from the table
of games of the program, as conditions on bytes of the RAM, and the flag of the rendering of Spec256 DOS
(colours C0–FF take the INK of the attribute, 0xFF is a colour, the background only at colour 0, no mixing)
and of the arithmetic of Spec256 DOS: after an instruction that puts arithmetic into A (ADD, ADC, SUB, SBC
of a register or a number, AND, XOR, OR of a number, INC A, DEC A, DAA, LD A,n, IN A,(n), NEG, LD A,I / R,
IN A,(C)) every lane takes the A of the main CPU; AND, XOR, OR of a register keep the colour (the
"arithmetic mono" of the MiSTer core). A rule that shows a background without its file shows none.

### Fixes of games

By the name of the snapshot (`GAME_FIXES`, found by the Spec256 core for MiSTer):

| Game | Fix |
|---|---|
| Cybernoid II | `JR NC / SET 7,(HL)` (and `SET 0`), which wrap the bit leaving a row of a sprite on the carry of the main CPU, become `RL (HL) / RRC (HL)` (`RR / RLC`): the same for the main CPU, each lane with its own carry; the planes of those bytes = the code |
| Mad Mix 2 | the painted entries of its table of reversed bytes at `5B00` lose their colour |
| Jetpac | the coloured pixels of `7C65`–`7E08` become C0 + their brightness: with the DOS rendering they take the INK (the rocket changes colour as in the original) |
| Bruce Lee | colour 07 on paper pixels (bit 0 of the main byte), in the RAM and the ROM planes, becomes 0: the background shows there |

Read windows (the block of the windows, the `rules` of the MiSTer core's `spec256_games.ini`): where a game
looks up a table that only moves bits (a mirror, a shift, a mask) with a coloured index, each lane reads at
its own address (its HL, DE or BC) in the pages of the window, and every plane byte is XORed; Spec256 DOS
v1.2 does the same with readers of its own in Knight Lore, Sabre Wulf and Underwurlde. `LO[-HI]` are the
pages (A15..A8 of the address of the main CPU), `op=XX/MM` (`op!=`) a filter on the opcode:

| Game | Windows |
|---|---|
| Knight Lore | `F1; F2-FF op!=A6 xor=FF` |
| Sabre Wulf, Underwurlde | `F0-FF` |
| Head over Heels | `B9; 40-FF op=0A/EF` (`LD A,(BC)`, `LD A,(DE)`) |
| Scooby-Doo | `FC; 40-FF op=0A/EF` |
| Bubbler | `F9-FF` |
| Mad Mix 2 | `5B` |

The other keys of EmuZWin (`GFXLeveled*`, `UpMixChgBright`, `DownMixPaper`, …) are not used; what they mean
and why they do not matter for the games there are: [EZX.md](EZX.md#the-cfg-keys).

## The `.256` file

| Offset | Size | What |
|---|---|---|
| 0 | 49152 | the RAM 4000–FFFF: the banks 5, 2, 0 |
| 49152 | 393216 | its planes: 8 bytes per address, bit k of plane p = bit p of the colour of pixel k (a transpose of the `.GFX`) |
| 442368 | 28 | the registers, in the order of the `DIR` port of T80, and the border |
| 442396 | | the extension (not with `--plain`), little endian: |
| +0 | 4 | `K256` |
| +4 | 1 | version: 1; 2 with flag 4 or 5 (a core that knows version 1 leaves such an extension out) |
| +5 | 1 | flags: 0 ROM 1 planes, 1 Paper00InkFF, 2 HideSameInkPaper, 3 BkOverFF, 4 ROM 0 planes, 5 the 128K block, 6 the block of the rules (a core before converter v1.5 does not read it and plays as before), 7 the block of the windows (a core before v1.6 does not read it) |
| +6 | 1 | UpColorsMixed |
| +7 | 1 | DownColorsMixed |
| +8 | 1 | number of backgrounds (the highest Bnn + 1) |
| +9 | 1 | number of rules |
| +10 | 1 | the background shown first: the first rule that matches the snapshot, else the lowest Bnn; 0xFF none |
| +11 | 2 | the rules that match the snapshot (bit n: rule n) |
| +13 | 3 | the pages (high bytes) of the tables of reversed bytes `T[v] = reverse(v)`, 0: none |
| +16 | 768 | the palette, RGB |
| +784 | 64 | 16 rules: background, address (2), value |
| +848 | 131072 | ROM 1 planes (`.GFB`), if flag 0 |
| | 131072 | ROM 0 planes (`.GFA`), if flag 4 (flag 0 is then set too: a `.GFB` of 0) |
| | 49152 × n | the backgrounds, 256×192 each |
| | 8 + 5 × 147456 | the 128K block, if flag 5: `#7FFD` and 7 reserved bytes, then the banks 1, 3, 4, 6, 7: 16384 bytes of RAM and 131072 of planes each |
| | 160 | the block of the rules, if flag 6; it replaces the rules at +784 (and +10, +11): |
| ++0 | 1 | flags: 0 the rendering of Spec256 DOS, 1 the arithmetic of Spec256 DOS (the lanes take A after arithmetic) |
| ++1 | 1 | the background when no rule matches: n, `FE` none, `FF` the one there is |
| ++2 | 2 | the conditions that hold in the snapshot (bit n: condition n) |
| ++4 | 64 | 16 conditions: address (2), mask, value; it holds while the byte at the address, masked, = the value (< with its bit at ++68); the core follows the writes of the CPU |
| ++68 | 2 | the conditions that compare with < |
| ++72 | 64 | 16 rules: background (n, `FE` none, `FD` keep the one there is, `FF` no rule), conditions (2, bit n: condition n), reserved; the first rule whose conditions all hold |
| ++136 | 17 | reserved (zeros) |
| ++153 | 1 | the background at the start (n, `FE` none) |
| ++154 | 6 | reserved |
| | 64 | the block of the windows, if flag 7 (after the block of the rules, or in its place without flag 6): |
| ++0 | 1 | the number of windows (up to 8), then 7 reserved |
| ++8 | 48 | 8 windows: first page, last page, opcode value, opcode mask, flags (bit 0: negate the opcode test), xor. A read of data (not an M1 cycle) hits when the page of the address of the main CPU is in [first, last] and `((opcode ^ value) & mask) == 0` (or not, with bit 0); the opcode is the last byte read in an M1 cycle (`xx` of `CB xx` / `ED xx`, `CB` of `DD CB d xx`); the first window that hits wins. On a hit each lane reads at its own address (through HL, DE, BC) when the 8 differ, and each plane byte is XORed |
| ++56 | 8 | reserved |

A 48K game is version 1, byte for byte as the converter v1.3 wrote it.
