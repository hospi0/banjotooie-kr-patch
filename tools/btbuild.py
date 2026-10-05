"""Banjo-Tooie (USA) Korean builder — PoC 1 (dialogue font).

usage: python tools/btbuild.py <tsv folder> <out.z64>

Design (docs/00 «반조-투이 코드 조사»):
  * Korean = 2-byte code, lead 0x88..0x97 x trail 0x98..0xFC (0x7F..0x87 are button icons).
  * blob (hook code + frame tables + IA8 glyphs) DMA'd to expansion RAM 0x80400000 at boot
    by a stub written over 0x800D34A0 (bold-font charmap init, called once from 0x800A7C68);
    the original init body is moved into the blob.
  * hooks: getGlyphId 0x800D35D0 (lead -> -1 and remember, trail -> 0x1000+g / 0x2000+g),
    sprite frame 0x800B0D6C (id >= 0x1000 -> scratch frame with offset relative to the real sprite),
    glyphWidth 0x800D36C4 (lead -> advance, trail -> 0; zoombox line wrap is pixel based).
  * assets: whole data region rebuilt at ROM 0x2000000 (table stays at 0x5180, entries rewritten),
    data base constant at 0x800D5D8C..94.
  * core2 text re-deflated in its original slot (must not grow). CRC-checked functions are untouched.
"""
import os, sys, struct, zlib, glob, csv

sys.path.insert(0, os.path.dirname(__file__))
import btrom, btcode, bdf, n64crc, btrules
from mips import Asm, hi, lo

# --- code addresses (core2) ---------------------------------------------------
CORE2_VRAM = 0x800815C0
INIT_FN = 0x800D34A0            # bold charmap init (0x84 bytes, to 0x800D3524), called once at boot
INIT_END = 0x800D3524
DMA = 0x80012F78                # rom_copy(ram, rom, size)
GET_GLYPH = 0x800D35D0          # getGlyphId(font, c)
GLYPH_W = 0x800D36C4            # glyphWidth(font, c)
FRAME = 0x800B0D6C              # sprite frame(sprite, idx) = sprite + 0xC + 8*idx
ASSET_BASE = 0x800D5D8C         # lui t6,0 / addiu t6,t6,0x5180 / ori at,zero,0xD9A4 (data base)
TABLE_PTR = 0x8011B900          # core2 .data word = ROM address of the table entries (0x5188)
CORE2_DATA_VRAM = 0x80117C60

# --- Korean code space --------------------------------------------------------
LEAD0, NLEAD = 0x88, 16
TRAIL0, NTRAIL = 0x98, 101      # 0x98..0xFC
KR_RAM = 0x80400000
KR_CODE = KR_RAM + 0x40

# dialogue font 0xC21: 14 px high, caps on rows 2..11 (baseline row 11)
G0_W, G0_H, G0_ADV = 16, 14, 13
FONT_PATH = r'C:\claude\utils\font\Galmuri-v2.40.3\Galmuri11-Bold.bdf'
# bold font 0xC22: 23 px high, IA8 white + dark drop shadow; caps rows 1..19.
# Hangul = Galmuri14 at 1x + 1 px horizontal thickening (하스피: 원본 크기로 겹치면 지저분 — 작아도 읽히게)
G1_W, G1_H, G1_ADV = 24, 23, 19      # 16 -> 19 (하스피 «글자끼리 좀 더 벌려줘»)
BOLD_FONT_PATH = r'C:\claude\utils\font\Galmuri-v2.40.3\Galmuri14.bdf'

NEW_ASSET_BASE = 0x2000000
ROM_SIZE = 0x4000000
PUNCT = ',.!?:;)]}\'"~'


# --- translations ---------------------------------------------------------------
def read_tsv(paths):
    """folders and/or .tsv files -> {위치: (구분, 원문, 번역)} (rows with an empty 번역 are skipped)"""
    files = []
    for p in paths:
        files += sorted(glob.glob(os.path.join(p, '*.tsv'))) if os.path.isdir(p) else [p]
    rows = {}
    for p in files:
        with open(p, encoding='utf-8-sig', newline='') as f:
            for r in csv.DictReader(f, delimiter='	', quoting=csv.QUOTE_NONE):
                if (r.get('번역') or '').strip():
                    rows[r['위치']] = (r['구분'], r['원문'], r['번역'])
    return rows, files


