#!/usr/bin/env python3
"""Drive a Karabas Go / Mini / Mini G board over its USB CDC port (Linux).

  kg_board.py version                    the firmware build, HW_ID and the running core
  kg_board.py at LINE...                 send AT lines, print the replies
  kg_board.py log [SECONDS]              print the debug log (debug=1), DIAG lines left out
  kg_board.py key KEYS...                press keys (AT+KARABAS=key:), e.g. menu+esc down enter
  kg_board.py type TEXT                  type a text (AT+KARABAS=type:)
  kg_board.py menu                       back to the boot core (Ctrl+Alt+Backspace)
  kg_board.py fw FILE.uf2                flash the MCU firmware (BOOTSEL, copy, wait for the port)
  kg_board.py sd FILE... [--to DIR]      copy files to the SD card through USB mass storage
                 [--sd2]                 (the second card: AT+KARABAS=msc2), compare, eject
  kg_board.py shot FILE.jpg [--video DEV] one frame of an HDMI capture device

The port is found by its id (/dev/serial/by-id/usb-Karabas_Go_*), and found again after the
board reboots (the number of ttyACM may change). Only the standard library: the port is opened
raw with termios and DTR set (the firmware writes only to an open terminal).

Every step that changes the board checks its result and stops with an error otherwise: a
firmware flash that went wrong half way may need the Boot button of the board.
"""

import argparse
import fcntl
import glob
import os
import select
import shutil
import struct
import subprocess
import sys
import termios
import time

PORT_GLOB = "/dev/serial/by-id/usb-Karabas_Go_*-if00"
MSC_GLOB = "/dev/disk/by-id/usb-Karabas_SD_Card*"
BOOTSEL_INFO = "INFO_UF2.TXT"
TIOCMBIS = getattr(termios, "TIOCMBIS", 0x5416)
TIOCM_DTR = getattr(termios, "TIOCM_DTR", 0x002)


def fail(msg):
    print("error: " + msg, file=sys.stderr)
    sys.exit(1)


def info(msg):
    print(msg, flush=True)


def wait_for(what, check, timeout, step=0.5):
    end = time.time() + timeout
    while time.time() < end:
        r = check()
        if r:
            return r
        time.sleep(step)
    fail("%s: not after %d s" % (what, timeout))


def find_port():
    ports = sorted(glob.glob(PORT_GLOB))
    return ports[0] if ports else None


def run(cmd, check=True):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if check and r.returncode != 0:
        fail("%s: %s" % (" ".join(cmd), r.stdout.strip()))
    return r.stdout


class Port:
    def __init__(self, timeout=10):
        path = wait_for("the board's port", find_port, timeout)
        self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        a = termios.tcgetattr(self.fd)
        a[0] = 0                                    # iflag
        a[1] = 0                                    # oflag
        a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        a[3] = 0                                    # lflag
        a[4] = a[5] = termios.B115200
        a[6][termios.VMIN] = 0
        a[6][termios.VTIME] = 0
        termios.tcsetattr(self.fd, termios.TCSANOW, a)
        fcntl.ioctl(self.fd, TIOCMBIS, struct.pack("I", TIOCM_DTR))
        self.buf = ""

    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass

    def write_line(self, line):
        os.write(self.fd, (line + "\r\n").encode())

    def read(self, seconds, until=None):
        """Read for seconds, or until a line starts with one of until; the lines."""
        end = time.time() + seconds
        while time.time() < end:
            r, _, _ = select.select([self.fd], [], [], 0.05)
            if r:
                try:
                    d = os.read(self.fd, 4096)
                except OSError:
                    break                           # the board went away (a reboot)
                if not d:
                    break
                self.buf += d.decode(errors="replace")
                if until and any(l.startswith(until) for l in self.buf.splitlines()):
                    break
        lines, self.buf = self.buf.splitlines(), ""
        return lines

    def drain(self):
        self.read(0.5)

    def at(self, line, seconds=3):
        """One AT+KARABAS line: its +KARABAS lines; fails on ERROR."""
        self.drain()
        self.write_line(line)
        lines = self.read(seconds, until=("OK", "ERROR"))
        lines = [l for l in lines if not l.startswith("DIAG") and l.strip()]
        if any(l.startswith("ERROR") for l in lines):
            fail("%s: ERROR" % line)
        return [l for l in lines if l.startswith("+KARABAS")]


