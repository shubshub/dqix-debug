# DQIX source-level debugging: melonDS + VS Code

1. Rebuild the debug ELF after source changes (about 3 minutes):
   `python make_dbg_elf.py` (add `--no-build` to skip `ninja build/usa/arm9.o`)
2. Start the game: `melonds-debug ../dqix-decomp/extract/baserom_dqix_usa.nds`
   (GDB stub on, port 3333 for ARM9, and JIT off are set in ~/.config/melonDS/melonDS.toml)
3. Open `dqix-decomp` in VS Code and press F5 ("DQIX: attach to melonDS (ARM9)", in its gitignored .vscode/).
   Set breakpoints by clicking in any .cpp; step, inspect args, locals and the call stack.

Command-line check: `gdb-multiarch -batch -x smoke.gdb arm9_dbg.elf` (attaches, breaks in the idle loop, detaches).

Notes
- Covers main, ITCM and DTCM. Overlays (battle, field, menus) share addresses, and gdb shows whichever overlay's
  source it finds first (e.g. 0x02188bf8 shows ov008 even when ov009 is loaded). Trust the disassembly there.
- The stub serves one client. It keeps no-ack mode after a client leaves, so the next connect fails
  ("vMustReplyEmpty: timeout") unless gdb runs `set remote noack-packet off` first (vscode.gdb and smoke.gdb do).
- VS Code's Stop sends `kill`, and melonDS resets emulation and wedges on vKill. vscode.gdb's `hook-kill`
  detaches first, so Stop leaves the game running. Tested: kill, then two reconnects.
- gdb-multiarch is unpacked under ~/.local/opt/gdb-multiarch (no root) and linked as ~/.local/bin/gdb-multiarch.
- What make_dbg_elf.py fixes in MWCC's output:
  - it relinks with `-sym on`
  - it rewrites `Z:\` paths to `/./`
  - it trims 3 compile units whose ranges span .text to .init
  - it retargets 26 null member-pointer type references
  - it writes a plain ELF with real code sections, because mwldarm's has none and gdb crashes on breakpoints
