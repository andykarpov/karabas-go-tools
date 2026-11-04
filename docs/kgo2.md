# Core file format kgo2 (`.kg`)

Status: **draft**, agreed in outline (2026-11-04), not implemented. It replaces the older sketch
`make_core/core_structure_v2.txt`. The current format, kgo1 (`.kg1` / `.kg2` / `.kg3`), is described
in [make_core/README.md](../make_core/README.md#core-file-format-signature-kgo1) and stays supported.

## Why

kgo1 has fixed fields (a 32 byte loader dir, 256 bytes per F slot field, 16 byte names) and the
firmware writes the user's state back into the core file: the switches, the F / FL images, the last
file of the loader, the EEPROM of banks 4..254. So:

- copying a new build of a core over the old one loses every setting of the user;
- the settings are tied to positions: a switch is the byte of its item's position, a value is the
  position of the option. Moving an item or an option in `core.json` changes what the RTL gets and
  what the saved settings mean;
- one core needs three files (`.kg1`, `.kg2`, `.kg3`) and three almost equal `core.json`;
- the core file is written by the firmware, a failed write can damage it.

kgo2:

- **one file for all boards** (`.kg`), its parts tagged by a 16-bit board mask;
- **the core file is read-only** for the firmware: it holds the description and the defaults, the
  user's state is in `/config/<core id>.ini` and `/config/<core id>.eep` on the SD card;
- **three layers per item and option**: the order of the menu (the position in `core.json`), the
  numbers the RTL gets (`index`, `value`), the keys the settings are saved under (`key`). Each can
  change without the others;
- **no fixed string lengths**: all strings are in a string pool.

## Boards

| Board | HW_ID | Name in `core.json` | Mask bit |
| --- | --- | --- | --- |
| Karabas Go | 1 | `go` | `1 << 1` |
| Karabas Mini | 2 | `mini` | `1 << 2` |
| Karabas Mini G | 3 | `minig` | `1 << 3` |

Bit `n` is HW_ID `n`; bit 0 is not used. A file may have any subset of the boards, one board only
is a valid file. The firmware lists a `.kg` only if it has a bitstream for its board.

## core.json

One `core.json` describes the core for every board: the common keys at the top level and, in
`boards`, what differs per board (variant A of the draft).

```json
{
  "id": "msx",
  "name": "MSX1",
  "build": "26103108",
  "type": "osd",
  "visible": true,
  "order": 12,
  "eeprom_bank": 255,
  "roms": [ {"filename": "roms/cbios_main_msx1_eu.rom", "address": 0} ],
  "boards": {
    "go":    { "bitstream": "karabas_go.bin" },
    "mini":  { "bitstream": "karabas_mini.bin" },
    "minig": { "bitstream": "karabas_minig.bin", "spi_freq": 16 }
  },
  "osd": [
    { "type": "F", "key": "disk_a", "name": "Disk A", "slot": 0, "exts": ["dsk"], "dir": "/msx",
      "boards": ["go"], "physical": true, "hotkey": "Menu+F3" },
    { "type": "F", "key": "disk_a", "name": "Disk A", "slot": 0, "exts": ["dsk"], "dir": "/msx",
      "boards": ["mini", "minig"], "hotkey": "Menu+F3" },
    { "type": "S", "key": "video", "index": 7, "name": "Video", "default": "pal", "hotkey": "Menu+V",
      "options": [ {"key": "pal", "name": "PAL 50Hz", "value": 0},
                   {"key": "ntsc", "name": "NTSC 60Hz", "value": 1} ] }
  ]
}
```

### Boards

- `boards` has one object per board the file is made for, with its `bitstream` and any top-level
  key that differs on that board. make_core merges it over the top level: objects (`buttons`,
  `matrix`, `loader`) key by key, everything else (numbers, strings, arrays) is replaced.
- An OSD item with `"boards": [...]` is on these boards only; without it, on all. Two items may
  have the same `key` on disjoint boards: one setting with a different look per board.
- make_core can pack the boards it has bitstreams for, and can add or replace the bitstream of one
  board in an existing `.kg` (a core is often built for Mini G first).

### Keys

- `key` of an item: `a-z`, `0-9`, `_`, 1..16 chars. Without it make_core makes it from the name:
  lower case, every run of other chars becomes `_`, cut to 16 (`"FM (MSX-MUSIC)"` -> `fm_msx_music`).
  When an item is renamed, write its old key into `key` and the users keep their setting.
- `key` of an option: the same rules, made from the option text when not given.
- Keys are unique per board among the items that keep a state (S, F, FL) and among the options
  of an item. Items without a state (N, T, H, P, M, -) need no key.

### Numbers for the RTL

- `index` of an item: the switch number of `CMD_SWITCHES`, 0..254. Default: the position of the
  item in the flat `osd` list, as in kgo1 (so a converted core needs no RTL change). Unique per
  board.
- `value` of an option: the byte sent to the core for that option, 0..255. Default: the position of
  the option. Unique within the item, gaps allowed.
- `default` of an item names an option by its key (or its text); a number is taken as a position,
  as in kgo1. `show_if` / `enable_if` work as in kgo1 (`item`: a key, a name or a position;
  `value`: an option key, text or position) and are packed as the option `value`.

So the menu can be reordered and options can be moved or inserted without touching the RTL or
losing the user's settings.

### Options

`options` is a list of strings (as in kgo1) or of objects `{ "name", "key", "value" }`; both may be
mixed. Up to 16 options, names up to 16 chars (the width of the OSD column).

### Files: the loader and F / FL items

```json
"loader": { "dir": "/nes", "exts": ["nes", "ines"], "file": ["Super Mario Bros.nes"],
            "autoload": true, "save_dir": "/nes/saves" }
```

- `loader` (FILELOADER cores): `dir` the start dir of the file list, `exts`, `file` the default file,
  `autoload` load the default / last file at the start of the core, `save_dir` the dir of the
  backup RAM files. The kgo1 top-level keys `dir`, `extensions`, `filename`, `save_dir` are taken
  into `loader` when it is not given.
- F / FL items: `slot`, `dir`, `exts`, `file`, `autoload` (FL), `physical` (F, Karabas Go: the
  physical floppy drives in the browser), `readonly` (F: the image is mounted without writes).
- `exts`: a list (`["dsk", "img"]`) or the kgo1 string (`".dsk,.img"`).
- `file`: a string or a list of candidates; the first one that exists is used
  (`["kick13.rom", "kick.rom"]`). A path relative to `dir`, or from the root with `/`. The kgo1 key
  `filename` is the same.

## The user's state: `/config/<core id>.ini`, `/config/<core id>.eep`

The firmware never writes the core file. What the user changes goes into `/config/<core id>.ini`
(made when the first value is saved); the EEPROM of banks 4..254 goes into `/config/<core id>.eep`
(256 bytes, binary; its first content is the `EEPROM_INIT` section, else FF). One file per core id,
shared by the boards (a card moved between boards keeps its settings).

```ini
; msx, written by the firmware
[core]
build=26103108

[osd]
video=ntsc

[file]
disk_a=/msx/dsk/Aleste.dsk
cart_b=

[loader]
file=/nes/test/Aladdin.nes
```

- `[osd]` `key=option key`: only the S items whose value differs from the default. N items are not
  saved (as in kgo1).
- `[file]` `key=path` of the F / FL items: the full path of the image the user chose, or empty when
  the user ejected it (the default is not mounted then). No line: the default (`dir` + `file`).
- `[loader]` `file=` the full path of the last loaded file; the file list opens in its dir, else in
  `loader.dir`. Replaces the kgo1 pair of the file id in the core file and `karabas.ini`
  `[fileloader]`.
- `[core]` `build=`: the build that wrote the file, for the log only.
- Lines are up to 511 chars (the paths). The file is rewritten whole through a `.new` file, 2 s
  after the last change, when the OSD is closed and before another core or a reboot.

### Old settings (another build of the core)

The values are matched by key, never by position:

- a key that is not in the file: the default of the core. A changed default reaches every user who
  did not change that setting;
- a value that is not an option of the item any more, or a key whose item changed its type: the
  default; the line stays in the file;
- keys that this core / board does not have stay in the file (another build, another board), so
  going back to an older build brings its settings back. Only "Reset settings" removes them;
- a file that does not exist (a default or a saved one): an empty slot, no error.

The risk left is a key that means different things on different boards: give such items different
keys.

## Binary layout

All numbers are little-endian. Offsets are from the start of the file unless said otherwise.

### Header (32 bytes)

| Offset | Size | Field |
| --- | --- | --- |
| 0 | 4 | signature `kgo2` |
| 4 | 1 | format version: 1 |
| 5 | 1 | reserved, 0 |
| 6 | 2 | header size: 32 |
| 8 | 2 | number of sections |
| 10 | 2 | size of a section table entry: 16 |
| 12 | 2 | board mask of the file: the boards with a bitstream |
| 14 | 18 | reserved, 0 |

### Section table (from offset 32, 16 bytes per entry)

| Offset | Size | Field |
| --- | --- | --- |
| 0 | 2 | type |
| 2 | 2 | board mask: the boards the section is for |
| 4 | 4 | offset of the section |
| 8 | 4 | length of the section |
| 12 | 4 | reserved, 0 |

For each type a board has at most one section. make_core writes a section once when it is the same
for several boards (one mask with their bits). The firmware takes, for each type, the section with
its bit and skips unknown types (a newer format version may add sections). Sizes in the records
let a newer version append fields: the firmware reads the fields it knows and skips the rest.

| Type | Section | Needed |
| --- | --- | --- |
| 1 | STRINGS | yes |
| 2 | CORE | yes |
| 3 | LOADER | FILELOADER cores |
| 4 | OSD | no |
| 5 | BUTTONS | no (all buttons go to the core) |
| 6 | MATRIX | no (`core`) |
| 7 | EEPROM_INIT | no (FF) |
| 8 | ROMS | no |
| 9 | BITSTREAM | yes |

### STRINGS

NUL-terminated strings, ASCII (paths may be UTF-8). A string is referenced by a 16-bit offset into
this section; offset 0 is the empty string (the section starts with a NUL). make_core writes every
distinct string once. One STRINGS section serves every board.

### CORE

| Offset | Size | Field |
| --- | --- | --- |
| 0 | 2 | size of this record |
| 2 | 2 | id (string) |
| 4 | 2 | name (string) |
| 6 | 2 | build (string) |
| 8 | 1 | type: 0 boot, 1 osd, 2 fileloader, 255 hidden |
| 9 | 1 | visible in the core list: 0 / 1 |
| 10 | 1 | order 0..255 |
| 11 | 1 | RTC mode (as kgo1) |
| 12 | 1 | EEPROM bank (as kgo1: 0..3 the 24C08, 4..254 the `.eep` file, 255 none) |
| 13 | 1 | SPI frequency in MHz, 0 = default |
| 14 | 2 | reserved, 0 |

### LOADER

| Offset | Size | Field |
| --- | --- | --- |
| 0 | 2 | size of this record |
| 2 | 2 | dir (string) |
| 4 | 2 | extensions (string, comma separated, without dots: `nes,ines`) |
| 6 | 2 | save dir (string, empty: `<dir>/saves`) |
| 8 | 1 | flags: bit 0 autoload |
| 9 | 1 | number of file candidates |
| 10 | 2 | offset (in this section) of the candidates: 2 bytes (a string) each |

### OSD

| Offset | Size | Field |
| --- | --- | --- |
| 0 | 2 | number of items |
| 2 | 2 | size of an item record (48) |
| 4 | 4 | reserved, 0 |
| 8 | ... | the item records, then the option records and the file candidates they point to |

Item record (48 bytes):

| Offset | Size | Field |
| --- | --- | --- |
| 0 | 1 | type: 0 S, 1 N, 2 T, 3 H, 4 P, 5 F, 6 FL, 7 M, 8 separator (as kgo1) |
| 1 | 1 | flags: bit 0 physical (F), bit 1 read-only (F), bit 2 autoload (FL), bits 3..7 reserved |
| 2 | 1 | switch index (`CMD_SWITCHES`), 255 = none |
| 3 | 1 | page of the item, 0 = the main menu |
| 4 | 1 | M: the page it opens |
| 5 | 1 | the item of the condition + 1 (its number in this section), 0 = none |
| 6 | 1 | condition: bit 7 disable (else hide), bit 6 invert |
| 7 | 1 | condition value: the option `value` |
| 8 | 1 | default: the option `value` (S, N) |
| 9 | 1 | slot (F, FL) |
| 10 | 1 | hotkey modifiers (as kgo1) |
| 11 | 1 | hotkey key code (as kgo1) |
| 12 | 1 | number of options |
| 13 | 1 | number of file candidates |
| 14 | 2 | reserved, 0 |
| 16 | 2 | key (string) |
| 18 | 2 | name (string; P: the whole line, up to 32 chars) |
| 20 | 2 | hotkey text (string) |
| 22 | 2 | extensions (string, F / FL) |
| 24 | 2 | dir (string, F / FL) |
| 26 | 2 | offset (in this section) of the option records |
| 28 | 2 | offset (in this section) of the file candidates: 2 bytes (a string) each |
| 30 | 18 | reserved, 0 |

Option record (8 bytes): key (string, 2), name (string, 2), value (1), reserved (3).

### BUTTONS

1 byte: the number of buttons (6), then 3 bytes per button as in kgo1 (press action, hold action,
hold time / 100 ms; FF = not set).

### MATRIX

The 256 bytes of the kgo1 matrix block (`FILE_POS_MATRIX`, `kg_matrix` of the firmware).

### EEPROM_INIT

256 bytes: the first content of `/config/<core id>.eep`.

### ROMS

The ROM blocks as in kgo1, but little-endian: length (4, bit 31 = external: the payload is a file
name on the SD card), address (4), payload. One section serves every board that has the same ROMs.

### BITSTREAM

The FPGA bitstream of the board(s) of its mask (one board each in practice).

## Firmware

- Reads `.kg` files whose board mask has its HW_ID, and `.kg1` / `.kg2` / `.kg3` (kgo1) as before.
  For kgo1 nothing changes: the state stays in the core file, no ini.
- The state of a kgo2 core is in `/config/<core id>.ini` / `.eep`; the core file is opened for
  reading only.
- New: "Reset settings" (deletes `/config/<core id>.ini`), the read-only flag of F items (the
  firmware refuses the write requests of the core, and tells the core through a bit of the
  `CMD_IMG_*` mount frames, to be defined in `docs/protocol.md`).

## Steps

1. **make_core**: kgo2 writer next to kgo1 (`make_core.py core.json out.kg`: the format from the
   extension), the `boards` merge, keys, `index` / `value`, the checks, adding one board's
   bitstream to an existing `.kg`; README; kgo1 output unchanged (byte compare).
2. **Firmware, reading**: a kgo2 parser in `lib/common` (host tests on files made by make_core),
   the core list with `.kg`, `read_core()` filling the same `core` structure; the state still in
   memory only.
3. **Firmware, state**: `/config/<id>.ini` / `.eep` (matching by key, the rules above, debounced
   writes), the loader file, Reset settings; `karabas.ini [fileloader]` is used by kgo1 cores only.
4. **Read-only images**: the protocol bit, the firmware, a core that shows it.
5. **Cores**: one `core.json` per core, `.kg` into the release repos (with the core CI).
