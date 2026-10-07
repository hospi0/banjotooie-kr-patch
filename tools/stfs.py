# -*- coding: utf-8 -*-
r"""엑스박스 360 STFS(LIVE) 패키지 읽기 + 다시 쌓기 (2026-10-07) — 읽기 전용형(볼륨 구분 바이트 1 = 해시표 한 벌)만
  읽기는 utils/한글화 이식/cod/port/stfs.py 와 같은 규약(Free60·Velocity).
  다시 쌓기 rebuild(원본, {경로: 새 바이트}) — 머리(0..첫 해시표)는 원본 그대로 두고:
    파일표 블록 0 → 파일들을 원래 시작 블록 차례로 빈틈없이(연속) · 0단 해시 항목 = SHA1(블록) + 0x80 + 다음 블록(int24 BE, 끝 FFFFFF)
    1단 항목 = SHA1(0단 표) + 0 · 1단 표 +0xFF0 = 할당 블록 수(u32 BE) · 최상위 해시(볼륨 서술자 +8) = SHA1(1단 표, 블록 0xAA 개 이하면 0단 표)
    볼륨 서술자 파일표 블록 수·시작 · 할당 블록 수(+0x1C) · 내용 크기 0x34C · 머리 해시 0x32C = SHA1([0x344, 첫 해시표))
  ⚠서명(0x4)은 그대로라 맞지 않는다 → Xenia 전용(실기 X).
  검산: 원본 파일을 그대로 넣어 다시 쌓으면 원본과 바이트까지 같다(python tools/stfs.py <패키지> --selftest).
  python tools/stfs.py <패키지>            # 목록"""
import hashlib, struct, sys

B = 0x1000
L0N = 0xAA                      # 0단 표 하나가 덮는 블록 수
L1N = 0x70E4                    # 1단 표 하나가 덮는 블록 수
L2N = L1N * L0N                 # 2단 표 하나가 덮는 블록 수


class STFS:
    def __init__(self, path):
        self.path = path
        self.f = open(path, 'rb')
        h = self.f.read(0x1000 * 16)
        self.magic = h[:4]
        hs = struct.unpack_from('>I', h, 0x340)[0]
        self.first = (hs + 0xFFF) & ~0xFFF
        self.head = h[:self.first] if self.first <= len(h) else None
        if self.head is None:
            self.f.seek(0); self.head = self.f.read(self.first)
        vd = 0x379
        self.sep = h[vd + 2]
        assert self.sep == 1, '해시표 두 벌(읽고 쓰기형) 패키지는 안 다룸'
        self.ft_count = struct.unpack_from('<H', h, vd + 3)[0]
        self.ft_block = h[vd + 5] | (h[vd + 6] << 8) | (h[vd + 7] << 16)
        self.entries = self._filetable()

    def offset(self, b):
        return (backing(b) << 12) + self.first

    def next_block(self, b):
        self.f.seek(self.first + (table_at(b, 0) << 12) + (b % L0N) * 0x18)
        e = self.f.read(0x18)
        return (e[0x15] << 16) | (e[0x16] << 8) | e[0x17]

    def read_blocks(self, start, count, contiguous, size):
        out = bytearray(); b = start
        for _ in range(count):
            self.f.seek(self.offset(b)); out += self.f.read(B)
            if len(out) >= size:
                break
            b = b + 1 if contiguous else self.next_block(b)
        return bytes(out[:size])

    def _filetable(self):
        raw = self.read_blocks(self.ft_block, self.ft_count, False, self.ft_count * B)
        ents = []
        for i in range(0, len(raw), 0x40):
            e = raw[i:i + 0x40]; fl = e[0x28]; ln = fl & 0x3F
            if ln == 0:
                continue
            ents.append(dict(raw=e, name=e[:ln].decode('latin1'), dir=bool(fl & 0x80), cont=bool(fl & 0x40),
                             blocks=int.from_bytes(e[0x29:0x2C], 'little'), start=int.from_bytes(e[0x2F:0x32], 'little'),
                             parent=struct.unpack_from('>h', e, 0x32)[0], size=struct.unpack_from('>I', e, 0x34)[0]))
        for e in ents:
            p, parts = e['parent'], [e['name']]
            while p != -1 and 0 <= p < len(ents):
                parts.append(ents[p]['name']); p = ents[p]['parent']
            e['path'] = '/'.join(reversed(parts))
        return ents

    def get(self, e):
        return self.read_blocks(e['start'], e['blocks'], e['cont'], e['size'])


def backing(b):
    """데이터 블록 b → 패키지 안 블록 자리(해시표 끼워 넣은 뒤) — Xenia BlockToOffsetSTFS(읽기 전용형)와 같음"""
    assert b < L2N, '3단(2단 표 하나)까지만'
    r = b + (b + L0N) // L0N
    if b < L0N:
        return r
    r += (b + L1N) // L1N
    return r if b < L1N else r + 1