def at_once(line, seconds=3):
    p = Port()
    try:
        return p.at(line, seconds)
    finally:
        p.close()


def version():
    """(build, hw_id, core)"""
    for l in at_once("AT+KARABAS=version"):
        f = l.split(":", 1)[1].split(";")
        return f[0], f[1], f[2]
    fail("no answer to AT+KARABAS=version")


def send_no_wait(line):
    """A line after which the board reboots: no answer is waited for."""
    p = Port()
    try:
        p.drain()
        p.write_line(line)
        p.read(1)
    finally:
        p.close()


def wait_port_back(old_gone=True):
    """old_gone: the board reboots now; its port goes away first (if it is seen within 10 s)."""
    if old_gone:
        end = time.time() + 10
        while time.time() < end and find_port():
            time.sleep(0.1)
    wait_for("the board's port back", find_port, 30)
    time.sleep(1)
    # the firmware answers once the APP task runs
    wait_for("the firmware answering", lambda: try_version(), 30, 1)


def try_version():
    try:
        p = Port(1)
    except SystemExit:
        return None
    try:
        p.drain()
        p.write_line("AT+KARABAS=version")
        return any(l.startswith("+KARABAS:") for l in p.read(2, until=("OK", "ERROR")))
    except OSError:
        return None
    finally:
        p.close()


def to_boot_core():
    if version()[2] == "boot":
        return
    info("back to the boot core")
    at_once("AT+KARABAS=key:ctrl+alt+bksp")
    wait_port_back()
    wait_for("the boot core", lambda: version()[2] == "boot", 20, 1)


def kernel_errors(since):
    out = run(["journalctl", "-k", "--since", since, "--no-pager"], check=False)
    return [l for l in out.splitlines() if "I/O error" in l]


def mounts():
    with open("/proc/mounts") as f:
        return [l.split() for l in f]


def mount_point(dev):
    real = os.path.realpath(dev)
    for m in mounts():
        if os.path.realpath(m[0]) == real:
            return m[1].replace("\\040", " ")
    return None


def bootsel_mount():
    for m in mounts():
        if os.path.exists(os.path.join(m[1].replace("\\040", " "), BOOTSEL_INFO)):
            return m[1].replace("\\040", " ")
    return None


def cmd_fw(args):
    uf2 = args.file
    if not os.path.isfile(uf2) or not uf2.endswith(".uf2"):
        fail("%s: not a .uf2 file" % uf2)
    if bootsel_mount():
        fail("a BOOTSEL drive is mounted already (%s): check the board" % bootsel_mount())
    to_boot_core()
    before = version()
    info("firmware %s, HW_ID %s: rebooting into BOOTSEL" % (before[0], before[1]))
    since = time.strftime("%Y-%m-%d %H:%M:%S")
    send_no_wait("AT+KARABAS=boot")
    mnt = wait_for("the BOOTSEL drive", bootsel_mount, 30)
    info("copying %s to %s" % (uf2, mnt))
    shutil.copy(uf2, mnt)
    os.sync()
    wait_port_back(old_gone=False)
    errors = kernel_errors(since)
    after = version()
    info("firmware %s, HW_ID %s, core %s" % after)
    if errors:
        print("warning: kernel I/O errors during the flash (often harmless at the reboot):", file=sys.stderr)
        for e in errors[-5:]:
            print("  " + e, file=sys.stderr)


def msc_disk():
    for d in sorted(glob.glob(MSC_GLOB)):
        if "-part" not in d:
            return d
    return None


def msc_part():
    """The first partition of the card. The disk is on the host also outside MSC mode (the MSC
    interface without a medium): the partition shows the card."""
    d = msc_disk()
    parts = sorted(glob.glob(d + "-part*")) if d else []
    return parts[0] if parts else None