def to_src_bytes(s):
    """TSV token text ({XX} = raw byte) -> bytes (ASCII only)."""
    out = bytearray(); i = 0
    while i < len(s):
        if s[i] == '{' and s[i + 3:i + 4] == '}':
            out.append(int(s[i + 1:i + 3], 16)); i += 4
        else:
            out.append(ord(s[i])); i += 1
    return bytes(out)


def encode(t, cmap):
    out = bytearray(); i = 0
    while i < len(t):
        ch = t[i]
        if ch == '{' and t[i + 3:i + 4] == '}':
            out.append(int(t[i + 1:i + 3], 16)); i += 4; continue
        if ord(ch) < 0x80:
            out.append(ord(ch))
        else:
            g = cmap[ch]
            out += bytes((LEAD0 + g // NTRAIL, TRAIL0 + g % NTRAIL))
        i += 1
    return bytes(out)


def font0_advances(rom, tab):
    r = btrom.asset(rom, tab, 0xC21)
    return {chr(0x21 + i): struct.unpack_from('>BBBBI', r, 0xC + 8 * i)[2] for i in range(88)}


def glyph_checker():
    f0, f1 = bdf.BdfFont(FONT_PATH), bdf.BdfFont(BOLD_FONT_PATH)
    def ok(c):
        o = ord(c)
        if o < 0x80:
            return 0x20 <= o <= 0x5F           # dialogue font: space, digits, capitals, punctuation
        return 0xAC00 <= o <= 0xD7A3 and o in f0.glyphs and o in f1.glyphs
    return ok


# --- dialogue asset (de)serialise -------------------------------------------------
def build_dialog(nlang, secs, tail):
    out = bytearray((nlang,)) + struct.pack('<H', 1 + 2 * nlang)
    assert nlang == 1
    for sec in secs:
        out.append(len(sec))
        for cmd, spk, raw in sec:
            assert len(raw) < 256
            out += bytes((3, spk, len(raw))) if cmd == 3 else bytes((cmd, len(raw)))
            out += raw
    return bytes(out) + tail


def inflate_used(rom, p):
    """rarezip stream at p -> (raw, bytes consumed incl. 2-byte header) — what the game's loader advances by."""
    o = zlib.decompressobj(-15)
    r = o.decompress(bytes(rom[p + 2:p + 2 + 0x100000]))
    assert o.eof
    return r, 2 + 0x100000 - len(o.unused_data) if len(rom) - p - 2 >= 0x100000 else None


def deflate_best(raw):
    """raw deflate via zopfli (zlib container minus 2-byte header and adler32)."""
    import zopfli.zopfli
    return zopfli.zopfli.compress(raw, numiterations=15)[2:-4]


def rarezip(raw):
    c = zlib.compressobj(9, zlib.DEFLATED, -15, 9)
    z = struct.pack('>H', (len(raw) + 15) // 16) + c.compress(raw) + c.flush()
    return z + bytes(-len(z) % 4)


# --- glyphs -------------------------------------------------------------------------
def render_dialog_glyphs(chars):
    f = bdf.BdfFont(FONT_PATH)
    out = []
    for ch in chars:
        g = f.glyphs[ord(ch)]
        w, h, xo, yo = g.bbx
        px = bytearray(G0_W * G0_H)
        top = 12 - (h + yo)                 # Galmuri baseline -> row 12 (Hangul descends to row ~12)
        for y, row in enumerate(g.bitmap()):
            for x, v in enumerate(row):
                X, Y = x + xo, y + top
                if v and 0 <= X < G0_W and 0 <= Y < G0_H:
                    px[Y * G0_W + X] = 0xFF
        out.append(bytes(px))
    return out


def render_bold_glyphs(chars):
    """bold font 0xC22 look: IA8 white + 1 px dark drop shadow (I=0, A=F) right/down.
    Galmuri14 at 1x, thickened 1 px to the right, rows ~4..17 (centred on the caps)."""
    f = bdf.BdfFont(BOLD_FONT_PATH)
    out = []
    for ch in chars:
        g = f.glyphs[ord(ch)]
        w, h, xo, yo = g.bbx
        top = 18 - (h + yo)
        ink = set()
        for y, row in enumerate(g.bitmap()):
            for x, v in enumerate(row):
                if v:
                    ink.add((x + xo, y + top))
                    ink.add((x + xo + 1, y + top))
        px = bytearray(G1_W * G1_H)
        for (X, Y) in ink:
            for dx, dy in ((1, 1), (1, 0), (0, 1)):
                xx, yy = X + dx, Y + dy
                if 0 <= xx < G1_W and 0 <= yy < G1_H and (xx, yy) not in ink:
                    px[yy * G1_W + xx] = 0x0F
        for (X, Y) in ink:
            if 0 <= X < G1_W and 0 <= Y < G1_H:
                px[Y * G1_W + X] = 0xFF
        out.append(bytes(px))
    return out


# --- hook code ----------------------------------------------------------------------
# state @KR_RAM: +0 lead byte, +4 pending KR id (system 2 stores glyph ids in a byte), +8 ring index,
#                +0x10..0x2F scratch frames
HOOK_ASM = """
KR_GID:                         # getGlyphId(a0 font, a1 c)
    sltiu at, a1, LEAD0
    bnez at, GID_ORIG
    nop
    sltiu at, a1, TRAIL0
    beqz at, GID_TRAIL
    lui t0, 0x8040
    sb a1, 0(t0)                # remember lead, draw nothing
    jr ra
    li v0, -1
GID_TRAIL:
    sltiu at, a1, 0xFD
    beqz at, GID_ORIG
    nop
    lbu t1, 0(t0)
    beqz t1, GID_ORIG
    nop
    sb zero, 0(t0)
    addiu t1, t1, -LEAD0
    sll t2, t1, 6               # g = lead*101 + trail
    sll t3, t1, 5
    addu t2, t2, t3
    sll t3, t1, 2
    addu t2, t2, t3
    addu t2, t2, t1
    addiu t3, a1, -TRAIL0
    addu t2, t2, t3
    bnez a0, GID_NOT0
    nop
    ori v0, t2, 0x1000
    jr ra
    sw v0, 4(t0)                # pending id
GID_NOT0:
    li t3, 1
    bne a0, t3, GID_NONE
    nop
    ori v0, t2, 0x2000
    jr ra
    sw v0, 4(t0)
GID_NONE:
    jr ra
    li v0, -1
GID_ORIG:
    li v0, 2                    # original first two instructions
    bne a0, v0, GID_O2
    nop
    j 0x800D35F8
    nop
GID_O2:
    j 0x800D35DC
    nop

KR_FRAME:                       # frame(a0 sprite, a1 idx)
    sltiu at, a1, 0x1000
    beqz at, FR_KR
    nop
    sltiu at, a1, 0x100         # byte id from system 2? (0x800B8148 stores the id with sb)
    beqz at, FR_PLAIN
    lui t8, 0x8040
    lw t7, 4(t8)
    beqz t7, FR_PLAIN
    andi t9, t7, 0xFF
    bne t9, a1, FR_PLAIN
    lui t9, 0x8012
    lw t6, -0x4A9C(t9)          # font 0 sprite (0x8011B564)
    beq t6, a0, FR_PEND
    nop
    lw t6, -0x4A94(t9)          # font 1 sprite (0x8011B56C)
    bne t6, a0, FR_PLAIN
    nop
FR_PEND:
    move a1, t7
    b FR_KR
    nop
FR_PLAIN:
    sll t6, a1, 3
    addu v0, a0, t6
    jr ra
    addiu v0, v0, 0xC
FR_KR:
    lui t8, 0x8040
    sw zero, 4(t8)              # pending consumed
    andi t6, a1, 0xFFF
    sll t6, t6, 3
    srl t7, a1, 12
    li t9, 1
    bne t7, t9, FR_T1
    nop
    lui t7, %hi(TAB0)
    b FR_T
    addiu t7, t7, %lo(TAB0)
FR_T1:
    lui t7, %hi(TAB1)
    addiu t7, t7, %lo(TAB1)
FR_T:
    addu t6, t6, t7             # source frame (tw th adv h, abs data)
    lw t9, 8(t8)
    addiu t9, t9, 8
    andi t9, t9, 0x18
    sw t9, 8(t8)
    addu v0, t8, t9
    addiu v0, v0, 0x10          # scratch slot (4-entry ring)
    lw t7, 0(t6)
    sw t7, 0(v0)
    lw t7, 4(t6)
    lw t9, 8(a0)                # sprite data offset
    addu t9, t9, a0
    subu t7, t7, t9
    jr ra
    sw t7, 4(v0)

KR_GW:                          # glyphWidth(a0 font, a1 c)
    sltiu at, a1, LEAD0
    bnez at, GW_ORIG
    nop
    sltiu at, a1, TRAIL0
    bnez at, GW_LEAD
    nop
    sltiu at, a1, 0xFD
    bnez at, GW_TRAIL
    nop
GW_ORIG:
    addiu sp, sp, -0x20
    j 0x800D36CC
    sw ra, 0x14(sp)
GW_LEAD:                        # font 0: lead carries the width (zoombox wrap) / font 1: 4 (cancels fxkern -4)
    bnez a0, GW_LEAD1
    nop
    jr ra
    li v0, G0_ADV
GW_LEAD1:
    li t0, 1
    bne a0, t0, GW_ZERO
    nop
    jr ra
    li v0, 4
GW_TRAIL:
    li t0, 1
    bne a0, t0, GW_ZERO
    nop
    jr ra
    li v0, G1_ADV
GW_ZERO:
    jr ra
    move v0, zero

KR_S2DRAW:                      # wraps jal 0x800B81CC in the system-2 string loop (0x800B8E28, string ptr = s2)
    sltiu at, a3, LEAD0
    bnez at, S2_PLAIN
    nop
    sltiu at, a3, TRAIL0
    beqz at, S2_PLAIN
    nop
    lbu t0, 1(s2)               # trail
    beqz t0, S2_NONE
    nop
    lui t1, 0x8040
    sb a3, 0(t1)                # lead for getGlyphId
    move a3, t0
    addiu s2, s2, 1             # caller adds one more -> both bytes consumed, one advance
S2_PLAIN:
    j 0x800B81CC
    nop
S2_NONE:
    jr ra
    move v0, zero

KR_FXDRAW:                      # fxkern (overlay 724) draws its string BACKWARDS (s1 = &str[i], i--):
    sltiu at, a3, TRAIL0        # a trail is drawn before its lead -> take the lead from str[i-1]
    bnez at, FX_PLAIN
    nop
    sltiu at, a3, 0xFD
    beqz at, FX_PLAIN
    nop
    lbu t0, -1(s1)
    sltiu at, t0, LEAD0
    bnez at, FX_PLAIN
    nop
    sltiu at, t0, TRAIL0
    beqz at, FX_PLAIN
    nop
    lui t1, 0x8040
    sb t0, 0(t1)
FX_PLAIN:
    j 0x800B8DEC
    nop
"""


def hook_asm(_=None):
    t = HOOK_ASM
    for k, v in (('LEAD0', LEAD0), ('TRAIL0', TRAIL0), ('G0_ADV', G0_ADV), ('G1_ADV', G1_ADV)):
        t = t.replace(k, str(v))
    return t.splitlines()


def jmp(a, target):
    return Asm(a).assemble([f'j {target:#x}', 'nop'])


def asm_syms(**extra):
    d = {'LEAD0': LEAD0, 'TRAIL0': TRAIL0, 'G0_ADV': G0_ADV, 'G1_ADV': G1_ADV}
    d.update(extra)
    return d


def build_blob(chars, orig_init, blob_rom):
    """-> (blob bytes, code syms). Layout at KR_RAM: [0x00 state][0x40 code][orig init][TAB0][TAB1][glyphs]."""
    g0 = render_dialog_glyphs(chars)
    g1 = render_bold_glyphs(chars)
    size = len(Asm(KR_CODE, asm_syms(TAB0=0, TAB1=0)).assemble(hook_asm()))   # size independent of tables
    init_at = KR_CODE + size
    tab0 = (init_at + len(orig_init) + 15) & ~15
    tab1 = tab0 + 8 * len(chars)
    a = Asm(KR_CODE, asm_syms(TAB0=tab0, TAB1=tab1))
    code = a.assemble(hook_asm())
    assert len(code) == size
    syms = a.syms
    syms['ORIG_INIT'] = init_at
    gdata = (tab1 + 8 * len(chars) + 15) & ~15
    t0 = t1 = pix = b''
    for px in g0:
        t0 += struct.pack('>BBBBI', G0_W, G0_H, G0_ADV, G0_H, gdata + len(pix))
        pix += px + bytes(-len(px) % 8)
    for px in g1:
        t1 += struct.pack('>BBBBI', G1_W, G1_H, G1_ADV, G1_H, gdata + len(pix))
        pix += px + bytes(-len(px) % 8)
    blob = bytearray(tab0 - KR_RAM)
    blob[0x40:0x40 + len(code)] = code
    blob[init_at - KR_RAM:init_at - KR_RAM + len(orig_init)] = orig_init
    blob += t0 + t1
    blob += bytes(gdata - KR_RAM - len(blob))
    blob += pix
    blob += bytes(-len(blob) % 16)
    return bytes(blob), syms


S2_DRAW_CALL = 0x800B8EE8       # jal 0x800B81CC inside the system-2 string loop


def core2_patches(syms, blob_rom, blob_size, data_base):
    p = {}
    stub = Asm(INIT_FN).assemble([
        'addiu sp, sp, -0x18', 'sw ra, 0x14(sp)',
        'lui a0, 0x8040',
        f'lui a1, {hi(blob_rom)}', f'addiu a1, a1, {lo(blob_rom)}',
        f'lui a2, {hi(blob_size)}',
        f'jal {DMA:#x}', f'addiu a2, a2, {lo(blob_size)}',
        f'jal {syms["ORIG_INIT"]:#x}', 'nop',
        'lw ra, 0x14(sp)', 'jr ra', 'addiu sp, sp, 0x18'])
    assert INIT_FN + len(stub) <= INIT_END
    p[INIT_FN] = stub
    p[GET_GLYPH] = jmp(GET_GLYPH, syms['KR_GID'])
    p[FRAME] = jmp(FRAME, syms['KR_FRAME'])
    p[GLYPH_W] = jmp(GLYPH_W, syms['KR_GW'])
    p[S2_DRAW_CALL] = Asm(S2_DRAW_CALL).assemble([f'jal {syms["KR_S2DRAW"]:#x}'])
    p[ASSET_BASE] = Asm(ASSET_BASE).assemble([
        f'lui t6, {hi(data_base)}', f'addiu t6, t6, {lo(data_base)}', 'ori at, zero, 0'])
    return p


# CRC-checked RAM ranges (core1 crc_entries) — patches must stay out
CRC_RANGES = [(0x8001E840, 0x2D0), (0x80081E00, 0x628), (0x800A1364, 0x5FC), (0x800965D4, 0x1C8),
              (0x8001C1C0, 0x130), (0x800CFA90, 0x1958), (0x800D1510, 0xB04)]


# strings inside overlays (the only on-screen ones found in code): (overlay, body offset, original, ko, slot bytes)
OVL_STRINGS = [
    (799, 0x1520, b'PLAYER %d', '플레이어 %d', 12),     # sumultiscore
    (846, 0x09C0, b'LOTS', '많음', 8),                  # sccustom
]


# code edits inside overlays: (overlay, body offset, original word, hook symbol) — absolute jal to core, not relocated
OVL_CODE = [
    (724, 0x348, 0x0C02E37B, 'KR_FXDRAW'),             # fxkern: jal 0x800B8DEC in its backwards draw loop
]


def patch_overlays(rom, cmap, syms):
    """Re-pack overlays in their own ROM slots: header words +0/+8 carry XOR bk_crc(decompressed body)."""
    ovs = btcode.overlays(rom)
    edits = {}
    for idx, off, src, ko, slot in OVL_STRINGS:
        edits.setdefault(idx, []).append(('str', off, src, ko, slot))
    for idx, off, word, sym in OVL_CODE:
        edits.setdefault(idx, []).append(('code', off, word, sym, None))
    for idx, lst in edits.items():
        o = ovs[idx - 1]
        assert o['idx'] == idx and o['compressed']
        body = bytearray(o['body'])
        rel = {(struct.unpack_from('>H', body, o['rel_off'] + 2 * i)[0] ^ o['reloc_xor']) & ~3
               for i in range(o['nrel'])}
        for kind, off, a, b_, slot in lst:
            if kind == 'code':
                assert struct.unpack_from('>I', body, off)[0] == a, (idx, hex(off))
                assert off - o['code_off'] not in rel, (idx, hex(off))
                struct.pack_into('>I', body, off, (3 << 26) | ((syms[b_] >> 2) & 0x3FFFFFF))
                continue
            src, ko = a, b_
            assert body[off:off + len(src) + 1] == src + b'\0', (idx, hex(off))
            assert not any(body[off + len(src):off + slot]), (idx, hex(off))
            b = encode(ko, cmap) + b'\0'
            assert len(b) <= slot, (ko, len(b), slot)
            body[off:off + slot] = b + bytes(slot - len(b))
        c1, c2 = btcode.bk_crc(body)
        hdr = bytearray(o['hdr'])
        struct.pack_into('>I', hdr, 0, struct.unpack_from('>I', hdr, 0)[0] ^ c1)
        struct.pack_into('>I', hdr, 8, struct.unpack_from('>I', hdr, 8)[0] ^ c2)
        p, end = o['rom'], o['rom_end']
        blob = bytes(hdr) + bytes(rom[p + 0x10:p + 0x12]) + deflate_best(bytes(body))
        assert len(blob) <= end - p, (idx, len(blob), end - p)
        rom[p:end] = blob + bytes(end - p - len(blob))
        chk = btcode.overlays(rom)[idx - 1]
        assert chk['body'] == bytes(body) and chk['hdr'] == o['hdr']
        print(f'overlay {idx} {o["name"]}: {len(lst)} strings, {len(blob)}/{end - p} B')


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    *paths, out = sys.argv[1:]
    print(btrules.BANNER)
    rom = bytearray(btrom.load_rom())
    tab = btrom.asset_table(rom)
    tr, files = read_tsv(paths)
    print(f'번역 파일 {len(files)}개, 번역된 행 {len(tr)}')

    # 1. validate every row first (rules are enforced on read; any error -> no build)
    adv = font0_advances(rom, tab)
    glyph_ok = glyph_checker()
    by_asset, errors, nwarn = {}, [], 0
    for loc, (kind, src, ko) in tr.items():
        pages, err, warn = btrules.validate(src, ko, kind, adv, glyph_ok)
        for e in err:
            errors.append(f'{loc}	{e}	{ko}')
        nwarn += len(warn)
        a, s_, i = loc.split(':')
        by_asset.setdefault(int(a, 16), []).append((int(s_), int(i), src, pages))
    chars = sorted({ch for v in by_asset.values() for *_, pages in v for pg in pages for ch in pg if ord(ch) >= 0x80}
                   | {ch for *_, ko, _ in OVL_STRINGS for ch in ko if ord(ch) >= 0x80})
    if len(chars) > NLEAD * NTRAIL:
        errors.append(f'한글 {len(chars)}자 > {NLEAD * NTRAIL}자')
    cmap = {ch: i for i, ch in enumerate(chars)}

    replaced = {}
    for a, rows in sorted(by_asset.items()):
        if not 0 <= a < len(tab) - 1:
            errors.append(f'{a:04X}	에셋 번호 범위 밖'); continue
        raw = btrom.asset(rom, tab, a)
        nlang, secs, end = btrom.parse_dialog(raw)
        assert build_dialog(nlang, secs, raw[end:]) == raw, hex(a)     # round trip
        rep = {}
        for s_, i, src, pages in rows:
            if s_ >= len(secs) or i >= len(secs[s_]):
                errors.append(f'{a:04X}:{s_}:{i}	원문에 없는 위치'); continue
            cmd, spk, old = secs[s_][i]
            if old != to_src_bytes(src) + b'\0':
                errors.append(f'{a:04X}:{s_}:{i}	원문 칸이 롬과 다름(엑셀이 고쳤나?)	{src}'); continue
            rep[(s_, i)] = [(cmd, spk, encode(pg, cmap) + b'\0') for pg in pages]
        new = []
        for s_, sec in enumerate(secs):
            out_sec = []
            for i, ent in enumerate(sec):
                out_sec += rep.get((s_, i), [ent])
            if len(out_sec) > 255:
                errors.append(f'{a:04X}:{s_}	쪽 나눔으로 항목 255개 초과')
            new.append(out_sec)
        if not errors:
            replaced[a] = rarezip(build_dialog(nlang, new, raw[end:]))
    if errors:
        print(f'\n★규칙 위반 {len(errors)}건 — 빌드하지 않음')
        for e in errors[:200]:
            print('  ' + e)
        open('work/bt_errors.tsv', 'w', encoding='utf-8').write('위치\t문제\t번역\n' + '\n'.join(errors) + '\n')
        print('  전체 목록: work/bt_errors.tsv')
        sys.exit(1)
    print(f'에셋 {len(replaced)}개 교체, 한글 {len(chars)}자, 경고 {nwarn}건')

    # 2. asset table + data at NEW_ASSET_BASE. ★ROM 0x1000..0x101000 stays original so the header CRC
    #    (and the emulator's game database match -> EEPROM 16K) is unchanged (PoC 2nd: «NO CONTROLLER»).
    n = struct.unpack_from('>I', rom, btrom.TABLE)[0]
    ents = [struct.unpack_from('>I', rom, btrom.TABLE + 8 + 4 * k)[0] for k in range(n)]
    data = bytearray()
    new_ents = []
    for k in range(n):
        new_ents.append(((len(data) // 4) << 8) | (ents[k] & 0xFF))
        if k + 1 < n:
            p, size, _ = tab[k]
            data += replaced.get(k, rom[p:p + size])
            data += bytes(-len(data) % 4)
    assert len(data) // 4 < (1 << 24)
    region = struct.pack('>II', n, 0xFFFFFFFF) + b''.join(struct.pack('>I', e) for e in new_ents)
    new_table = NEW_ASSET_BASE + 8                 # what *(0x8011B900) points at (orig 0x5188)
    data_base = NEW_ASSET_BASE + len(region)       # orig 0x12B24 = 0x5188 + 4n
    region += data
    rom += bytes(ROM_SIZE - len(rom))
    rom[NEW_ASSET_BASE:NEW_ASSET_BASE + len(region)] = region
    blob_rom = (NEW_ASSET_BASE + len(region) + 0xFFFF) & ~0xFFFF

    # 3. blob
    t0, t1, _ = btcode.CORE2
    text, _ = btcode.inflate_at(rom, t0, t1 - t0)
    text = bytearray(text)
    oi = INIT_FN - CORE2_VRAM
    blob, syms = build_blob(chars, bytes(text[oi:INIT_END - CORE2_VRAM]), blob_rom)
    assert blob_rom + len(blob) <= ROM_SIZE
    rom[blob_rom:blob_rom + len(blob)] = blob
    print(f'glyphs {len(chars)}  blob {len(blob)} B @ROM {blob_rom:#x}  asset region {len(data):#x} @ {NEW_ASSET_BASE:#x}')

    # 4. core2 text patches, re-deflate in place
    for a, b in core2_patches(syms, blob_rom, len(blob), data_base).items():
        for r0, rn in CRC_RANGES:
            assert not (a < r0 + rn and r0 < a + len(b)), hex(a)
        text[a - CORE2_VRAM:a - CORE2_VRAM + len(b)] = b
    z = struct.pack('>H', len(text) // 16) + deflate_best(bytes(text))   # zlib -9 is ~800 B over the slot
    assert len(text) % 16 == 0
    # ★the boot loader inflates .data right where the .text stream ENDS (compressed pointer carries on,
    #  core1/1E319F0.c) -> the data stream must follow the new text stream immediately.
    _, _, t2 = btcode.CORE2
    dat, _ = btcode.inflate_at(rom, t1, t2 - t1)
    dat = bytearray(dat)
    assert struct.unpack_from('>I', dat, TABLE_PTR - CORE2_DATA_VRAM)[0] == btrom.TABLE + 8
    struct.pack_into('>I', dat, TABLE_PTR - CORE2_DATA_VRAM, new_table)
    assert len(dat) % 16 == 0
    dstream = struct.pack('>H', len(dat) // 16) + deflate_best(bytes(dat))
    slot = t2 - t0
    print(f'core2 text {len(z)} + data {len(dstream)} / slot {slot}')
    assert len(z) + len(dstream) <= slot
    rom[t0:t2] = z + dstream + bytes(slot - len(z) - len(dstream))
    chk, used = inflate_used(rom, t0)
    assert chk == bytes(text)
    dchk, _ = inflate_used(rom, t0 + used)
    assert dchk == bytes(dat)

    # 4b. strings inside overlays
    patch_overlays(rom, cmap, syms)

    # 5. header CRC: untouched area -> must still match the original header
    orig = btrom.load_rom()
    assert rom[:0x101000] == orig[:0x101000]
    assert n64crc.calc(rom, 6105) == struct.unpack_from('>II', orig, 0x10)
    open(out, 'wb').write(rom)
    import hashlib
    print(out, hashlib.md5(rom).hexdigest())


if __name__ == '__main__':
    main()
