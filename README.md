# Karabas Go Dev Tools

This repo contains various development tools to build Karabas Go cores, such as:

- **make_core** - a python script to create a packed core binary from the bitstream and json config, including additional resources, like ROMs, OSD menu, eeprom config, etc. Documentation: [make_core/README.md](make_core/README.md) ([по-русски](make_core/README.ru.md)) — usage, `core.json` reference with examples, the `.kg1/.kg2/.kg3` file format (it supersedes `core_structure.txt`). The MCU ↔ FPGA protocol is described in [karabas-go-firmware/docs/protocol.md](https://github.com/andykarpov/karabas-go-firmware/blob/master/docs/protocol.md).

