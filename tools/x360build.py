"""반조-투이 XBLA(360) 한글 빌더 — 한글을 «일본어» 언어 칸에 넣는다 (Xenia, user_language = 일본어).

python tools/x360build.py <번역 폴더(work/text/fixed)> <출력 폴더> [--write]

구조 (work/x360 에 풀어 둔 것: db360.bin · textures.bin · default.pe — docs/00 «XBLA»)
  * 일본어 글 = AD 6A + 1바이트 글자 번호. 1번 글꼴은 일본어 모드에서 에셋 0x36CC(텍스처 146, 768×768 48px 칸)로
    바뀌고 822479E8 이 바이트를 그대로 글자 번호로 돌려준다.
  * 한글 = 선행 0xE0~0xE4 + 후행 → 글자 번호 = (선행-0xDF)*256 + 후행. 822479E8 의 «1번 글꼴·일본어» 출구를
    동굴로 돌려 선행이면 쪽을 기억하고 -1(폭 0·안 그림), 다음 바이트에 쪽을 더한다.
  * 글꼴 = 에셋 0x36CC 를 1536칸으로 늘리고 새 텍스처(마지막 번호, 2048×1536)를 가리키게:
    위 왼쪽 768×768 = 원래 일본어 그대로, 나머지 48px 칸 = 한글. 기록 = {칸폭, 24, 폭, 24, y/2, x/2}.
  * 일본어 칸은 영어 한 줄을 여러 항목(같은 묶음 번호 / 목록은 같은 명령)으로 나눠 둔다 → 같은 식으로 줄을 나눠 넣는다.
  * 버튼 {80}~{8F} = 일본어 글자 0x96~0xA5(일본어 칸이 쓰는 번호), ~ (숫자 자리) = 0xAE, 효과 FD xx = AD xx.
  * 일본어가 하나라도 남으면 선행 바이트와 겹쳐 깨진다(0xE0~ = 일본어 ら행) → 번역 없는 줄도 영어를 일본어 글꼴로 넣는다.
"""
import csv, glob, os, re, shutil, struct, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
import xex, ppc, btrules
import x360bt as X
from x360tex import Textures, tiled_offset

ROOT = os.path.join(os.path.dirname(__file__), '..')
X360 = X.X360
PKG = X.PKG
FONT = r'C:\Windows\Fonts\malgunbd.ttf'

FONT_ASSET = 0x36CC
LEAD0, NLEAD = 0xE0, 7
# 후행에서 빼는 것: 줄바꿈·공백·0xAC(메뉴 줄바꿈)·0xAD 탈출·0xAE 숫자 자리·0xFD~FF
#   0x95~0xA5 = 일본어 칸 버튼 아이콘(글자 찾기 전에 따로 그려 쪽이 안 지워짐 — 하스피 «비어»→«비Ⓨ월、») · 0xA0/A1 = 2번 글꼴 대체
#   0xE0~0xE4 = 선행(훅이 선행부터 보므로 후행과 겹치면 안 됨)
# 후행 = «그냥 바이트»(부호·숫자·영문 0x01~0x41 · 버튼 0x95~0xA5 · 0xAC~0xAE · 선행 0xE0~0xE6 · 0xFD~)와 겹치지 않는 범위만.
#   오프닝·지역 이름 글자 연출은 글자를 «끝에서 앞으로» 하나씩 그린다(N64 fxkern 과 같음) → 후행이 선행보다 먼저 와도
#   훅이 «대기»로 받아 두었다가 선행 때 그린다. 그냥 바이트가 후행 범위에 있으면 대기로 빠져 사라지므로 겹치면 안 된다.
#   0xA0·0xA1 = 2번 글꼴 대체 · 0x95~0xA5 = 아이콘(글자 찾기 전에 따로 그림 — 하스피 «비어»→«비Ⓨ월、»)
TRAILS = [t for t in list(range(0x42, 0x95)) + list(range(0xA6, 0xE0)) + list(range(0xE7, 0xFD))
          if t not in (0xAC, 0xAD, 0xAE)]
NGLYPH = 256 * (NLEAD + 1)
CELL = 48                          # 텍스처 칸(px) — 기록 좌표는 px/2
TEX_W, TEX_H = 2048, 1536
KR_W = 20                          # 한글 폭(기록 단위 = 40px)
SPACE_W = 8
PLACE, PLACE_W = 0xAE, 30
# 2번 글꼴(메뉴 — 에셋 0xC20, 언어와 상관없이 가나 256자, 텍스처 0번 512×512, 높이 16단위 = 32px).
# 822479E8 은 2번 글꼴의 0xA0·0xA1 을 출구 전에 다른 글자로 바꾼다 → 후행에서 뺌
FONT2_ASSET, FONT2_TEX = 0xC20, 0
CELL2, TEX2_W, TEX2_H = 32, 2048, 1024
KR_W2, SPACE_W2 = 15, 5
LINE_UNITS = 262                   # 일본어 원본 줄 폭: 최대 277 · 99% 264
ESC = 0xAD

# 일본어 글꼴(투이 = 카주이와 같은 배치)의 부호·영숫자 번호
JP = {'!': 0x34, '"': 0x35, "'": 0x37, '*': 0x38, '+': 0x39, ',': 0x3A, '-': 0x3B, '.': 0x3C, '/': 0x3D,
      ':': 0x3E, '=': 0x3F, '?': 0x40, '@': 0x41, '(': 0x03, ')': 0x04, '%': 0x06, '&': 0x0C,   # 0x0A = < (줄바꿈과 겹쳐 안 씀) · 0x0D = ～
      '>': 0x0B, '$': 0x02}
for i, c in enumerate('0123456789'):
    JP[c] = 0x10 + i
for i, c in enumerate('ABCDEFGHIJKLMNOPQRSTUVWXYZ'):
    JP[c] = 0x1A + i
JP['x'] = 0x95 + 23                # 크레딧 저작권 «x 2000» (일본어 글꼴 소문자 칸)