def cmd_sd(args):
    for f in args.files:
        if not os.path.isfile(f):
            fail("%s: no such file" % f)
    if msc_part():
        info("the board is in USB mass storage already")
    else:
        to_boot_core()
        info("rebooting into USB mass storage")
        send_no_wait("AT+KARABAS=msc2" if args.sd2 else "AT+KARABAS=msc")
    part = wait_for("the SD card", msc_part, 60)
    time.sleep(3)                                   # the desktop may mount it by itself
    mnt = mount_point(part)
    if not mnt:
        run(["udisksctl", "mount", "-b", part])
        mnt = wait_for("the SD card mount", lambda: mount_point(part), 60)
    dest = os.path.join(mnt, args.to.strip("/"))
    if not os.path.isdir(dest):
        fail("%s: no such dir on the card" % args.to)
    since = time.strftime("%Y-%m-%d %H:%M:%S")
    ok = True
    for f in args.files:
        t = os.path.join(dest, os.path.basename(f))
        info("copying %s to %s" % (f, t))
        shutil.copyfile(f, t)
    os.sync()
    for f in args.files:
        t = os.path.join(dest, os.path.basename(f))
        if subprocess.run(["cmp", "-s", f, t]).returncode != 0:
            print("error: %s differs on the card" % t, file=sys.stderr)
            ok = False
    errors = kernel_errors(since)
    # unmount, then eject the drive: the firmware reboots on the eject (never power it off: the
    # board stays in MSC and is gone until replugged)
    run(["udisksctl", "unmount", "-b", part])
    disk = msc_disk()
    obj = None
    for l in run(["udisksctl", "info", "-b", os.path.realpath(disk)]).splitlines():
        if l.strip().startswith("Drive:"):
            obj = l.split(":", 1)[1].strip().strip("'")
    if not obj:
        fail("no UDisks2 drive of %s" % disk)
    run(["gdbus", "call", "--system", "--dest", "org.freedesktop.UDisks2", "--object-path", obj,
         "--method", "org.freedesktop.UDisks2.Drive.Eject", "{}"])
    info("ejected, waiting for the board")
    wait_for("the SD card going away", lambda: msc_part() is None, 30)
    wait_port_back()
    if errors:
        print("error: kernel I/O errors while copying:", file=sys.stderr)
        for e in errors[-5:]:
            print("  " + e, file=sys.stderr)
        ok = False
    info("core %s" % version()[2])
    if not ok:
        sys.exit(1)


def cmd_shot(args):
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "v4l2", "-input_format", "mjpeg",
         "-i", args.video, "-vf", "select=gte(n\\,5)", "-frames:v", "1", args.file])
    info(args.file)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("version")
    p = sub.add_parser("at"); p.add_argument("lines", nargs="+")
    p = sub.add_parser("log"); p.add_argument("seconds", nargs="?", type=float, default=5)
    p = sub.add_parser("key"); p.add_argument("keys", nargs="+")
    p = sub.add_parser("type"); p.add_argument("text")
    sub.add_parser("menu")
    p = sub.add_parser("fw"); p.add_argument("file")
    p = sub.add_parser("sd"); p.add_argument("files", nargs="+"); p.add_argument("--to", default="/")
    p.add_argument("--sd2", action="store_true")
    p = sub.add_parser("shot"); p.add_argument("file"); p.add_argument("--video", default="/dev/video4")
    args = ap.parse_args()

    if args.cmd == "version":
        info("firmware %s, HW_ID %s, core %s" % version())
    elif args.cmd == "at":
        p = Port()
        try:
            for l in args.lines:
                for r in p.at(l):
                    info(r)
        finally:
            p.close()
    elif args.cmd == "log":
        p = Port()
        try:
            for l in p.read(args.seconds):
                if not l.startswith("DIAG"):
                    info(l)
        finally:
            p.close()
    elif args.cmd == "key":
        at_once("AT+KARABAS=key:" + " ".join(args.keys))
    elif args.cmd == "type":
        at_once("AT+KARABAS=type:" + args.text)
    elif args.cmd == "menu":
        to_boot_core()
        info("core boot")
    elif args.cmd == "fw":
        cmd_fw(args)
    elif args.cmd == "sd":
        cmd_sd(args)
    elif args.cmd == "shot":
        cmd_shot(args)


if __name__ == "__main__":
    main()
