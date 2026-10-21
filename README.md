# dqix-debug

Source-level debugging for the [Dragon Quest IX decomp](https://github.com/ZevyaDev/dqix-decomp). Play the game in
melonDS and step through the decompiled C++ in VS Code: breakpoints in any `.cpp`, the call stack, arguments and
locals.

How it works: [ZevyaDev's melonDS fork](https://github.com/ZevyaDev/melonDS) runs the game with its GDB stub on.
VS Code's C/C++ debugger drives `gdb-multiarch`, which attaches to the stub. `make_dbg_elf.py` relinks the decomp with
debug info and writes `arm9_dbg.elf`, which tells gdb which source line each address came from.

## Getting started

### 1. What you need

- **A building dqix-decomp checkout**, cloned beside this repo:
  ```
  some-folder/
    dqix-decomp/    # ninja builds it, extract/baserom_dqix_usa.nds is present
    dqix-debug/     # this repo
  ```
  If the decomp lives elsewhere, set `DQIX_REPO=/path/to/dqix-decomp` when you run `make_dbg_elf.py`.
- **Python 3 with pyelftools** (`pip install pyelftools`). The decomp's venv usually has it already.
- **gdb-multiarch**: `sudo apt install gdb-multiarch`. Without root:
  ```
  apt-get download gdb-multiarch && dpkg-deb -x gdb-multiarch_*.deb ~/.local/opt/gdb-multiarch
  ln -s ~/.local/opt/gdb-multiarch/usr/bin/gdb-multiarch ~/.local/bin/gdb-multiarch
  ```
- **VS Code** with Microsoft's **C/C++** extension (`ms-vscode.cpptools`).
- **ZevyaDev's melonDS debug build**: download the AppImage from
  [github.com/ZevyaDev/melonDS/releases/latest](https://github.com/ZevyaDev/melonDS/releases/latest) and
  `chmod +x` it. Its `DEBUGGER.md` on the `debug` branch documents the built-in debugger window, symbols and Lua.

### 2. Set up melonDS (once)

Start melonDS once, then close it and edit `~/.config/melonDS/melonDS.toml`:

```toml
[Instance0.Gdb]
Enabled = true

[Instance0.Gdb.ARM9]
BreakOnStartup = false
Port = 3333

[JIT]
Enable = false
```

JIT must be off: breakpoints and stepping need the interpreter. The same settings are in Config > Emu settings.

### 3. Build the debug ELF

```
python make_dbg_elf.py
```

This runs `ninja build/usa/arm9.o` in the decomp, relinks with `-sym on` into `build/usa/dbg/`, and writes
`arm9_dbg.elf` here. It takes about 3 minutes. Rerun it after changing decomp sources; add `--no-build` if the decomp
is already built. The game code it links is the same as the normal build's.

`arm9_dbg.elf`, `overlays.json` and `*.bin` hold the game's compiled code. They are gitignored: never commit them.

### 4. Set up VS Code (once)

Copy the template into the decomp. VS Code reads it from there, and the decomp gitignores `.vscode/`:

```
mkdir -p ../dqix-decomp/.vscode && cp vscode/launch.json ../dqix-decomp/.vscode/launch.json
```

If `gdb-multiarch` is not on VS Code's PATH, set `miDebuggerPath` to its full path.

### 5. Debug

1. Start the game: `./melonDS-debug-x86_64.AppImage ../dqix-decomp/extract/baserom_dqix_usa.nds`
2. Open the `dqix-decomp` folder in VS Code and choose **Run > Start Debugging** (F5) with
   "DQIX: attach to melonDS (ARM9)". "Run Without Debugging" does nothing useful here.
3. VS Code attaches and pauses the game. Click in the gutter of any `.cpp` to set a breakpoint, then Continue (F5).
   The usual controls work: step over/into/out, the call stack, Variables, Watch, and the Debug Console (prefix gdb
   commands with `-exec`, e.g. `-exec info line *$pc`).
4. **Stop** detaches and leaves the game running, so you can attach again without restarting melonDS.

To break somewhere on every attach, add lines to `postRemoteConnectCommands` in launch.json, for example
`{ "text": "break *0x02188bf8" }`.

To check the setup from a terminal: `gdb-multiarch -batch -x smoke.gdb arm9_dbg.elf`. It attaches, breaks in a
per-frame function, prints source, locals and arguments, and detaches.

## Limits and troubleshooting

- **Overlays.** Main, ITCM and DTCM map to source. Overlays (battle, field, menus) share address ranges, and gdb shows
  whichever overlay's source it finds first: 0x02188bf8 shows ov008 even while ov009 is loaded. In overlay code, trust
  the disassembly over the source view.
- **One client at a time.** The stub serves one gdb.
- **"vMustReplyEmpty: timeout" on attach.** melonDS keeps no-ack mode after a client leaves. `vscode.gdb` and
  `smoke.gdb` run `set remote noack-packet off` to fix it. If you write your own gdb script, do the same.
- **Stop resets or freezes the game.** VS Code's Stop sends `kill`, and melonDS resets emulation and wedges on it.
  `vscode.gdb` defines `hook-kill` to detach first. Make sure launch.json still sources it.
- **The stub stops answering.** This happens if gdb crashes while attached. Restart melonDS.
- **Wrong line, or a breakpoint never hits after a code change.** Rebuild `arm9_dbg.elf`.

## What make_dbg_elf.py fixes in MWCC's output

- MWCC drops debug info at link time unless `-sym on` is passed, so it relinks with it.
- MWCC runs under wibo, so paths read `Z:\home\...`. It rewrites them to `/./home/...` (same length, so no offsets
  move).
- 3 compile units span from `.text` to a `.init` static initializer, covering about 600 KB of unrelated code. It trims
  them to their own functions.
- 26 member-pointer types reference DIE 0, and gdb aborts on them. It points them at a base type.
- mwldarm's ELF has no code sections, so gdb crashes setting any breakpoint. It writes a plain ELF with one section per
  region instead.

## Files

| File | What it is |
|------|------------|
| `make_dbg_elf.py` | Builds `arm9_dbg.elf` from the decomp |
| `vscode.gdb` | gdb settings for the melonDS stub, sourced by launch.json |
| `vscode/launch.json` | VS Code template, copied to `dqix-decomp/.vscode/` |
| `smoke.gdb` | Command-line check of the whole setup |