# ---------------------------------------------------------------- 글자 번호
def kr_code(k):
    lead, t = divmod(k, len(TRAILS))
    assert lead < NLEAD, '한글 글자가 너무 많음'
    return bytes([LEAD0 + lead, TRAILS[t]]), (lead + 1) * 256 + TRAILS[t]


TOKEN = re.compile(r'\{[0-9A-F]{2}\}|.')


def encode(t, cmap):
    """번역(정리 끝난 한 줄) → AD 6A + 바이트 + NUL"""
    out = bytearray(b'\xad\x6a')
    toks = TOKEN.findall(t)
    i = 0
    while i < len(toks):
        c = toks[i]; i += 1
        if len(c) > 1:
            v = int(c[1:3], 16)
            if v == 0xFD:                          # 효과 FD xx → AD xx (일본어 칸 탈출 문자)
                nxt = toks[i]; i += 1
                out += bytes([ESC, int(nxt[1:3], 16) if len(nxt) > 1 else ord(nxt)])
            elif 0x7F <= v <= 0x8F:
                out.append(v + 0x16)               # 버튼
            elif v == 0x0A:
                out.append(0x0A)
            elif v == 0x92:                        # ’ (메뉴 문자열 영어)
                out.append(JP["'"])
            else:
                raise ValueError('처리 못 하는 토큰 %s: %s' % (c, t))
        elif c == '~':
            out.append(PLACE)
        elif c == ' ':
            out += cmap[' '][0]
        elif c in cmap:
            out += cmap[c][0]
        elif c in JP:
            out.append(JP[c])
        elif c == '#':                             # 영어 이름표 띠 표시(일본어 칸은 안 씀)
            continue
        else:
            raise ValueError('글꼴에 없는 글자 %r: %s' % (c, t))
    return bytes(out) + b'\0'


jp_w = {}


def width(t):
    w = 0
    toks = TOKEN.findall(t)
    i = 0
    while i < len(toks):
        c = toks[i]; i += 1
        if len(c) > 1:
            v = int(c[1:3], 16)
            if v == 0xFD:
                i += 1
            elif 0x7F <= v <= 0x8F:
                w += jp_w[v + 0x16]
            elif v == 0x92:
                w += jp_w[JP["'"]]
            continue
        w += (SPACE_W if c == ' ' else PLACE_W if c == '~' else KR_W if ord(c) >= 0xAC00 else
              0 if c == '#' else jp_w[JP[c]])
    return w


def wrap(t, limit=LINE_UNITS):
    """{0A} 는 그대로 두고(일본어 칸도 0x0A 를 씀) 공백에서 나눔 → 줄 목록"""
    lines = []
    for seg in t.split('{0A}'):
        words = seg.split(' ')
        cur = ''
        out = []
        for w in words:
            cand = (cur + ' ' + w) if cur else w
            if width(cand) <= limit or not cur:
                if width(cand) > limit:
                    raise ValueError('공백 없는 구간이 한 줄을 넘음: ' + cand)
                cur = cand
            else:
                out.append(cur); cur = w
        out.append(cur)
        lines.append(out)
    # 0x0A 로 나뉜 조각은 한 항목 안에 두고, 폭으로 넘친 줄만 항목을 나눈다
    res = []
    for k, out in enumerate(lines):
        if k == 0:
            res += out
        else:
            res[-1] = res[-1] + '{0A}' + out[0]
            res += out[1:]
    return res


def en_text(raw):
    """영어 칸 바이트 → 번역 TSV 와 같은 표기({XX})"""
    return ''.join(chr(b) if 0x20 <= b < 0x7F else '{%02X}' % b for b in raw.rstrip(b'\0'))


def en_fallback(raw):
    """번역 없는 영어 줄 → 일본어 글꼴로 쓸 수 있는 꼴(소문자는 대문자로, 글꼴에 없는 부호는 뺌 — 크레딧 이름의 [ 등)"""
    t = re.sub('[a-z]+', lambda m: m.group().upper(), en_text(raw))
    return ''.join(c for c in TOKEN.findall(t) if len(c) > 1 or c in JP or c in ' ~#')


def is_text(cmd):
    return cmd == 3 or cmd >= 0x80


# ---------------------------------------------------------------- 번역
JOSA_V = re.compile(r'(\{(?:7F|8[0-9A-F])\})(으로|이나|을|과|은|이(?=[ ,.!?…]|$))')
JOSA_MAP = {'을': '를', '으로': '로', '과': '와', '은': '는', '이나': '나', '이': '가'}


def josa360(t):
    """N64 는 아이콘 뒤를 받침 조사(을·으로·과·이·은)로 맞췄다 — 360 버튼 이름은 모두 모음으로 끝나므로 를·로·와·가·는"""
    return JOSA_V.sub(lambda m: m.group(1) + JOSA_MAP[m.group(2)], t)


def read_rows(path):
    files = sorted(glob.glob(os.path.join(path, '*.tsv'))) if os.path.isdir(path) else [path]
    tr = {}
    for f in files:
        with open(f, encoding='utf-8-sig', newline='') as fh:
            for r in csv.DictReader(fh, delimiter='\t', quoting=csv.QUOTE_NONE):
                kr = (r.get('번역') or '').strip()
                if kr:
                    t = josa360(btrules.squeeze(btrules.normalize(kr, r['원문'])))
                    tr[r['위치']] = (r['구분'], r['원문'], t)
    return tr


X360_KR = os.path.join(ROOT, 'work', 'text', 'x360_kr.tsv')
# 크레딧(하스피 «크레딧은 번역하지마») — N64 크레딧이 밀린 구간 + 360 전용 크레딧: 영어 그대로
CREDITS = set(range(0x1B68, 0x1B9C)) | set(range(0x368C, 0x36CC))


