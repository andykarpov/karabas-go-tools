# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Development tools for the Karabas Go / Mini / Mini G cores, plain Python 3 scripts with no dependencies outside the standard library:

- `make_core/make_core.py` packs a core file from a JSON description (`core.json`): the FPGA bitstream, the ROMs, the OSD menu and the core settings. An output named `*.kg` is kgo2 (`docs/kgo2.md`: one file for all the boards, `"boards"` in the json, `--boards` picks the boards to take bitstreams of, the others keep those of the existing file; `kg2_write()`), what every core uses since 2026-11-04; `*.kg1` / `.kg2` / `.kg3` is the older kgo1 (one board per file, `kgo1_write()`), still supported. Usage: `python3 make_core.py <core.json> <output file> [--boards ...]`, run from the dir the JSON's paths are relative to (a core's `src/`). Documentation: `make_core/README.md` and `README.ru.md` (the `core.json` reference and the kgo1 format), `docs/kgo2.md` (kgo2).
- `make_core/kg_dump.py` prints a `.kg`; `kg_compare.py` (with `kg_model.py`) compares what the firmware gets from two core files (kgo1 vs a board of a kgo2); `merge_boards.py` merges the per-board jsons into one kgo2 json; `kg1_to_json.py` turns a kgo1 file back into a json + files.
- `spec256/spec256.py` converts Spec256 / EmuZWin 256-colour games into the `.256` files of `karabas-go-core-spec256`. Documentation: `spec256/README.md`, `spec256/EZX.md`. The format is defined by this script and the loader of the core (`src/rtl/spec256.vhd`): a change goes into both.

## Related repositories (siblings in `..`)

- `karabas-go-firmware`: reads the core files. The header offsets are the `FILE_POS_*` constants of `src/config.h`, parsed by `lib/common/kg_format` (and `kg_matrix`); the OSD items and the protocol are in `docs/protocol.md`. A header change here needs the matching firmware change (and the other way round).
- `karabas-go-core-*`: the cores. They call `make_core.py` through a symlink `src/make_core.py` -> `../../karabas-go-tools/make_core/make_core.py`, so a change here reaches every core at its next pack: keep old `core.json` files working (a new key is optional, with the old behaviour as its default).
- `karabas-go`: the release repo of all the boards (`cores/*.kg`, `firmware/`); `karabas-mini` is archived (2026-11-04).

## Rules

- **The Python `make_core.py` is the one in use.** `makecore/` (Go) is untracked and not used: don't change it (the backlog has the question whether to develop or delete it).
- **A header field change** goes into `make_core.py`, `make_core/README.md`, `README.ru.md` and `core_structure.txt` together (kgo1); a kgo2 change into `make_core.py`, `docs/kgo2.md`, `kg_dump.py`, `kg_model.py` and the parser of the firmware (`lib/common/kg2_format`, its fixture).
- **Untracked files are the user's** (`makecore/`, `rs232mnt/`, `make_core/core_structure_v2.txt`): never add or delete them.
- **Check a change** by packing a few real cores before and after (e.g. the boot core in `../karabas-go-core-menu/src`, `python3 make_core.py core.json /tmp/boot.kg`) and comparing the files byte by byte (`cmp`): only the bytes of the changed field may differ. kgo1 must stay byte-identical too: pack a kgo1 json (the per-board jsons are in the cores' git history before 2026-11-04, e.g. `git show <commit>^:src/core_minig.json`) to a `.kg3` before and after. Don't run the cores' `make <board>-core` targets for this: they may start a full ISE build.
- Branches and PRs go to `master`; commit messages start with the tool (`make_core: ...`, `spec256: ...`).

## Memory

The Claude Code memory of this repo is shared with all karabas-go repos: `~/.claude/projects/<this project>/memory` is a symlink to `../karabas-go-notes` (private repo `andykarpov/karabas-go-notes`, `link.sh` there makes the links). Its `MEMORY.md` is split by repo; commit and push it after every memory change.
