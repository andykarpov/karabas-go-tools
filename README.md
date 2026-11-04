# Karabas Go Dev Tools

This repo contains various development tools to build Karabas Go cores, such as:

- **make_core** - a python script to create a packed core binary from the bitstream and json config, including additional resources, like ROMs, OSD menu, eeprom config, etc. Documentation: [make_core/README.md](make_core/README.md) ([по-русски](make_core/README.ru.md)) — usage, `core.json` reference with examples, the core file formats: `.kg` (kgo2, one file for all the boards, [docs/kgo2.md](docs/kgo2.md)) and the older `.kg1/.kg2/.kg3` (it supersedes `core_structure.txt`); the tools to convert, compare and dump core files. The MCU ↔ FPGA protocol is described in [karabas-go-firmware/docs/protocol.md](https://github.com/andykarpov/karabas-go-firmware/blob/master/docs/protocol.md).
- **board** - `kg_board.py`, drives a board from a Linux PC over USB: the `AT+KARABAS=` commands, keys, flashing the MCU firmware, copying cores to the SD card through USB mass storage, a frame of an HDMI capture. Documentation: [board/README.md](board/README.md).
- **spec256** - the converter of 256-colour games (Spec256 `.SNA` + `.GFX` and the rest, 48K and 128K, or EmuZWin `.ezx`) into the `.256` of karabas-go-core-spec256. Documentation: [spec256/README.md](spec256/README.md), the EmuZWin format: [spec256/EZX.md](spec256/EZX.md).

