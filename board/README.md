# kg_board.py

Drives a Karabas Go / Mini / Mini G board from a Linux PC over its USB serial port: the AT
commands of the firmware (`AT+KARABAS=`, see the firmware README), flashing the MCU firmware and
copying cores and other files to the SD card. Python 3, only the standard library; `udisksctl`,
`gdbus`, `journalctl` for the SD card, `ffmpeg` for `shot`.

```
kg_board.py version                    the firmware build, HW_ID and the running core
kg_board.py at LINE...                 send AT lines, print the replies
kg_board.py log [SECONDS]              print the debug log (debug=1), DIAG lines left out
kg_board.py key KEYS...                press keys, e.g. menu+esc down enter (names: firmware kg_keys)
kg_board.py type TEXT                  type a text
                                       (key, type: --sync returns when it has been delivered)
kg_board.py state                      the running core, the OSD screen, the file items
kg_board.py load CORE                  start a core (file name or id) from any core; boot: reboot
kg_board.py reset                      start the running core again, with clean memory
kg_board.py osd [ITEM[=VALUE]]         the menu items of the core: all, one, set (name or number)
kg_board.py mount ITEM PATH            an image for a file item
kg_board.py eject ITEM                 no image
kg_board.py mouse DX DY [BTNS [WHEEL]] move, BTNS = "" keeps the buttons held (bit 0 left, 1 right, 2 middle)
kg_board.py click [left|right|middle]  a mouse click
kg_board.py pad 0|1 BUTTONS... [--hold] pad buttons (up+a), port 0 or 1, released after each
kg_board.py release                    all keys, mouse buttons and pad buttons up
kg_board.py sync                       waits until the queued input has been delivered
kg_board.py debug 0|1                  the debug log until the next reboot
kg_board.py menu                       back to the boot core (Ctrl+Alt+Backspace)
kg_board.py fw FILE.uf2                flash the MCU firmware
kg_board.py sd FILE... [--to DIR]      copy files to the SD card (--sd2: the second card)
kg_board.py shot FILE.jpg [--video DEV] one frame of an HDMI capture device (default /dev/video4)
```

- The port is found by its id (`/dev/serial/by-id/usb-Karabas_Go_*`) and found again after a
  reboot, when the number of `ttyACM` may change.
- `fw` and `sd` go back to the boot core first (rebooting into BOOTSEL from another core often
  fails). `fw`: `AT+KARABAS=boot`, the uf2 copied to the BOOTSEL drive, then it waits for the
  firmware to answer and shows the kernel I/O errors of that time (a few at the reboot are
  harmless).
- `sd`: `AT+KARABAS=msc`, waits for the card (the "Karabas SD Card" disk is on the host also
  outside MSC mode, without a medium: its partition shows the card), mounts it if the desktop did
  not, copies, compares, unmounts and ejects it through UDisks2 (the firmware reboots on the eject),
  then waits for the board. Never power the drive off (`udisksctl power-off`): the board stays in
  MSC mode and is gone until it is plugged again. The cores of a `.kg` go into the root, the
  default `--to /`.
- Each step that changes the board checks its result and stops with an error otherwise.
- With some cores (UKNC on Mini and Mini G, Atari ST) the USB of the board resets every few seconds: commands
  fail with "no answer", and after a `load` of such a core its port may stay away until the board is replugged.
  Use a core with a stable USB for checks of the board itself.
