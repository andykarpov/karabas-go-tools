# The EZX format of EmuZWin and its 256 colours

EmuZWin 2.4 (Vladimir Kladov, 2003–2004) plays Spec256 games and saves them, with their colours, as one
`.ezx` file (the "state" of the emulator). Some games of the Spec256 collections exist only as `.ezx`
(Dizzy 2, Gun Runner, Head Over Heels, Highway Encounter, Mad Mix 2, Pac Mania); `spec256.py` reads them
(`ezx_extract`).

Sources: `EZXFormat_Eng.htm` of `EmuZWin_Addons.zip` (once at bonanzas.rinet.ru/zx/) for the layout and the
chunks; the compression and the details marked *checked* below come from reading the 11 `.ezx` of the
collection and comparing them with the `.SNA` / `.GFX` of the same games.

## The container

- Not compressed: the data start with `Emuz`.
- Compressed (from 2.4): `EZX` (3 bytes), then blocks: the length of the block (4 bytes, little endian),
  then that many bytes of **UCL NRV2E** with an 8-bit bit buffer (`ucl_nrv2e_decompress_8`; EmuZWin uses
  the DIUCL library of Ralf Junker, the description says "UPX algorithm"). The blocks unpacked one after
  the other give the uncompressed data, `Emuz` first. *Checked*: each block unpacks to 512K (524288 bytes),
  the last one to the rest (2 or 3 blocks in the collection); each ends where its length says.

## The fixed part

Little endian, packed (offsets checked on all the files):

| Offset | Size | What |
|---|---|---|
| 0 | 4 | `Emuz` |
| 4 | 16384 | ROM 0 (the 128 ROM) |
| 16388 | 16384 | ROM 1 (the 48 ROM) |
| 32772 | 8 × 16384 | the RAM banks 0..7 |
| 163844 | 1 | Lock7FFD: 1 = a 48K machine |
| 163845 | 43 | TSpecState (below) |
| 163888 | 17 | TSoundChipState: the last `#FFFD`, the 16 AY registers |
| 163905 | 4 | ReleaseDescriptor, not used |
| 163909 | 30 | TTapeData (a pointer, 5 integers, a byte, an integer, a boolean) |
| 163939 | | the chunks |

TSpecState (43 bytes):

| Offset | Size | What |
|---|---|---|
| 0 | 12 × 2 | AF, BC, DE, HL, IX, IY, AF', BC', DE', HL', PC, SP |
| 24 | 3 | I, R, the hidden register (MEMPTR) |
| 27 | 3 | IFF1, IFF2, the INT signal |
| 30 | 1 | IM |
| 31 | 4 | T-states since the last INT |
| 35 | 1 | the ROM at 0000: 0 = ROM 0, 1 = ROM 1, 2 = TR-DOS, 3 = IF1 |
| 36 | 1 | the RAM bank at C000 |
| 37 | 1 | the screen: 0 = bank 5, 1 = bank 7 |
| 38 | 1 | the border |
| 39 | 4 | MIC, just after EI, FLASH, frames since the FLASH switched |

*Checked*:
- The PC is in the registers, not on the stack (a `.SNA` of 48K pushes it: the RAM of the `.ezx` and the
  `.SNA` of Exolon differ in those two bytes only).
- A 48K state (Lock7FFD = 1) can have **bank 7** at C000 (Cybernoid II, Gun Runner): the 48K RAM is the banks
  5, 2 and the bank of offset 36, not always 5, 2, 0.
- R can be one more than in a `.SNA` of the same moment.
- The ROM 0 of EmuZWin differs from the usual 128 ROM in 65 bytes (`#2785`…, `#3BEC`…).

## The chunks

Each chunk is a name (4 bytes), a length (4 bytes) and the data, so that an unknown one can be skipped.
Those of the description: `NAME` (the file name), `RAM ` (banks 8..63 of bigger machines), `PORT`, `GS  `,
`POKS`, `BRKS`, `LABS`, `ASMZ`, `KEYS`, `JOY `, `AMXM`, `AYMS`, `COLR`, `LDIR`, `DISK`, `BETA`, `MDRV`, `DISD`,
`DISC`, `PRVW`, `MULT`, `AYST`, `MAP `, `TAPE`, and those of the 256 colours:

