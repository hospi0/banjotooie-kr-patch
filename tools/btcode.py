"""Banjo-Tooie (USA) code: core1/core2 + overlays (ported from Mr-Wiseguy/banjo-tooie tools/rom_decompressor.cpp).

core1/core2 = 4 rarezip streams (text, data each) at fixed ROM offsets.
Overlay table @0x1E899B0: BE32 offsets relative to the table; overlay i (1-based) = [t[i-1], t[i]).
Overlay = 0x10 header {u16 text/16, rodata/16, data/16, bss/16, n_entry, n_reloc, u32 flags (byte +0xE = name_len)}
          + (if flags & 0x80) u16 decompressed_size/16 + raw deflate, else raw.
Contents: +0x28 entrypoints (BE32 x n_entry), name (padded to 4), relocs (BE16 x n_reloc, XORed with
          rom[0x40 + 4*idx] & 0xFFFF), then code aligned to 16 (VRAM base for code = 0 + overlay load address).
Anti-tamper: header words +0 and +8 are XORed with bk_crc(decompressed contents).
"""
import struct, zlib, sys, os

from btrom import load_rom

CORE1 = (0x1E29B60, 0x1E3F718, 0x1E42550)   # text start, data start, end
CORE2 = (0x1E42550, 0x1E86C76, 0x1E899B0)
CORE1_VRAM = 0x80012030                     # per decomp baserom.us.yaml (core1 text)
OVL_TABLE = 0x1E899B0


def bk_crc(b, c1=0, c2=0):
    for x in b:
        c1 = (c1 + x) & 0xFFFFFFFF
        c2 = (c2 ^ (x << (c1 & 0x17))) & 0xFFFFFFFF
    return c1, c2


def inflate_at(rom, p, n):
    size = struct.unpack_from('>H', rom, p)[0] * 16
    o = zlib.decompressobj(-15)
    r = o.decompress(rom[p + 2:p + n])
    assert o.eof, hex(p)
    return r, size


def core(rom, seg):
    t, d, e = seg
    text, _ = inflate_at(rom, t, d - t)
    data, _ = inflate_at(rom, d, e - d)
    return text, data


def overlays(rom):
    """-> list of dict(idx, name, rom, hdr(bytes, un-XORed), body(decompressed contents), code_off, sizes...)"""
    tsize = struct.unpack_from('>I', rom, OVL_TABLE)[0]
    n = tsize // 4 - 1
    t = [struct.unpack_from('>I', rom, OVL_TABLE + 4 * i)[0] for i in range(n + 1)]
    out = []
    for idx in range(1, n + 1):
        a, b = t[idx - 1], t[idx]
        if a == b:
            out.append(None); continue
        p = OVL_TABLE + a
        hdr = bytearray(rom[p:p + 0x10])
        flags = struct.unpack_from('>I', hdr, 0xC)[0]   # u32; name_len = byte +0xE
        if flags & 0x80:
            dsize = struct.unpack_from('>H', rom, p + 0x10)[0] * 16
            o = zlib.decompressobj(-15)
            body = o.decompress(rom[p + 0x12:OVL_TABLE + b])
            assert o.eof
            c1, c2 = bk_crc(body)
            struct.pack_into('>I', hdr, 0, struct.unpack_from('>I', hdr, 0)[0] ^ c1)
            struct.pack_into('>I', hdr, 8, struct.unpack_from('>I', hdr, 8)[0] ^ c2)
        else:
            body = rom[p + 0x10:OVL_TABLE + b]
        text, rod, dat, bss, nent, nrel = struct.unpack_from('>6H', hdr)
        nlen = hdr[0xE]
        name = body[0x28 + 4 * nent:0x28 + 4 * nent + nlen].split(b'\0')[0].decode('ascii', 'replace')
        rel0 = 0x28 + 4 * nent + ((nlen + 3) & ~3)
        code = (rel0 + 2 * nrel + 15) & ~15
        out.append(dict(idx=idx, name=name, rom=p, rom_end=OVL_TABLE + b, compressed=bool(flags & 0x80),
                        hdr=bytes(hdr), body=body, code_off=code, text=text * 16, rodata=rod * 16,
                        data=dat * 16, bss=bss * 16, nent=nent, nrel=nrel,
                        entries=[struct.unpack_from('>I', body, 0x28 + 4 * i)[0] for i in range(nent)],
                        reloc_xor=struct.unpack_from('>I', rom, 0x40 + 4 * idx)[0] & 0xFFFF, rel_off=rel0))
    return out


if __name__ == '__main__':
    rom = load_rom()
    outdir = sys.argv[1] if len(sys.argv) > 1 else 'work/bt/code'
    os.makedirs(outdir, exist_ok=True)
    for nm, seg in (('core1', CORE1), ('core2', CORE2)):
        tx, dt = core(rom, seg)
        open(f'{outdir}/{nm}_text.bin', 'wb').write(tx)
        open(f'{outdir}/{nm}_data.bin', 'wb').write(dt)
        print(nm, hex(len(tx)), hex(len(dt)))
    ov = overlays(rom)
    with open(f'{outdir}/overlays.tsv', 'w', encoding='utf-8') as f:
        f.write('idx\tname\trom\tsize\tcompressed\ttext\trodata\tdata\tbss\tcode_off\n')
        for o in ov:
            if not o: continue
            f.write(f"{o['idx']}\t{o['name']}\t{o['rom']:X}\t{o['rom_end']-o['rom']:X}\t{int(o['compressed'])}\t"
                    f"{o['text']:X}\t{o['rodata']:X}\t{o['data']:X}\t{o['bss']:X}\t{o['code_off']:X}\n")
            open(f"{outdir}/{o['idx']:03d}_{o['name']}.bin", 'wb').write(o['body'])
    print(sum(1 for o in ov if o), 'overlays')
