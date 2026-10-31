# make_core: Karabas core files (.kg1 / .kg2 / .kg3)

[Русская версия](README.ru.md) · MCU ↔ FPGA protocol: [karabas-go-firmware/docs/protocol.md](https://github.com/andykarpov/karabas-go-firmware/blob/master/docs/protocol.md)

A core file packs everything the RP2040 firmware needs to start a core:

- the FPGA bitstream;
- the ROMs to load into the core;
- the OSD menu;
- the core settings: name, type, EEPROM bank, RTC mode, SPI clock, file loader settings.

`make_core.py` builds it from a JSON description (`core.json`).

| Board | File extension | Usual JSON name |
|---|---|---|
| Karabas Go | `.kg1` | `core.json` |
| Karabas Mini | `.kg2` | `core_mini.json` |
| Karabas Mini G | `.kg3` | `core_minig.json` |

The format is the same for all three. The extension only tells the firmware which board the bitstream is for, so each board needs its own bitstream and its own file.

## Building a core file

```
python3 make_core.py <core.json> <output file>
```

Paths inside the JSON (`bitstream`, ROM `filename`) are relative to the **current directory**, so run the script from the directory the JSON refers to. A typical script in a core repo (`src/`):

```sh
python3 make_core.py core.json       tsconf.kg1
python3 make_core.py core_mini.json  tsconf.kg2
python3 make_core.py core_minig.json tsconf.kg3
```

The bitstream is the `.bin` file from ISE (`bitgen -g Binary:yes`). Copy the resulting files to the root of the SD card. The boot core (`boot.kg1/2/3`) must be there too.

## core.json reference

The file must be strict JSON: no comments, no trailing commas (`{...},` before `]`).

### Top level

| Key | Type | Required | Meaning |
|---|---|---|---|
| `id` | string, ≤ 32 | yes | Core identifier. |
| `name` | string, ≤ 32 | yes | Name shown in the core list. |
| `build` | string, ≤ 8 | yes | Build / version string, usually `YYMMDDHH`. |
| `bitstream` | path | yes | FPGA bitstream (`.bin`). |
| `visible` | bool | yes | Show the core in the boot menu's core list. |
| `order` | 0–255 | yes | Sort order in the core list. |
| `type` | string | yes | `boot`, `osd`, `fileloader`; anything else (e.g. `hidden`, `none`) = no OSD. See below. |
| `eeprom_bank` | 0–255 | yes | `0`–`3`: a bank of the on-board 24C08 EEPROM; `4`–`254`: 256 bytes stored inside the core file; `255`: no EEPROM. |
| `rtc_mode` | 0–3 | no (0) | RTC register model: `0` MC146818A, `1` DS1307, `2` ZX Evolution (MC146818A, always BCD), `3` MSM6242B (Amiga, 13 BCD digits; firmware with MSM6242B support). |
| `spi_freq` | MHz | no (0) | Clock of the MCU ↔ FPGA SPI link for this core. `0` = default 16 MHz. |
| `save_dir` | string | no | Dir of the backup RAM files (`.sav`) of a core with backup RAM (caps bit 3, firmware `docs/protocol.md` "Backup RAM"), up to 32 characters. Not set: `<dir>/saves`. |
| `buttons` | object | no | Actions of the on-board buttons, see below. Not set: the button goes to the core. |
| `matrix` | string / object | no | What the LED matrix shows, see below. Not set: the core draws on it. |
| `dir` | string, ≤ 32 | no | `fileloader` cores: initial directory on the SD card. |
| `extensions` | string, ≤ 32 | no | `fileloader` cores: allowed extensions, comma separated (`.rom,.bin`). |
| `filename` | string | no | Keep it empty (`""`) or leave it out. The firmware uses this field to store the last selected file. |
| `roms` | array | yes (may be `[]`) | ROMs, see below. |
| `osd` | array | yes (may be `[]`) | OSD menu items, see below. |

Core types:

- **`boot`**: the boot menu. Its OSD is the core browser that lists the cores on the SD card. With the FT812 video chip present and enabled, the browser is drawn by the FT812.
- **`osd`**: a normal core. The OSD menu opens with `Menu+Esc`.
- **`fileloader`**: the OSD opens at start with a file browser over `dir` / `extensions`. The selected file is sent to the core with the file loader commands. `Menu+Esc` opens the browser again.
- **any other value**: no OSD at all.

### Buttons

`buttons` sets what the on-board buttons do in this core. Keys `btn1`, `btn2` (`btn3`..`btn6` are reserved for the extra buttons of the Karabas Mini G). A value is an action name, or an object:

| Key | Meaning |
|---|---|
| `press` | Action of a press. Default `core`. |
| `hold` | Action of a hold of `hold_ms`. Default: none. |
| `hold_ms` | 100–25400 ms, default 2000. |

Actions:

| Action | Meaning |
|---|---|
| `core` | The press and the release go to the core (`CMD_BTN`); the core decides (reset, NMI...). |
| `none` | Ignored. |
| `osd` | Opens / closes the OSD menu. |
| `menu` | Back to the boot menu. |
| `reload` | Loads the core again (hard reset). |
| `bootsel` | Reboots the MCU into BOOTSEL (firmware update). |
| `msc` | Reboots into USB mass storage (the SD card on the PC). |
| `msc2` | The same with the second SD card (the slot of the FPGA). |

With `press` set to `core`, the core gets the press at once and `hold` follows while the button is still held. With another `press`, a short press runs `press` on the release and a hold runs only `hold`.

```json
"buttons": {
    "btn1": "core",
    "btn2": {"press": "core", "hold": "menu", "hold_ms": 3000}
}
```

### LED matrix

`matrix` sets what the LED matrix add-on (16x8, red / green / yellow) shows in this core. A value is a mode name, or an object:

| Key | Meaning |
|---|---|
| `mode` | `core` (the default): the core draws on the matrix or shows its audio meters; the boot core scrolls `KARABAS GO`. `scroll`: scrolls `text`. `effect`: an animated `effect`. `image`: a picture, or an animation of up to 4 frames. `blank`: off. |
| `text` | `scroll`: up to 64 ASCII chars. `{name}`, `{build}`, `{time}` (HH:MM) and `{date}` (DD.MM.YYYY) are replaced at the start of each pass. |
| `color` | `scroll`: `yellow` (the default), `red`, `green`, `rainbow` (by character), `gradient` (by column: green, yellow, red). `effect` `scanner`: `red` (the default), `green`, `yellow`. |
| `step_ms` | 20–5100 ms: one pixel of the scroll, one step of the effect, one frame of the animation. Default: scroll 100, image 200, effect: its own. |
| `repeat` | `scroll`: passes of the text, `image`: loops of the animation (with one frame: steps of `step_ms`). Then `then` takes over. `0` (the default): forever. |
| `then` | After `repeat`: `core` (the default), `effect` or `blank`. |
| `effect` | `clock` (HH:MM, the seconds run along the bottom row), `fire`, `life` (Conway's Game of Life), `scanner`, `rain`, `plasma`, `stars`, `pong`, `drive` (the mounted disk images: a dot lit on an access, green read / red write, and the head position over the image in yellow). |
| `brightness` | 1–16, default 5. |
| `image` | One frame: 8 strings of 16 chars, `G` green, `R` red, `Y` yellow, `.` off. |
| `frames` | Up to 4 such frames, an animation. |

The core draws on the matrix (`CMD_MATRIX_*`) only in the `core` mode, or after `then: core`.

```json
"matrix": {"mode": "scroll", "text": "NES {build}", "color": "rainbow", "repeat": 2,
           "then": "effect", "effect": "fire"}
```

```json
"matrix": {"mode": "image", "step_ms": 300, "frames": [
    ["................", "..YYY...........", ".YYYYY..........", ".YYY............",
     ".YYYYY..........", "..YYY...........", "................", "................"],
    ["................", "..YYY...........", ".YYYYY..........", ".YYYYY..........",
     ".YYYYY..........", "..YYY...........", "................", "................"]
]}
```

### ROMs

```json
"roms": [
    {"filename": "roms/ts-bios.rom", "address": 0},
    {"filename": "roms/gs105b.rom",  "address": 2147483648}
]
```

- `address` is a 32-bit target address. Its meaning is up to the core: for example, TS-Conf maps bit 31 (`0x80000000` = 2147483648) to the General Sound ROM.
- The ROMs are sent to the core in this order on every core load. See `CMD_ROMLOADER` / `CMD_ROMDATA` in the [protocol description](https://github.com/andykarpov/karabas-go-firmware/blob/master/docs/protocol.md).
- `"external": true` stores only the file name in the core file. The firmware loads the ROM from that path on the SD card at every core start and shows `NO FILE` if it is missing. The file does not have to exist when the core file is built:

  ```json
  {"filename": "roms/zxnext.rom", "address": 0, "external": true}
  ```

### OSD items

Every item has a `type` and a `name`, at most 16 characters (a text line: 32). The item's **index** in the array is the switch number the core receives in `CMD_SWITCHES`. Don't reorder items without changing the core.

| `type` | Item | Keys | What the core gets |
|---|---|---|---|
| `S` | Switch: a value from a list, saved in the core file. | `options` (≤ 16 strings, ≤ 16 chars; firmware before the tree menus shows 8), `default`, `hotkey` | `CMD_SWITCHES (index, value)` at load and on change. |
| `N` | Non-volatile switch: like `S`, but the value is not saved. | same as `S` | same. |
| `T` | Trigger: a button. | `hotkey` (`options: null`, `default: 0`) | `CMD_SWITCHES (index, 1)`, then `(index, 0)` 100 ms later. |
| `H` | Hidden trigger: like `T`, not shown in the menu. | `hotkey` | same as `T`. |
| `P` | Plain text line, up to 32 characters. | `name` | nothing. |
| `FL` | File loader: pick a file, it is sent to the core at once. | `slot` (0–7), `extensions`, `hotkey`, optional `dir` / `filename` (the default file), optional `autoload` (bool: the file is also sent at core start, if it exists) | `CMD_IOCTL_*` sequence. |
| `M` | Page entry: opens the items of page `open` (a sub-menu). | `open` (1–255, one `M` per page) | nothing. |
| `-` | Separator: a line. | — | nothing. |
| `F` | File mounter: mount a disk image. | `slot` (0–7), `extensions`, `hotkey`, optional `dir` / `filename`, optional `physical` (bool: on a board with a floppy connector, Karabas Go, the browser also offers the physical drives) | `CMD_IMG_*`: the core reads and writes 512-byte sectors of the image; `CMD_IMG_PHYS` for a physical drive. |

`default` is the index of the default option. `hotkey` is described below. Up to 64 items (firmware before the tree menus reads 32).

### Sub-menus (pages) and conditional items

Every item can have:

- `"page": n` (0–255, default 0 = the main menu): the item is on page `n`. A page is opened by the `M` item with `"open": n`, which is itself on some page, so pages can nest. `make_core.py` stops on a page no `M` opens, a page opened twice or a loop.
- `"show_if"` or `"enable_if"`: `{"item": <index or unique name>, "value": <option index (0–63) or name>, "not": true|false}`. The item is shown (`show_if`) or can be chosen (`enable_if`, else drawn grey) when the switch `item` (an `S` / `N` with options) has `value`, or has not with `"not": true`.

The index of an item stays its position in the flat array, whatever its page: to turn a flat menu into a tree without changing the core, keep the items in order, add `page`, and append the `M` items at the end. Hotkeys work on any page. Firmware older than the tree menus shows all items in one list, the `M` and `-` items as plain rows.

```json
{"type": "S", "name": "Scanlines", "options": ["Off", "25%", "50%"], "default": 0, "page": 1},
{"type": "S", "name": "Scan color", "options": ["White", "Amber"], "default": 0, "page": 1,
 "enable_if": {"item": "Scanlines", "value": "Off", "not": true}},
{"type": "-"},
{"type": "M", "name": "Video", "open": 1}
``` The key `bits` that appears in some cores' JSON is ignored by `make_core.py`. It only notes how many bits the core decodes.

### Hotkeys

A hotkey is **zero or more modifiers and exactly one key**, joined with `+`:

```
"Menu+F6"   "Ctrl+Alt+Del"   "F12"   "Menu+J"
```

- **Modifiers:** `Ctrl`, `Shift`, `Alt`, `Menu` (the Win / GUI key). Left and right keys are the same.
- **Keys:**
  - letters `A`–`Z` and digits `0`–`9`;
  - `F1`–`F12`;
  - `Enter`, `Esc`, `Bkspace`, `Tab`, `Space`, `Caps`;
  - `PtrScr`, `ScrLk`, `Pause`;
  - `Ins`, `Del`, `Home`, `End`, `PgUp`, `PgDn`;
  - `Up`, `Down`, `Left`, `Right`.
- The text (≤ 16 chars) is shown in the menu next to the item.
- **Reserved by the firmware:** `Menu+Esc` toggles the OSD and `Ctrl+Alt+Bkspace` reboots the board. Don't use them.

`make_core.py` stops with an error on a hotkey without a key, with two keys or with an unknown name: such a hotkey would not fit into the 2 bytes the firmware reads. An empty string `""` means no hotkey.

### Examples

A normal core with switches, triggers, two ROMs and the ZX Evolution RTC (TS-Conf, Mini G):

```json
{
    "id": "tsconf",
    "name": "TS-Conf",
    "build": "26101416",
    "bitstream": "karabas_minig_top.bin",
    "visible": true,
    "type": "osd",
    "order": 3,
    "eeprom_bank": 0,
    "rtc_mode": 2,
    "roms": [
        {"filename": "roms/ts-bios.rom", "address": 0},
        {"filename": "roms/gs105b.rom", "address": 2147483648}
    ],
    "osd": [
        {"type": "S", "name": "PSG Mix", "options": ["ABC", "ACB", "Mono"], "default": 1, "hotkey": "Menu+F7"},
        {"type": "S", "name": "Joystick L", "options": ["Kempston", "Sinclair1", "Sinclair2", "Cursor"], "default": 0, "hotkey": "Menu+J"},
        {"type": "N", "name": "Pause", "options": ["Off", "On"], "default": 0, "hotkey": "Menu+P"},
        {"type": "T", "name": "NMI", "options": null, "default": 0, "hotkey": "F11"},
        {"type": "T", "name": "Reset", "options": null, "default": 0, "hotkey": "F12"}
    ]
}
```

A core with a file loader item in its OSD (Radio-86RK; the file goes through the ioctl commands):

```json
{
    "id": "rk86",
    "name": "Radio-86RK",
    "build": "26011000",
    "bitstream": "radio86rk_minig.bin",
    "visible": true,
    "type": "osd",
    "order": 8,
    "eeprom_bank": 6,
    "roms": [
        {"filename": "roms/BIOSSD.BIN", "address": 65536},
        {"filename": "roms/BIOS.BIN", "address": 69632}
    ],
    "osd": [
        {"type": "P", "name": "Please choose a tape image to"},
        {"type": "P", "name": "load into the the RAM"},
        {"type": "FL", "name": "Tape image", "slot": 1, "extensions": ".rkr,.rk,.gam", "hotkey": "Menu+T"},
        {"type": "S", "name": "ROM", "options": ["BIOSSD", "BIOS"], "default": 0, "hotkey": "Menu+B"},
        {"type": "T", "name": "Reset", "options": null, "default": 0, "hotkey": "Ctrl+Alt+Del"}
    ]
}
```

A file loader core (Alf; the file goes through the file loader commands):

```json
{
    "id": "alf",
    "name": "Alf",
    "build": "26101418",
    "bitstream": "karabas_minig_top.bin",
    "spi_freq": 64,
    "visible": true,
    "type": "fileloader",
    "dir": "alf",
    "filename": "",
    "extensions": ".rom,.bin",
    "order": 6,
    "eeprom_bank": 255,
    "roms": [
        {"filename": "rom/alf.rom", "address": 0}
    ],
    "osd": [
        {"type": "T", "name": "Reset", "hotkey": "Ctrl+Alt+Del"}
    ]
}
```

The boot core (`boot.kg*`, not listed itself):

```json
{
    "id": "boot",
    "name": "Boot Menu",
    "build": "26031015",
    "bitstream": "karabas_minig_top.bin",
    "visible": false,
    "type": "boot",
    "order": 1,
    "eeprom_bank": 0,
    "buttons": {"btn1": "bootsel", "btn2": "msc"},
    "roms": [],
    "osd": [
        {"type": "T", "name": "Reset", "options": null, "default": 0, "hotkey": "Ctrl+Alt+Del"}
    ]
}
```

## Core file format (signature `kgo1`)

All multi-byte numbers are **big-endian**. Strings are ASCII, padded with spaces (`make_core.py` writes zeros when an optional key is missing). The firmware reads the fields at the offsets `FILE_POS_*` in its `src/config.h`.

### Header (1024 bytes)

| Offset | Size | Field |
|---|---|---|
| 0 | 4 | Signature `kgo1` |
| 4 | 32 | `id` |
| 36 | 32 | `name` |
| 68 | 8 | `build` |
| 76 | 1 | `visible` (1 / 0) |
| 77 | 1 | `order` |
| 78 | 1 | Type: `0` boot, `1` osd, `2` fileloader, `255` none |
| 79 | 1 | `eeprom_bank` |
| 80 | 4 | Bitstream length `B` |
| 84 | 4 | ROM section length `R` (all ROM payloads + 8 bytes per ROM) |
| 88 | 1 | `rtc_mode` |
| 89 | 32 | File loader `dir`. The firmware may rewrite it. |
| 121 | 32 | File loader `filename`. The firmware stores the last selected file here as a 16-bit directory index in bytes 121–122. |
| 153 | 32 | File loader `extensions` |
| 185 | 1 | `spi_freq` (MHz, `0` = 16 MHz) |
| 186 | 32 | `save_dir`, `FF` when not set |
| 218 | 18 | Buttons `btn1`..`btn6`, 3 bytes each: `press`, `hold` (actions: `0` core, `1` none, `2` osd, `3` menu, `4` reload, `5` bootsel, `6` msc, `7` msc2), `hold_ms` / 100. `FF` = not set (`press`: core, no `hold`) |
| 236 | 20 | Reserved (`FF`) |
| 256 | 256 | EEPROM data, for `eeprom_bank` 4–254. Written by the firmware. |
| 512 | 256 | OSD switch values, one byte per OSD item: the defaults, then the values saved by the firmware. |
| 768 | 256 | LED matrix: +0 mode (`0` core, `1` scroll, `2` effect, `3` image, `4` blank), +1 color, +2 `step_ms` / 20 (`0` default), +3 `repeat`, +4 `then`, +5 effect, +6 brightness (`0` default), +7 frame count, +16 text (64), +80 four 32-byte frames (red plane, green plane, 2 bytes per row, bit 7 = left). `00` = core |

### Bitstream

Offset 1024, `B` bytes: the ISE `.bin` file, sent to the FPGA as is.

### ROM section

At `1024 + B`, `R` bytes in total, one block per ROM:

| Size | Field |
|---|---|
| 4 | Length of the data. Bit 31 set = external ROM: the data is a file name on the SD card. |
| 4 | Target `address` |
| n | ROM data (or the file name) |

### OSD section

At `1024 + B + R`:

| Size | Field |
|---|---|
| 1 | Number of items |
| … | Items, one after another |

One item:

| Size | Field |
|---|---|
| 1 | Type: `0` S, `1` N, `2` T, `3` H, `4` P, `5` F, `6` FL, `7` M, `8` separator |
| 1 | Flags: bit 0 = `physical` (`F` only), other bits reserved (0) |
| 16 | Name (`P`: the first 16 characters of the text) |
| 1 | Default value (`M`: the page it opens) |
| | **`F` / `FL`:** |
| 1 | Slot (bits 0–6), autoload flag (bit 7) |
| 256 | Extensions |
| 256 | Directory, padded with NULs. The firmware writes the last directory here. |
| 256 | File name, padded with NULs. The firmware writes the last file here. |
| | **other types:** |
| 1 | Number of options `n` (the firmware reads at most 16, before the tree menus 8) |
| 16 × n | Option names |
| | **all types:** |
| 16 | Hotkey text (`P`: characters 17–32 of the text) |
| 2 | Hotkey codes: modifier mask (Ctrl `11`, Shift `22`, Alt `44`, Menu `88`, OR-ed), USB HID key code |
| 1 | Page of the item (0 = the main menu) |
| 1 | Condition: the index + 1 of the switch it depends on, 0 = none |
| 1 | Condition: bit 7 disable (else hide), bit 6 invert, bits 0–5 the value. Shown / enabled when (the switch's value == value) xor invert |

Each item's default is also written to its byte at offset 512 + index.