| Chunk | Data | What |
|---|---|---|
| `GFXM` | bank (1), 131072 | the colours of a bank, in the layout of a `.GFX` (8 bytes per byte, byte k = the pixel of bit k): 0..7 RAM, 16 ROM 0 (`.GFA`), 17 ROM 1 (`.GFB`), 18 TR-DOS ROM. Not saved when all 0. *Checked*: the same bytes as the `.GFX` of Exolon; every file also has a bank **19**, all 0 (not in the description) |
| `GFXR` | 23 × 8 | the GFX registers: F, A, C, B, E, D, L, H, IXL, IXH, IYL, IYH, SP low, SP high, I, F', A', C', B', E', D', L', H', 8 bytes (colours) each |
| `GFXB` | number (2), width (2), height (2), pixels | a background, 320×200 or 256×192, a palette index per pixel (a `.Bnn`) |
| `GFXP` | number (2), 768 | a palette (a `.Pnn`; background nn uses palette nn, else 00) |
| `GFXS` | 147456 | the buffers of GFXScreenXORbuffered |
| `GFXC` | text | the `.CFG` of the game |

### What `spec256.py` takes

| EZX | written as |
|---|---|
| ROMs, the RAM banks, the registers | `NAME.SNA`: 48K when Lock7FFD (the PC pushed below SP), else 128K with `#7FFD` = bank at C000, screen, ROM 1, and the PC |
| `GFXM` 5, 2 and the bank at C000 | `NAME.GFX`; a bank without `GFXM` gets its own bytes as colours (not coloured) |
| the other `GFXM` 0..7 (128K) | `NAME.GFn` |
| `GFXM` 16, 17 | `NAME.GFA`, `NAME.GFB` |
| `GFXB` | `NAME.Bnn` (256×192 put into 320×200 at x 32, y 4) |
| `GFXP` | `NAME.PAL`: the lowest number |
| `GFXC` | `NAME.CFG` |

Not taken: `GFXR` (the core starts every lane with the registers of the main CPU; EmuZWin says restoring them
is needed only sometimes, when a register keeps graphics for long), `GFXS`, the AY, the tape and the rest.
A state saved in TR-DOS / IF1 is refused; one with the shadow screen gives a warning (the core does not show
it).

## The CFG keys

`GFXC` (and a `.CFG`) of EmuZWin, as its description gives them, with the EmuZWin defaults:

| Key | EmuZWin default | Meaning |
|---|---|---|
| `GFXLeveledXOR` | 0 | XOR of two GFX bytes gives max(A, B) (A xor A still 0) |
| `GFXLeveledOR` | 0 | OR gives max(A, B) |
| `GFXLeveledAND` | 0 | AND gives min(A, B) |
| `OrderPaletteSignedBytes` | 0 | the indices compare as −128..127 in the leveled operations |
| `GFXScreenXORBuffered` | 0 | `XOR A,(HL) / LD (HL),A` on the screen (4000–57FF) keeps the old colours in a buffer, and the same XOR again restores them |
| `UpColorsMixed` | 64 | the top n colours are mixed with the attribute; up + down at most 128 |
| `DownColorsMixed` | 0 | the same for the lowest n |
| `UpMixChgBright` | 0 | 0..100 %: the part of the mixed result that follows the BRIGHT of the attribute rather than its colour |
| `DownMixChgBright` | 0 | the same for the low colours |
| `UseBrightInMix` | 0 | mix with the INK with its BRIGHT (else the 3 bits of the INK) |
| `UpMixPaper` | 0 | mix the top colours with the PAPER instead of the INK |
| `DownMixPaper` | 0 | the same for the low colours |
| `BkMixed` | 0 | the background pixels in the mixed ranges are mixed with the attribute too |
| `BkMixBkAttr` | 0 | with BkMixed: with the PAPER instead of the INK |
| `BkOverFF` | 1 | the background shows also through 0xFF, except where the INK of the attribute is 7 (white) |

Background rules: `NN: addr [& mask1, ..., maskN] = [byte1, ..., byteN] [; addr ...]`: background NN while
all the masked bytes at addr, addr+1, … are equal; of several that match, the longest, then the first.

In the collection (41 games, 28 CFG) only these keys are not 0: `UpColorsMixed`, `BkOverFF`,
`UpMixChgBright=50` (12 games, always with `UpColorsMixed=1`: only colour 255 is mixed), `DownMixPaper=1`
(13 games, always with `DownColorsMixed=0`: nothing is mixed below). So the mixing keys change nothing there,
and the rules are all of the short form `NN: addr=VVh`, which is what the converter reads. The core follows
ZX-Poly: `BkOverFF` defaults to 0 when a `.CFG` does not say, and has no exception for a white INK.