def read_x360_kr():
    """360 에서 영어가 바뀐 줄·360 전용 줄: {(에셋, s, i): (360영어, 번역)}"""
    out = {}
    with open(X360_KR, encoding='utf-8-sig', newline='') as fh:
        for r in csv.DictReader(fh, delimiter='	', quoting=csv.QUOTE_NONE):
            a, s, i = r['360위치'].split(':')
            out[(int(a, 16), int(s), int(i))] = (r['360원문'], josa360(btrules.squeeze(btrules.normalize(r['번역'], r['360원문']))))
    return out


# ---------------------------------------------------------------- 목록 에셋 (메뉴·퀴즈 등): [6][0][u16le × 6] + [개수] + {명령, 길이, 글}
def is_list(kind, b):
    if not (kind == 3 and len(b) > 15 and b[0] == 6 and b[1] == 0):
        return False
    try:
        return build_list(parse_list(b)) == b
    except Exception:
        return False


def parse_list(b):
    nl = b[0]
    offs = list(struct.unpack_from('<%dH' % nl, b, 2)) + [len(b)]
    L = []
    for k in range(nl):
        o, end = offs[k], offs[k + 1]
        cnt = b[o]; o += 1
        e = []
        for _ in range(cnt):
            c, l = b[o], b[o + 1]
            e.append((c, b[o + 2:o + 2 + l])); o += 2 + l
        assert o <= end
        L.append((e, b[o:end]))
    return L


def build_list(L):
    nl = len(L)
    body = bytearray(); offs = []
    p = 2 + 2 * nl
    for e, pad in L:
        offs.append(p + len(body))
        assert len(e) < 256
        body.append(len(e))
        for c, t in e:
            assert len(t) < 256
            body += bytes([c, len(t)]) + t
        body += pad
    return bytes([nl, 0]) + struct.pack('<%dH' % nl, *offs) + bytes(body)


# ---------------------------------------------------------------- 글꼴 그림
def free_cells(tw=TEX_W, th=TEX_H, cell=CELL, jp=(768, 768)):
    cols, rows = tw // cell, th // cell
    return [(x * cell, y * cell) for y in range(rows) for x in range(cols)
            if not (x * cell < jp[0] and y * cell < jp[1])]


