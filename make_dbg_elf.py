#!/usr/bin/env python3
"""Build arm9_dbg.elf: the decomp's ARM9 link with DWARF line info kept, for source-level debugging
against melonDS's GDB stub.

usage: python make_dbg_elf.py [--no-build]

1. `ninja build/usa/arm9.o` in the decomp so every object is current (skip with --no-build).
2. Re-run the link command from build.ninja's `mwld` rule with `-sym on` into build/usa/dbg/.
   The game code is unchanged by it (build/usa/dbg/build/arm9.bin equals the normal build's).
3. MWCC runs under wibo, so DWARF paths read `Z:\\home\\...\\`. Rewrite each to `/./home/.../` in place
   (same length, so no offset moves) and write arm9_dbg.elf beside this script.
"""
import json, os, re, subprocess, sys
from elftools.elf.elffile import ELFFile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("DQIX_REPO", os.path.join(os.path.dirname(HERE), "dqix-decomp"))  # default: cloned beside us
OUT = os.path.join(HERE, "arm9_dbg.elf")
RAW = "build/usa/dbg/arm9_dbg.o"

if "--no-build" not in sys.argv:
    subprocess.run(["ninja", "build/usa/arm9.o"], cwd=REPO, check=True)

ninja = open(os.path.join(REPO, "build.ninja"), encoding="utf-8").read().replace("$\n", " ")
cmd = re.search(r"^rule mwld\n\s+command = (.+)$", ninja, re.M).group(1)
cmd = re.sub(r"\s+", " ", cmd).replace("$objects_file", "build/usa/objects.txt") \
    .replace("$lcf_file", "build/usa/arm9.lcf").replace("$out", RAW)
cmd = cmd.replace(" -o ", " -sym on -o ", 1)
os.makedirs(os.path.join(REPO, "build/usa/dbg/build"), exist_ok=True)  # the lcf writes build/*.bin beside -o
r = subprocess.run(cmd, shell=True, cwd=REPO, capture_output=True, text=True)
if r.returncode:
    sys.exit("link failed:\n" + "\n".join(l for l in (r.stdout + r.stderr).splitlines() if "warning" not in l)[-2000:])

data = bytearray(open(os.path.join(REPO, RAW), "rb").read())
with open(os.path.join(REPO, RAW), "rb") as fh:
    spans = [(s["sh_offset"], s["sh_offset"] + s["sh_size"]) for s in ELFFile(fh).iter_sections()
             if s.name.startswith(".debug")]
fixed = 0
for lo, hi in spans:
    i = data.find(b"Z:\\", lo, hi)
    while i != -1:
        end = data.index(b"\0", i)
        data[i:end] = b"/." + bytes(data[i + 2:end]).replace(b"\\", b"/")
        fixed += 1
        i = data.find(b"Z:\\", end, hi)

