"""Word-by-word MIPS disassembly of Banjo-Tooie code dumps (work/bt/code). usage: btdis.py core2 0x800d3400 0x800d3600"""
import capstone, struct, sys
md = capstone.Cs(capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS32 + capstone.CS_MODE_BIG_ENDIAN)
SEG = {'core1': ('work/bt/code/core1_text.bin', 'work/bt/code/core1_data.bin', 0x80012030),
       'core2': ('work/bt/code/core2_text.bin', 'work/bt/code/core2_data.bin', 0x800815C0)}


def image(seg):
    t, d, base = SEG[seg]
    return open(t, 'rb').read() + open(d, 'rb').read(), base


def dis(b, base, lo, hi):
    out = []
    for a in range(lo, hi, 4):
        w = b[a - base:a - base + 4]
        ins = next(md.disasm(w, a), None)
        out.append(f'{a:08x}: {w.hex()}  ' + (f'{ins.mnemonic} {ins.op_str}' if ins else '.word'))
    return '\n'.join(out)


if __name__ == '__main__':
    seg = sys.argv[1]
    if seg in SEG:
        b, base = image(seg)
    else:                       # overlay file, base = code offset 0
        b, base = open(seg, 'rb').read(), 0
    print(dis(b, base, int(sys.argv[2], 16), int(sys.argv[3], 16)))