def table_at(b, level):
    """데이터 블록 b 를 덮는 level 단 해시표 자리 — 1단·2단 표는 «첫 묶음 뒤»에 놓인다(0단 0번 뒤 1단 0번, 1단 0번 묶음 뒤 2단)"""
    if level == 0:
        if b < L0N:
            return 0
        blk = (b // L0N) * (L0N + 1) + (b // L1N) + 1
        return blk if b < L1N else blk + 1
    if level == 1:
        return L0N + 1 if b < L1N else 1 + (b // L1N) * (L1N + L1N // L0N + 1)
    return L1N + L1N // L0N + 1


def rebuild(src, files):
    """src: STFS · files: {경로: 새 바이트}(없는 경로는 원본 그대로) → 새 패키지 바이트"""
    ents = src.entries
    unknown = set(files) - {e['path'] for e in ents}
    assert not unknown, ('패키지에 없는 경로', sorted(unknown)[:5])
    order = sorted((i for i in range(len(ents)) if not ents[i]['dir']), key=lambda i: ents[i]['start'])   # 폴더 항목(블록 0)은 그대로
    ftn = (len(ents) * 0x40 + B - 1) // B
    data = {}; nxt = {}; b = ftn                                  # 데이터 블록 번호 → 바이트 · 다음 블록
    for k in range(ftn):
        nxt[k] = k + 1 if k + 1 < ftn else 0xFFFFFF
    new_ent = {}
    for i in order:
        e = ents[i]; body = files.get(e['path'])
        if body is None:
            body = src.get(e)
        n = max(1, (len(body) + B - 1) // B) if len(body) else 0
        new_ent[i] = (b, n, len(body))
        for j in range(n):
            data[b + j] = body[j * B:(j + 1) * B].ljust(B, b'\0')
            nxt[b + j] = b + j + 1 if j + 1 < n else 0xFFFFFF
        b += n
    total = b
    assert total < L2N, '블록 %d — 2단 표 하나를 넘음' % total
    ft = bytearray(ftn * B)
    for i, e in enumerate(ents):
        r = bytearray(e['raw'])
        if e['dir']:
            ft[i * 0x40:(i + 1) * 0x40] = r; continue
        st, n, size = new_ent[i]
        r[0x28] = (r[0x28] & 0x80) | 0x40 | (r[0x28] & 0x3F)       # 연속
        r[0x29:0x2C] = n.to_bytes(3, 'little'); r[0x2C:0x2F] = n.to_bytes(3, 'little')
        r[0x2F:0x32] = st.to_bytes(3, 'little'); struct.pack_into('>I', r, 0x34, size)
        ft[i * 0x40:(i + 1) * 0x40] = r
    for k in range(ftn):
        data[k] = bytes(ft[k * B:(k + 1) * B])
    levels = 1 if total <= L0N else 2 if total <= L1N else 3
    per = [L0N, L1N, L2N]
    counts = [(total + per[l] - 1) // per[l] for l in range(levels)]
    nhash = sum(counts)
    out = bytearray(src.first + (total + nhash) * B)
    for bb, blk in data.items():
        o = src.first + backing(bb) * B; out[o:o + B] = blk
    below = []                                                   # 바로 아래 단 표들(0단은 데이터 블록)
    for l in range(levels):
        tabs = []
        for k in range(counts[l]):
            t = bytearray(B)
            for j in range(L0N):
                if l == 0:
                    bb = k * L0N + j
                    if bb >= total:
                        break
                    t[j * 0x18:j * 0x18 + 0x14] = hashlib.sha1(data[bb]).digest()
                    t[j * 0x18 + 0x14] = 0x80; t[j * 0x18 + 0x15:j * 0x18 + 0x18] = nxt[bb].to_bytes(3, 'big')
                else:
                    c = k * L0N + j
                    if c >= len(below):
                        break
                    t[j * 0x18:j * 0x18 + 0x14] = hashlib.sha1(below[c]).digest()
            if l == levels - 1:
                struct.pack_into('>I', t, 0xFF0, total)            # 최상위 표 끝 = 할당 블록 수(원본 검산)
            o = src.first + table_at(k * per[l], l) * B; out[o:o + B] = t
            tabs.append(bytes(t))
        below = tabs
    assert len(below) == 1
    top = hashlib.sha1(below[0]).digest()
    h = bytearray(src.head)
    vd = 0x379
    struct.pack_into('<H', h, vd + 3, ftn); h[vd + 5:vd + 8] = (0).to_bytes(3, 'little')
    h[vd + 8:vd + 0x1C] = top
    struct.pack_into('>ii', h, vd + 0x1C, total, 0)
    struct.pack_into('>Q', h, 0x34C, (total + nhash) * B)
    h[0x32C:0x340] = hashlib.sha1(bytes(h[0x344:src.first])).digest()
    out[:src.first] = h
    return bytes(out)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    s = STFS(sys.argv[1])
    if '--selftest' in sys.argv:
        orig = open(sys.argv[1], 'rb').read(); new = rebuild(s, {})
        diff = next((i for i in range(min(len(orig), len(new))) if orig[i] != new[i]), None) if orig != new else None
        print('다시 쌓기 = 원본과 같음' if orig == new else '⛔다름: 길이 %d/%d · 첫 차이 %s' % (len(orig), len(new), hex(diff) if diff is not None else '-'))
    else:
        for e in s.entries:
            print('%-48s %10d  블록 %5d‥' % (e['path'], e['size'], e['start']))
