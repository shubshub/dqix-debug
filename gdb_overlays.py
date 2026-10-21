# Sourced by vscode.gdb. Overlays share addresses, so arm9_dbg.elf has every overlay switched off, and this
# keeps gdb's symbols on the overlays the game has loaded: it reads the game's overlay slot table, switches
# those overlays on in a copy (arm9_live.elf) and reloads it. It runs when gdb first stops after attaching,
# and at each overlay load (a breakpoint gdb never stops at on DecompressAndStaticInitializeOverlay, which
# runs before the overlay's code does), so breakpoints in an overlay's source go live as it loads.
# `dqix-overlays` reports what is loaded.
import gdb, json, os, struct

HERE = os.path.dirname(os.path.abspath(__file__))
INFO = json.load(open(os.path.join(HERE, "arm9_dbg.json")))
live = None  # overlay ids arm9_live.elf has switched on


def slots():
    """Overlay ids in the game's slot table: row data_01ffd348 of data_01ffd364[8][6], -1 = empty."""
    mem = gdb.selected_inferior().read_memory
    row = struct.unpack("<i", mem(INFO["row_index"], 4))[0]
    return {i for i in struct.unpack("6b", mem(INFO["rows"] + row * 6, 6)) if 0 <= i < len(INFO["overlays"])}


def switch(ids):
    global live
    ids = frozenset(ids)
    if ids == live:
        return
    data = bytearray(open(os.path.join(HERE, "arm9_dbg.elf"), "rb").read())
    for i in ids:
        ov = INFO["overlays"][i]
        struct.pack_into("<I", data, ov["flags_at"], 0x6)  # SHF_ALLOC | SHF_EXECINSTR
        for off, on, _ in ov["patches"]:
            struct.pack_into("<I", data, off, on)
    path = os.path.join(HERE, "arm9_live.elf")
    open(path + ".tmp", "wb").write(data)
    os.replace(path + ".tmp", path)  # a new file: gdb may still be reading the old one
    gdb.execute(f"symbol-file {path}", to_string=True)
    live = ids


class OverlayLoad(gdb.Breakpoint):
    def stop(self):
        # r0 is the OverlayMetadata being loaded; overlayIndex is its first word. Its slot was emptied first.
        new = struct.unpack("<I", gdb.selected_inferior().read_memory(int(gdb.parse_and_eval("$r0")), 4))[0]
        switch(slots() | {new})
        return False


def on_stop(_):
    if live is None:
        switch(slots())


def on_disconnect(_):
    global live
    live = None


class Overlays(gdb.Command):
    """Show the overlays the game has loaded and the ones gdb has source for."""
    def __init__(self):
        super().__init__("dqix-overlays", gdb.COMMAND_STATUS)

    def invoke(self, arg, from_tty):
        print(f"loaded: {sorted(slots())}  symbols: {sorted(live or ())}")


OverlayLoad(f"*{INFO['hook']:#x}", internal=True)
gdb.events.stop.connect(on_stop)
gdb.events.connection_removed.connect(on_disconnect)
Overlays()