def render_atlas(jp_img, chars, tw=TEX_W, th=TEX_H, cell=CELL, kw=KR_W, sw=SPACE_W, size=40):
    """chars[0] = 공백(빈 칸). 위 왼쪽 = 원래 일본어 그림. 반환: 그림, {글자 번호: 기록 8바이트}"""
    img = Image.new('RGBA', (tw, th), (255, 255, 255, 0))
    img.paste(jp_img, (0, 0))
    font = ImageFont.truetype(FONT, size)
    cells = free_cells(tw, th, cell, jp_img.size)
    recs = {}
    for k, c in enumerate(chars):
        _, gid = kr_code(k)
        cx, cy = cells[k]
        w = sw if c == ' ' else kw
        if c != ' ':
            m = Image.new('L', (cell, cell), 0)
            dr = ImageDraw.Draw(m)
            bb = dr.textbbox((0, 0), c, font=font)
            gw, gh = bb[2] - bb[0], bb[3] - bb[1]
            dr.text(((kw * 2 - gw) // 2 - bb[0], (cell - gh) // 2 - bb[1]), c, font=font, fill=255)
            g = Image.new('RGBA', (cell, cell), (255, 255, 255, 0)); g.putalpha(m)
            img.paste(g, (cx, cy))
        recs[gid] = struct.pack('>BBBBHH', w, cell // 2, w, cell // 2, cy // 2, cx // 2)
    return img, recs


def tile_argb(img, pitch=None):
    a = np.array(img)
    h, w = a.shape[:2]
    pitch = pitch or w
    argb = a[..., [3, 0, 1, 2]].reshape(-1, 4)
    out = np.zeros((pitch * ((h + 31) & ~31), 4), np.uint8)
    ys, xs = np.mgrid[0:h, 0:w]
    idx = np.vectorize(lambda x, y: tiled_offset(x, y, pitch, 2))(xs, ys).reshape(-1)
    out[idx] = argb
    return out.tobytes()


def build_textures(T, atlas_img, src_tex):
    TEX_W, TEX_H = atlas_img.size
    """새 텍스처를 마지막 번호로 붙인다(적재기는 마지막 항목 끝까지 읽음). 머리는 src_tex 를 본떠 크기·피치만."""
    d, n = T.d, T.n
    H0 = T.hdr0()
    base = T.base()
    ent = [struct.unpack_from('>6I', d, 4 + i * 24) for i in range(n)]
    last_end = ent[-1][0] + ent[-1][3]
    assert base + last_end == len(d)
    off = (last_end + 0xFFF) & ~0xFFF
    pix = tile_argb(atlas_img)
    so = ent[src_tex]
    new_ent = struct.pack('>6I', off, TEX_W, TEX_H, len(pix), 0xFFFFFFFF, so[5])
    hdr = bytearray(d[H0 + src_tex * 0x34:H0 + (src_tex + 1) * 0x34])
    f = list(struct.unpack_from('>6I', hdr, 0x1C))
    f[0] = (f[0] & ~(0x1FF << 22)) | ((TEX_W // 32) << 22)
    f[2] = (TEX_W - 1) | ((TEX_H - 1) << 13)
    f[4] &= ~(0xF << 6)                                     # 밉 없음
    f[5] &= 0xFFF
    struct.pack_into('>6I', hdr, 0x1C, *f)
    body = d[base:base + last_end] + bytes(off - last_end)
    out = (struct.pack('>I', n + 1) + d[4:4 + n * 24] + new_ent + d[H0:base] + bytes(hdr) + body + pix)
    return out, n


# ---------------------------------------------------------------- xex
CAVE = 0x825F8000          # .text 끝(0x825F3934) 뒤 .data(0x82600000) 앞 빈 곳
PAGE_VAR = 0x826CCF80      # .XBMOVIE(0x826CCE00, 8 B 사용) 안 빈 칸 — 쓰기 가능 섹션
HOOK_AT = 0x82247A58       # 822479E8: 1·2번 글꼴(일본어 모드) 출구 «mr r3,r4 / blr»


def patch_xex(img):
    img = bytearray(img)
    def w32(va, v):
        struct.pack_into('>I', img, va - 0x82000000, v)
    def r32(va):
        return struct.unpack_from('>I', img, va - 0x82000000)[0]
    assert r32(HOOK_AT) == 0x7C832378 and r32(HOOK_AT + 4) == 0x4E800020, hex(r32(HOOK_AT))
    hi, lo = (PAGE_VAR + 0x8000) >> 16, PAGE_VAR & 0xFFFF
    lo_s = lo - 0x10000 if lo >= 0x8000 else lo
    def lis(rd, v): return (15 << 26) | (rd << 21) | (v & 0xFFFF)
    def lwz(rd, d_, ra): return (32 << 26) | (rd << 21) | (ra << 16) | (d_ & 0xFFFF)
    def stw(rs, d_, ra): return (36 << 26) | (rs << 21) | (ra << 16) | (d_ & 0xFFFF)
    def slwi8(ra, rs): return (21 << 26) | (rs << 21) | (ra << 16) | (8 << 11) | (0 << 6) | (23 << 1)   # rlwinm ra,rs,8,0,23
    def add(rd, ra, rb): return (31 << 26) | (rd << 21) | (ra << 16) | (rb << 11) | (266 << 1)
    MR_R3_R4, BLR = 0x7C832378, 0x4E800020
    code = [
        ppc.cmplwi(6, 3, 1), ('blt', 'plain'),           # 1번(대사·일본어 모드) · 2번(메뉴) 글꼴
        ppc.cmplwi(6, 3, 2), ('bgt', 'plain'),
        lis(12, hi),
        ppc.cmplwi(6, 4, LEAD0), ('blt', 'notlead'),
        ppc.cmplwi(6, 4, LEAD0 + NLEAD), ('bge', 'notlead'),
        ppc.addi(11, 4, -(LEAD0 - 1)),                     # 쪽 = 선행-0xDF (1..)
        lwz(10, lo_s + 4, 12),                             # 대기 후행(거꾸로 그리기)이 있으면 지금 그 글자
        ppc.cmplwi(6, 10, 0), ('beq', 'setpage'),
        ppc.li(9, 0), stw(9, lo_s + 4, 12), stw(9, lo_s, 12),
        slwi8(11, 11), add(3, 11, 10), BLR,
        ('label', 'setpage'),
        stw(11, lo_s, 12),                                 # 선행이면 남은 쪽과 상관없이 새로
        ppc.li(3, -1), BLR,
        ('label', 'notlead'),
        ppc.cmplwi(6, 4, 0x42), ('blt', 'raw'),            # 후행 범위인가
        ppc.cmplwi(6, 4, 0xFC), ('bgt', 'raw'),
        ppc.cmplwi(6, 4, 0x95), ('blt', 'trail'),
        ppc.cmplwi(6, 4, 0xA5), ('ble', 'raw'),
        ppc.cmplwi(6, 4, 0xAC), ('blt', 'trail'),
        ppc.cmplwi(6, 4, 0xAE), ('ble', 'raw'),
        ppc.cmplwi(6, 4, 0xE0), ('blt', 'trail'),
        ppc.cmplwi(6, 4, 0xE6), ('ble', 'raw'),
        ('label', 'trail'),
        lwz(11, lo_s, 12),
        ppc.cmplwi(6, 11, 0), ('bne', 'pair'),
        stw(4, lo_s + 4, 12),                              # 선행보다 먼저 온 후행 → 대기, 안 그림
        ppc.li(3, -1), BLR,
        ('label', 'pair'),
        ppc.li(10, 0), stw(10, lo_s, 12),
        slwi8(11, 11), add(3, 11, 4), BLR,                 # 번호 = 쪽*256 + 후행
        ('label', 'raw'),
        ppc.li(10, 0), stw(10, lo_s, 12), stw(10, lo_s + 4, 12),   # 그냥 바이트: 남은 쪽·대기 버림(«1인»→«객인» 방지)
        ('label', 'plain'),
        MR_R3_R4, BLR,
    ]
    words = ppc.assemble(code, CAVE)
    for i, w in enumerate(words):
        assert r32(CAVE + i * 4) == 0
        w32(CAVE + i * 4, w)
    assert r32(PAGE_VAR) == 0 and r32(PAGE_VAR + 4) == 0
    w32(HOOK_AT, ppc.b(HOOK_AT, CAVE))
    # 82235A28(두 번째 출력 계통 — 글자 하나 그리기)가 글자 번호를 8비트로 잘라 글리프 기록을 찾는다 → 32비트 그대로
    assert r32(0x82235A84) == 0x57EB063E and r32(0x82235A8C) == 0x5564063E   # clrlwi r11,r31,24 / clrlwi r4,r11,24
    w32(0x82235A84, 0x7FEBFB78)                            # mr r11,r31
    w32(0x82235A8C, 0x7D645B78)                            # mr r4,r11

    def lbz(rd, d_, ra): return (34 << 26) | (rd << 21) | (ra << 16) | (d_ & 0xFFFF)

    def kr_test(reg, yes_lead, yes_trail, no):
        """reg = 바이트 → 선행 / 후행(TRAILS) / 그 밖"""
        return [ppc.cmplwi(6, reg, LEAD0), ('blt', 'nl'), ppc.cmplwi(6, reg, LEAD0 + NLEAD - 1), ('ble', yes_lead),
                ('label', 'nl'),
                ppc.cmplwi(6, reg, 0x42), ('blt', no), ppc.cmplwi(6, reg, 0xFC), ('bgt', no),
                ppc.cmplwi(6, reg, 0x95), ('blt', yes_trail), ppc.cmplwi(6, reg, 0xA5), ('ble', no),
                ppc.cmplwi(6, reg, 0xAC), ('blt', yes_trail), ppc.cmplwi(6, reg, 0xAE), ('ble', no),
                ('b', yes_trail)]                                   # 0xAF~0xDF·0xE7~0xFC (선행은 위에서)
    # 82247B08(글자 폭 — 오프닝·지역 이름 연출의 글자 자리 fxkern): 훅 상태를 안 건드리고 바이트로 바로 —
    # 선행 4 · 후행 한글 폭(fxkern 이 바이트마다 −4 → 한 글자 = 한글 폭 − 4, 영문과 같은 규칙). 원래는 선행(−1)에 기본 폭
    # → 글자마다 빈칸 하나(하스피 «좀 넓다»)
    W_AT = 0x82247B08
    assert r32(W_AT) == 0x7D8802A6                          # mflr r12
    cw = CAVE + 0x100
    code = kr_test(4, 'lead', 'trail', 'orig') + [
        ('label', 'lead'), ppc.li(3, 4), BLR,
        ('label', 'trail'), ppc.cmplwi(6, 3, 2), ('beq', 'f2'), ppc.li(3, KR_W), BLR,
        ('label', 'f2'), ppc.li(3, KR_W2), BLR,
        ('label', 'orig'), 0x7D8802A6, ('b', W_AT + 4)]
    for i, w in enumerate(ppc.assemble(code, cw)):
        assert r32(cw + i * 4) == 0
        w32(cw + i * 4, w)
    w32(W_AT, ppc.b(W_AT, cw))
    # 82235E20(두 번째 계통 문자열 출력) 비례 폭: 글자 폭 0 이면 기본 폭(r25)을 더한다 → 한글 바이트면 0(선행·대기 후행)
    S_AT, S_RET = 0x82235F24, 0x82235F30
    assert r32(S_AT) == 0x7F23CB78                          # mr r3,r25
    cs = CAVE + 0x180
    code = [lbz(0, -1, 29)] + kr_test(0, 'zero', 'zero', 'dflt') + [
        ('label', 'zero'), ppc.li(3, 0), ('b', S_RET),
        ('label', 'dflt'), 0x7F23CB78, ('b', S_RET)]
    for i, w in enumerate(ppc.assemble(code, cs)):
        assert r32(cs + i * 4) == 0
        w32(cs + i * 4, w)
    w32(S_AT, ppc.b(S_AT, cs))
    return bytes(img)


# ---------------------------------------------------------------- 메뉴 문자열 (RAWFiles/X360_strings.dat)
STRINGS_DAT = os.path.join(PKG, 'RAWFiles', 'X360_strings.dat')
X360_UI = os.path.join(ROOT, 'work', 'text', 'x360_ui.tsv')
UI_LANG = 5                        # 영·프·독·이·스·일 — 6번째가 일본어 칸
UI_NL = 0xAC                       # 일본어 칸 줄바꿈 (대사 에셋엔 안 나옴 → 후행에서 뺌)
UI_CREDITS = range(1330, 1477)     # 엔딩 출연진·제작진(하스피 «크레딧은 번역하지마») — 영어 그대로


def parse_strings(d):
    """[u16 개수][u16 언어 수][u32 언어별 총 길이] + 언어마다 [u32 길이 × 개수] + 문자열들"""
    n, nl = struct.unpack_from('<HH', d, 0)
    p = 4 + 4 * nl
    lens = []
    for _ in range(nl):
        lens.append(struct.unpack_from('<%dI' % n, d, p)); p += 4 * n
    langs = []
    for L in range(nl):
        a = []
        for l in lens[L]:
            a.append(d[p:p + l]); p += l
        langs.append(a)
    return langs, d[p:]


def build_strings(langs, tail):
    n, nl = len(langs[0]), len(langs)
    out = bytearray(struct.pack('<HH', n, nl))
    out += struct.pack('<%dI' % nl, *(sum(len(s) for s in a) for a in langs))
    for a in langs:
        out += struct.pack('<%dI' % n, *(len(s) for s in a))
    for a in langs:
        for s in a:
            out += s
    return bytes(out) + tail


def ui_kind(j):
    """일본어 칸 원래 형식: FONT(AD 6A 게임 글꼴) / UTF16(시스템 메시지 상자, BE) / ASCII(영어 그대로 — 법적 고지·제작진)"""
    if j[:2] == b'\xad\x6a':
        return 'FONT'
    if j[:1] == b'\0' or any(c >= 0x80 for c in j):
        return 'UTF16'
    return 'ASCII'


def ui_en(raw, kind):
    if kind == 'UTF16':
        return raw.decode('utf-16-be').rstrip('\0').replace('\n', '\\n')
    return ''.join(chr(b) if 0x20 <= b < 0x7F else ('\\n' if b == 10 else '{%02X}' % b) for b in raw.rstrip(b'\0'))


def read_ui():
    """{번호: (영어, 번역)} — 같은 영어가 여러 번호면 «번호» 칸에 쉼표로"""
    out = {}
    with open(X360_UI, encoding='utf-8-sig', newline='') as fh:
        for r in csv.DictReader(fh, delimiter='\t', quoting=csv.QUOTE_NONE):
            kr = josa360(btrules.squeeze(btrules.normalize(r['번역'].replace('\\n', '{0A}'), r['원문'].replace('\\n', '{0A}'))))
            for i in r['번호'].split(','):
                out[int(i)] = (r['원문'], kr)
    return out


def jp_line_w(b):
    w, j = 0, 0
    while j < len(b):
        if b[j] == ESC:
            j += 2; continue
        w += jp_w.get(b[j], 0); j += 1
    return w


def wrap_ui(t, limit):
    out, cur = [], ''
    for w in t.split(' '):
        cand = (cur + ' ' + w) if cur else w
        if width(cand) <= limit or not cur:
            cur = cand
        else:
            out.append(cur); cur = w
    out.append(cur)
    return out


def ui_upper(t):
    """게임 글꼴에는 영어 대문자만 있다"""
    return re.sub('[a-z]+', lambda m: m.group().upper(), t)


def ui_texts(tr):
    """메뉴 문자열 번역: x360_ui.tsv + N64 같은 영어(대소문자 무시) → {번호: 번역}, {번호: 출처}"""
    langs, _ = parse_strings(open(STRINGS_DAT, 'rb').read())
    en, jp = langs[0], langs[UI_LANG]
    n64 = {}
    for loc, (_, e, k) in tr.items():
        if int(loc.split(':')[0], 16) not in CREDITS:
            n64.setdefault(e.upper().replace('{0A}', '\\n').strip(), k)
    ui = read_ui()
    out, src = {}, {}
    for i in range(len(en)):
        kind = ui_kind(jp[i])
        if kind == 'ASCII' or i in UI_CREDITS:
            continue
        e = ui_en(en[i], kind)
        if not e.strip():
            continue
        if i in ui:
            assert ui[i][0] == e, ('x360_ui 원문 다름', i, ui[i][0], e)
            out[i] = ui[i][1]; src[i] = 'x360_ui'
        elif e.upper().strip() in n64:
            out[i] = n64[e.upper().strip()]; src[i] = 'N64'
    return out, src


def apply_ui(texts, cmap, errors):
    """일본어 칸을 한글로. 게임 글꼴 문자열:
      * 영어 칸이 빈 번호가 뒤따르면(일본어는 한 줄씩 나눠 둔 대사형) 그 번호들을 줄 칸으로 — 일본어 줄 최대 폭으로
        나눠 채우고 남는 칸은 빈 문자열(영어 칸처럼)
      * 한 칸짜리는 \\n·폭 넘침을 0xAC 로 (일본어 원본의 최대 줄 폭 기준; 일본어도 영어도 한 줄이면 나누지 않음)
      * 번역 없는 칸(크레딧 등)은 영어를 일본어 글꼴로 — 일본어를 남기면 선행 바이트와 겹친다
    시스템 메시지(UTF16)는 UTF-16BE 그대로. 반환: (새 파일, 통계)"""
    langs, tail = parse_strings(open(STRINGS_DAT, 'rb').read())
    en, jp = langs[0], langs[UI_LANG]
    new = list(jp)
    st = {'번역': 0, '영어 그대로': 0, '시스템': 0}
    n = len(en)
    i = 0
    while i < n:
        kind = ui_kind(jp[i])
        if kind == 'ASCII':
            i += 1; continue
        if kind == 'UTF16':
            if i in texts:
                new[i] = texts[i].replace('{0A}', '\n').encode('utf-16-be') + b'\0\0'; st['시스템'] += 1
            i += 1; continue
        grp = [i]
        j = i + 1
        while j < n and ui_kind(jp[j]) == 'FONT' and not en[j].rstrip(b'\0'):
            grp.append(j); j += 1
        i = j
        head = grp[0]
        raw = en[head]
        if head in texts:
            t = ui_upper(texts[head]); st['번역'] += 1
        else:
            if raw.rstrip(b'\0'):
                st['영어 그대로'] += 1
            t = ui_upper(ui_en(raw, 'FONT'))
            t = ''.join(c for c in re.findall(r'\{[0-9A-F]{2}\}|\\n|.', t) if len(c) > 1 or c in JP or c in ' ~')
            t = t.replace('\\n', '{0A}')
        jl = [l for g in grp for l in jp[g][2:].rstrip(b'\0').split(bytes([UI_NL]))]
        jw = max([jp_line_w(l) for l in jl] + [0])
        paras = t.split('{0A}')
        e_up = ''.join(c for c in re.findall(r'\{[0-9A-F]{2}\}|\\n|.', ui_upper(ui_en(raw, 'FONT')))
                       if len(c) > 1 or c in JP or c in ' ~')
        ew = max(width(l) for l in e_up.split('\\n'))
        try:
            if len(grp) > 1:
                lines = [l for p in paras for l in wrap_ui(p, max(jw, LINE_UNITS))]   # 대사 상자 = 대사 에셋과 같은 폭
                if len(lines) > len(grp):
                    errors.append('메뉴 %d: %d줄 > 칸 %d «%s»' % (head, len(lines), len(grp), t))
                    lines = lines[:len(grp) - 1] + [' '.join(lines[len(grp) - 1:])]
                for k, g in enumerate(grp):
                    new[g] = encode(lines[k], cmap) if k < len(lines) else b'\0'
            else:
                multi = len(jl) > 1 or len(paras) > 1
                lines = [l for p in paras for l in (wrap_ui(p, max(jw, 120)) if multi else [p])]
                if not multi and width(t) > max(jw, ew) + 20:
                    errors.append('메뉴 %d: 폭 %d > 일본어 %d·영어 %d «%s»' % (head, width(t), jw, ew, t))
                body = bytes([UI_NL]).join(encode(l, cmap)[2:-1] for l in lines)
                new[head] = b'\xad\x6a' + body + b'\0'
        except (ValueError, KeyError) as e:
            errors.append('메뉴 %d: %s' % (head, e))
    langs[UI_LANG] = new
    # 원본 파일 뒤 117 KB 는 옛 일본어 조각 + 0 채움 → 파일 크기는 원본 그대로(읽기 버퍼가 고정일 수 있다), 남는 곳은 0
    total = len(open(STRINGS_DAT, 'rb').read())
    body = build_strings(langs, b'')
    assert len(body) <= total, ('메뉴 문자열이 원본 파일 크기를 넘음', len(body), total)
    st['크기'] = len(body)
    return body + bytes(total - len(body)), st


# xex 안 일본어는 불러오기 오류 시스템 창(UTF-16BE)뿐 — 제자리, 원문 길이 이내(남는 칸은 0)
XEX_MSGS = [('読み込みエラー', '불러오기 오류'),
            ('「バンジョーとカズーイの大冒険 2」を読み込めませんでした。続行できません', '「반조-투이」를 불러오지 못해 계속할 수 없습니다'),
            ('アーケードへ戻る', '아케이드로 복귀')]


def patch_xex_msgs(img):
    img = bytearray(img)
    for jp_s, kr in XEX_MSGS:
        a, b = jp_s.encode('utf-16-be'), kr.encode('utf-16-be')
        assert img.count(a + b'\0\0') == 1 and len(b) <= len(a), jp_s
        k = img.index(a + b'\0\0')
        img[k:k + len(a)] = b + bytes(len(a) - len(b))
    return bytes(img)


# ---------------------------------------------------------------- main
def main():
    src, out_dir = sys.argv[1], sys.argv[2]
    tr = read_rows(src)
    db = X.DB()
    fa = db.asset(FONT_ASSET)
    cnt, _, ch, cw, jp_tex = struct.unpack_from('>HHHHI', fa, 0)
    assert cnt == 256 and jp_tex == 146, (cnt, jp_tex)
    for g in range(256):
        jp_w[g] = fa[12 + 8 * g + 2]

    # 번역 → 에셋별
    by_asset = {}
    for loc, (kind, en, kr) in tr.items():
        a, s, i = loc.split(':')
        by_asset.setdefault(int(a, 16), {})[(int(s), int(i))] = (en, kr)
    dialogs = {k for k in range(db.n) if db.kind[k] == 3 and X.is_dialog(3, db.asset(k))}
    lists = {k for k in range(db.n) if db.kind[k] == 3 and is_list(3, db.asset(k))}
    print('360 대사 에셋 %d · 목록 에셋 %d' % (len(dialogs), len(lists)))

    uitx, uisrc = ui_texts(tr)
    chars = [' '] + sorted({c for k in [k for _, _, k in tr.values()] + [k for _, k in read_x360_kr().values()] +
                            list(uitx.values())
                            for c in k if 0xAC00 <= ord(c) <= 0xD7A3})
    cmap = {c: kr_code(k) for k, c in enumerate(chars)}

    errors, stat = [], {'번역': 0, '영어 그대로': 0, '자리 옮김': 0, '360 전용': 0, '같은 영어': 0}
    xkr = read_x360_kr()
    xhit = set()
    left = []
    import collections
    cnt = collections.defaultdict(collections.Counter)
    for loc, (kind, en, kr) in tr.items():
        if int(loc.split(':')[0], 16) not in CREDITS:
            cnt[en][kr] += 1
    by_en = {en: c.most_common(1)[0][0] for en, c in cnt.items()}
    def align(a, entries):
        """N64 위치(s,i) → 360 (s,i): 같은 번호에 같은 영어면 그대로, 아니면 같은 구역의 같은 영어(안 쓴 것 먼저).
        entries = 360 영어 칸 [구역][번호] 글(글이 아닌 항목은 None)"""
        rows = by_asset.get(a, {})
        m = {}
        for (s, i), (src_en, kr) in sorted(rows.items()):
            if s < len(entries) and i < len(entries[s]) and entries[s][i] == src_en:
                m[(s, i)] = (src_en, kr)
        done = {v for v in m}
        for (s, i), (src_en, kr) in sorted(rows.items()):
            if (s, i) in done and m[(s, i)][0] == src_en:
                continue
            cands = [(s, j) for j in range(len(entries[s]) if s < len(entries) else 0)
                     if entries[s][j] == src_en and (s, j) not in m]
            if cands:
                m[cands[0]] = (src_en, kr); stat['자리 옮김'] += 1
            elif a not in CREDITS and not any((a, s, j) in xkr for j in range(len(entries[s]) if s < len(entries) else 0)):
                errors.append('%04X:%d:%d 360 에 같은 영어 없음 — N64 «%s»' % (a, s, i, src_en))
        return m

    def lines_for(a, key, raw, m):
        en = en_text(raw)
        t = None if a in CREDITS else m.get(key)
        if a not in CREDITS and (a,) + key in xkr:
            x_en, x_kr = xkr[(a,) + key]
            if x_en != en:
                errors.append('%04X:%d:%d x360_kr 원문 다름 «%s» / 360 «%s»' % (a, key[0], key[1], x_en, en))
            t = (en, x_kr); stat['360 전용'] += 1; xhit.add((a,) + key)
        elif t is None and a not in CREDITS and en in by_en:
            t = (en, by_en[en]); stat['같은 영어'] += 1
        if t is not None:
            stat['번역'] += 1
            text = t[1]
        else:
            stat['영어 그대로'] += 1
            if a not in CREDITS:
                left.append('%04X:%d:%d	%s' % (a, key[0], key[1], en))
            text = en_fallback(raw)
        try:
            return [encode(l, cmap) for l in wrap(text)]
        except (ValueError, KeyError) as e:
            errors.append('%04X:%d:%d %s' % (a, key[0], key[1], e))
            return [encode('', cmap)]

    for a in sorted(dialogs):
        langs, tail = X.parse_dialog(db.asset(a))
        en_secs = langs[X.LANG_EN][0]
        m = align(a, [[en_text(raw) if is_text(cmd) else None for g, cmd, spk, raw in sec] for sec in en_secs])
        jp = []
        for s, sec in enumerate(en_secs):
            e = []
            for i, (g, cmd, spk, raw) in enumerate(sec):
                if is_text(cmd) and raw.rstrip(b'\0'):
                    e += [(g, cmd, spk, l) for l in lines_for(a, (s, i), raw, m)]
                else:
                    e.append((g, cmd, spk, raw))
            jp.append(e)
        langs[X.LANG_JP] = (jp, langs[X.LANG_JP][1])
        db.put(a, X.build_dialog(langs, tail))
    for a in sorted(lists):
        L = parse_list(db.asset(a))
        m = align(a, [[en_text(raw) if c >= 0x80 else None for c, raw in L[X.LANG_EN][0]]])
        # 일본어가 항목 안에서 0xAC 로 줄을 바꾸는 목록(지역 이름·게임 선택·파일 상태 25개)은 항목을 나누지 않는다
        # (나누면 첫 항목만 나옴 — 하스피 «게임을 에서 더 안나옴») → 줄 = 0xAC, 영어 {0A}(0x0A) 도 0xAC
        ac = any(UI_NL in r[2:] for _, r in L[X.LANG_JP][0] if r[:2] == b'\xad\x6a')
        e = []
        for i, (c, raw) in enumerate(L[X.LANG_EN][0]):
            if raw.rstrip(b'\0') and c >= 0x80:
                ls = lines_for(a, (0, i), raw, m)
                if ac:
                    e.append((c, b'\xad\x6a' + bytes([UI_NL]).join(l[2:-1] for l in ls).replace(b'\x0a', bytes([UI_NL])) + b'\0'))
                else:
                    e += [(c, l) for l in ls]
            else:
                e.append((c, raw))
        L[X.LANG_JP] = (e, L[X.LANG_JP][1])
        db.put(a, build_list(L))
    print('줄: 번역 %(번역)d (자리 옮김 %(자리 옮김)d · 360 전용 %(360 전용)d · 같은 영어 %(같은 영어)d) · 영어 그대로 %(영어 그대로)d' % stat)
    print('크레딧 밖 영어 그대로 %d줄' % len(left), left[:10])
    xmiss = sorted(set(xkr) - xhit)
    if xmiss:
        errors += ['%04X:%d:%d x360_kr 줄이 안 쓰임(360 에 그 자리 없음)' % k for k in xmiss]
    miss = sorted({a for a in by_asset if a not in dialogs and a not in lists})
    print('360 에 없는 번역 에셋 %d' % len(miss), ['%04X' % a for a in miss[:8]])

    strings_bin, ust = apply_ui(uitx, cmap, errors)
    print('메뉴 문자열: 게임 글꼴 번역 %d (N64 같은 영어 %d · x360_ui %d) · 영어 그대로 %d · 시스템 메시지 %d' % (
        ust['번역'], sum(v == 'N64' for v in uisrc.values()), sum(v == 'x360_ui' for v in uisrc.values()),
        ust['영어 그대로'], ust['시스템']) + ' · 본문 %d B' % ust['크기'])

    # 글꼴
    T = Textures(os.path.join(X360, 'textures.bin'))
    atlas, recs = render_atlas(T.image(jp_tex), chars)
    tex_bin, tex_id = build_textures(T, atlas, jp_tex)
    newfa = bytearray(struct.pack('>HHHHI', NGLYPH, 0, ch, cw, tex_id))
    for g in range(NGLYPH):
        newfa += fa[12 + 8 * g:20 + 8 * g] if g < 256 else recs.get(g, bytes(8))
    db.put(FONT_ASSET, bytes(newfa))
    # 2번 글꼴(메뉴): 같은 글자 번호에 32px 한글 — 텍스처를 하나 더 붙인다
    fb = db.asset(FONT2_ASSET)
    cnt2, _, ch2, cw2, t2 = struct.unpack_from('>HHHHI', fb, 0)
    assert cnt2 == 256 and t2 == FONT2_TEX, (cnt2, t2)
    atlas2, recs2 = render_atlas(T.image(FONT2_TEX), chars, TEX2_W, TEX2_H, CELL2, KR_W2, SPACE_W2, 27)
    T2 = Textures.__new__(Textures); T2.d = tex_bin; T2.n = struct.unpack('>I', tex_bin[:4])[0]
    tex_bin, tex2_id = build_textures(T2, atlas2, FONT2_TEX)
    newfb = bytearray(struct.pack('>HHHHI', NGLYPH, 0, ch2, cw2, tex2_id))
    for g in range(NGLYPH):
        newfb += fb[12 + 8 * g:20 + 8 * g] if g < 256 else recs2.get(g, bytes(8))
    db.put(FONT2_ASSET, bytes(newfb))
    atlas2.save(os.path.join(X360, 'kr_atlas2.png'))
    # 그림: 일본 로고 자리에 영문 로고 · 일본판 간판 43장 한글 · GAME OVER / THE END (tools/x360signs.py)
    import x360signs
    tex_bin, n_img = x360signs.patch(tex_bin, tile_argb)
    print('그림 %d장 (로고·간판·GAME OVER·THE END)' % n_img)
    dbb = db.build()

    img, base, _ = xex.load(os.path.join(PKG, 'default.xex'))
    img = patch_xex(img)
    img = patch_xex_msgs(img)
    atlas.save(os.path.join(X360, 'kr_atlas.png'))
    print('한글 %d자 · 텍스처 #%d %dx%d · db %d B · 텍스처 파일 %d B · 오류 %d' % (
        len(chars) - 1, tex_id, TEX_W, TEX_H, len(dbb), len(tex_bin), len(errors)))
    if errors:
        open(os.path.join(ROOT, 'work', 'x360_errors.txt'), 'w', encoding='utf-8').write('\n'.join(errors) + '\n')
        print('→ work/x360_errors.txt')
    if '--write' not in sys.argv:
        print('드라이런 — 출력 안 씀 (--write 로 기록)')
        return
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    shutil.copytree(PKG, out_dir)
    xex.write_plain(os.path.join(PKG, 'default.xex'), img, os.path.join(out_dir, 'default.xex'))
    open(os.path.join(out_dir, 'RAWFiles', 'db360.cmp'), 'wb').write(dbb)
    open(os.path.join(out_dir, 'RAWFiles', 'db360.textures.cmp'), 'wb').write(tex_bin)
    open(os.path.join(out_dir, 'RAWFiles', 'X360_strings.dat'), 'wb').write(strings_bin)
    print('출력', out_dir)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