# A CU holding both .text and a .init static initializer gets low_pc/high_pc spanning everything between
# (LightingManager.cpp covers 0x2050454-0x20e5e2c), and gdb resolves every address in that span to it. End
# such a CU at the cluster of functions that starts at its low_pc; its .init initializer loses its lines.
trimmed = 0
with open(os.path.join(REPO, RAW), "rb") as fh:
    elf = ELFFile(fh)
    info_off = elf.get_section_by_name(".debug_info")["sh_offset"]
    for cu in elf.get_dwarf_info().iter_CUs():
        top = cu.get_top_DIE()
        subs = sorted((c.attributes["DW_AT_low_pc"].value, c.attributes["DW_AT_high_pc"].value)
                      for c in top.iter_children()
                      if c.tag == "DW_TAG_subprogram" and "DW_AT_low_pc" in c.attributes)
        end = subs[0][1] if subs else None
        for lo, hi in subs[1:]:
            if lo - end > 0x1000:
                break
            end = max(end, hi)
        hp = top.attributes.get("DW_AT_high_pc")
        if end and hp and hp.value > end:
            data[info_off + hp.offset:info_off + hp.offset + 4] = end.to_bytes(4, "little")
            trimmed += 1

    # MWCC leaves a pointer-to-member type's DW_AT_type as ref_addr 0, and gdb aborts reading any CU that
    # holds one ("Cannot find DIE at 0x0"). Point it at a base type instead; it only affects how gdb
    # prints those rare member-pointer types.
    base, zero = None, []
    for cu in elf.get_dwarf_info().iter_CUs():
        for die in cu.iter_DIEs():
            if base is None and die.tag == "DW_TAG_base_type":
                base = die.offset
            t = die.attributes.get("DW_AT_type")
            if die.tag == "DW_TAG_ptr_to_member_type" and t and t.form == "DW_FORM_ref_addr" and t.value == 0:
                zero.append(t.offset)
    for off in zero:
        data[info_off + off:info_off + off + 4] = base.to_bytes(4, "little")

    # mwldarm's ELF has no code sections, only segments, and its symbols point at empty region sections
    # (ARM9, OV031, ...), so gdb crashes setting any breakpoint. Write a plain ELF instead: one section per
    # region holding its linked image, the patched debug sections verbatim (their offsets stay valid), and
    # every symbol in the section of its region, $a/$t mapping symbols included (gdb tells ARM from Thumb by
    # them). Overlays share address ranges, so each overlay section gets its real VMA and a unique dummy LMA:
    # that makes gdb treat it as an overlay, and gdb_overlays.py maps whichever ones RAM holds.
    lcf = open(os.path.join(REPO, "build/usa/arm9.lcf"), encoding="utf-8").read()
    order = re.findall(r"^\s+([A-Z0-9]+) : ORIGIN", lcf, re.M)          # ARM9, ITCM, DTCM, OV000, ...
    vmas = [p["p_vaddr"] for p in elf.iter_segments() if p["p_type"] == "PT_LOAD"]
    bins = {"ARM9": "arm9.bin", "ITCM": "itcm.bin", "DTCM": "dtcm.bin"}
    regions = []
    for i, (region, vma) in enumerate(zip(order, vmas)):
        name = {"ARM9": ".text", "ITCM": ".itcm", "DTCM": ".dtcm"}.get(region, "." + region.lower())
        lma = vma if region in bins else 0x80000000 + i * 0x400000
        blob = open(os.path.join(REPO, "build/usa/dbg/build", bins.get(region, f"arm9_{region.lower()}.bin")), "rb").read()
        regions.append((name, vma, blob, lma, region))
    debug = [(s.name, bytes(data[s["sh_offset"]:s["sh_offset"] + s["sh_size"]]))
             for s in elf.iter_sections() if s.name.startswith(".debug")]
    secs = list(elf.iter_sections())
    index = {r[4]: i + 1 for i, r in enumerate(regions)}
    syms = []
    for s in elf.get_section_by_name(".symtab").iter_symbols():
        sh = s["st_shndx"]
        if not s.name or s["st_info"]["type"] in ("STT_SECTION", "STT_FILE") or not isinstance(sh, int):
            continue
        if secs[sh].name in index:
            syms.append((s["st_info"]["bind"] != "STB_LOCAL", s.name, s["st_value"], s["st_size"],
                         {"STT_FUNC": 2, "STT_OBJECT": 1}.get(s["st_info"]["type"], 0), index[secs[sh].name]))
    syms.sort(key=lambda x: x[0])  # locals before globals
    with open(os.path.join(HERE, "overlays.json"), "w") as fh:  # what gdb_overlays.py compares RAM against
        json.dump([{"section": n, "vma": v, "size": len(b), "bin": os.path.join(REPO, "build/usa/dbg/build",
                    f"arm9_{r.lower()}.bin")} for n, v, b, l, r in regions if r not in bins], fh, indent=1)


def write_elf(path, regions, debug, syms, entry):
    import struct
    shstr, strtab = bytearray(b"\0"), bytearray(b"\0")
    def name(tab, s):
        off = len(tab); tab += s.encode() + b"\0"; return off
    body = bytearray()
    def put(blob, align=4):
        body.extend(b"\0" * (-(52 + len(body)) % align)); off = 52 + len(body); body.extend(blob); return off
    shdrs = [struct.pack("<10I", *[0] * 10)]
    phdrs = []
    for n, addr, blob, lma, _ in regions:
        off = put(blob)
        shdrs.append(struct.pack("<10I", name(shstr, n), 1, 0x6, addr, off, len(blob), 0, 0, 4, 0))
        phdrs.append(struct.pack("<8I", 1, off, addr, lma, len(blob), len(blob), 7, 4))
    for n, blob in debug:
        shdrs.append(struct.pack("<10I", name(shstr, n), 1, 0, 0, put(blob, 1), len(blob), 0, 0, 1, 0))
    sym = bytearray(b"\0" * 16)
    for glob, n, val, size, typ, shndx in syms:
        sym += struct.pack("<IIIBBH", name(strtab, n), val, size, ((1 if glob else 0) << 4) | typ, 0, shndx)
    first_global = 1 + sum(1 for s in syms if not s[0])
    symtab_idx = len(shdrs)
    shdrs.append(struct.pack("<10I", name(shstr, ".symtab"), 2, 0, 0, put(bytes(sym)), len(sym),
                             symtab_idx + 1, first_global, 4, 16))
    shdrs.append(struct.pack("<10I", name(shstr, ".strtab"), 3, 0, 0, put(bytes(strtab), 1), len(strtab), 0, 0, 1, 0))
    shstr_idx = len(shdrs)
    shdrs.append(struct.pack("<10I", name(shstr, ".shstrtab"), 3, 0, 0, put(bytes(shstr), 1), len(shstr), 0, 0, 1, 0))
    phoff = put(b"".join(phdrs))
    shoff = put(b"".join(shdrs))
    ident = b"\x7fELF\x01\x01\x01" + b"\0" * 9
    hdr = ident + struct.pack("<HHIIIIIHHHHHH", 2, 40, 1, entry, phoff, shoff, 0x05000000, 52, 32,
                              len(phdrs), 40, len(shdrs), shstr_idx)
    open(path, "wb").write(hdr + body)


write_elf(OUT, regions, debug, syms, 0x02000800)
print(f"wrote {OUT}: {fixed:,} paths rewritten, {trimmed} CU ranges trimmed, "
      f"{len(zero)} null member-pointer types retargeted, {len(syms):,} symbols, {len(regions) - 3} overlay sections")
