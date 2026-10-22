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
| +5 | 1 | flags: 0 ROM 1 planes, 1 Paper00InkFF, 2 HideSameInkPaper, 3 BkOverFF, 4 ROM 0 planes, 5 the 128K block |
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

A 48K game is version 1, byte for byte as the converter v1.3 wrote it.
