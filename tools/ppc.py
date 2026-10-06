"""작은 PowerPC 어셈블러 (360 xex 훅용). 조건 분기는 cr6 기준."""


def cmplwi(crf, ra, uimm):
    return (10 << 26) | (crf << 23) | (ra << 16) | (uimm & 0xFFFF)


def addi(rd, ra, simm):
    return (14 << 26) | (rd << 21) | (ra << 16) | (simm & 0xFFFF)


def stw(rs, d, ra):
    return (36 << 26) | (rs << 21) | (ra << 16) | (d & 0xFFFF)


def li(rd, simm):
    return addi(rd, 0, simm)


def cmpw(crf, ra, rb):
    return (31 << 26) | (crf << 23) | (ra << 16) | (rb << 11)


def lbzx(rd, ra, rb):
    return (31 << 26) | (rd << 21) | (ra << 16) | (rb << 11) | (87 << 1)


def b(pc, target):
    return (18 << 26) | ((target - pc) & 0x3FFFFFC)


_BC = {'blt': (12, 0), 'bgt': (12, 1), 'beq': (12, 2), 'bge': (4, 0), 'ble': (4, 1), 'bne': (4, 2)}


def bc(kind, pc, target, crf=6):
    bo, bit = _BC[kind]
    off = target - pc
    assert -0x8000 <= off < 0x8000
    return (16 << 26) | (bo << 21) | ((crf * 4 + bit) << 16) | (off & 0xFFFC)


def assemble(items, base):
    """items: 정수(완성 명령) / ('label', 이름) / (분기종류, 이름 또는 주소)."""
    labels, pc = {}, base
    for it in items:
        if isinstance(it, tuple) and it[0] == 'label':
            labels[it[1]] = pc
        else:
            pc += 4
    out, pc = [], base
    for it in items:
        if isinstance(it, tuple):
            if it[0] == 'label':
                continue
            tgt = labels[it[1]] if isinstance(it[1], str) else it[1]
            if it[0] == 'b':
                out.append(b(pc, tgt))
            elif it[0].endswith('0'):                    # 'bne0' 등 = cr0 기준
                out.append(bc(it[0][:-1], pc, tgt, crf=0))
            else:
                out.append(bc(it[0], pc, tgt))
        else:
            out.append(it)
        pc += 4
    return out
