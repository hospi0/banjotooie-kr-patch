"""반조-투이 XBLA(360) 데이터 읽기/쓰기.

db360.bin (db360.cmp 를 lzx.xctd_decompress(first=0x100) 로 푼 것):
  [u32 에셋 수 n][u32 0xCDCDCDCD] + u32×n 색인 + 데이터
  색인 값 = (데이터 기준 바이트 오프셋 << 6) | 종류(6비트)   — 카주이는 8바이트 {오프셋, 플래그}
대사 에셋(종류 3): N64 와 같은 [언어 수][u16le 오프셋 × 언어] + 언어마다 구역 1~2개,
  구역 = [항목 수] + 항목. 항목은 N64 항목 앞에 «묶음 번호» 1바이트가 붙는다:
    [묶음][0x03][화자][길이][글]   (글 = NUL 포함)
    [묶음][명령][길이][자료]
  언어 = 영·일·프·독·이·스. 일본어 글 = AD 6A + 1바이트 글자 번호, 영어 한 줄을 여러 항목(같은 묶음 번호)으로 나눔.
"""
import os, struct

ROOT = os.path.join(os.path.dirname(__file__), '..')
X360 = os.path.join(ROOT, 'work', 'x360')
PKG = os.path.join(X360, 'pkg')
LANG_EN, LANG_JP = 0, 1


class DB:
    """엔진은 에셋 크기를 «다음 색인 항목 오프셋 - 자기 오프셋»으로 잰다(0x82265B38).
    색인 중간에 데이터 밖·엉뚱한 곳을 가리키는 쓰레기 항목이 섞여 있어(쓰이지 않는 번호) 다시 쓸 때는
    «원래 배치 그대로 + 바뀐 에셋만 갈아 끼우고, 그 끝 이후를 가리키는 오프셋을 길이 차만큼 민다»."""
    def __init__(self, path=None):
        d = open(path or os.path.join(X360, 'db360.bin'), 'rb').read()
        self.d = d
        self.n = struct.unpack_from('>I', d)[0]
        self.idx = list(struct.unpack_from('>%dI' % self.n, d, 8))
        self.base = 8 + 4 * self.n
        self.size = len(d) - self.base
        offs = [v >> 6 for v in self.idx] + [self.size]
        self.span = [(offs[i], offs[i + 1]) for i in range(self.n)]
        self.kind = [v & 0x3F for v in self.idx]
        self.new = {}

    def ok(self, i):
        a, b = self.span[i]
        return a <= b <= self.size

    def asset(self, i):
        if i in self.new:
            return self.new[i]
        a, b = self.span[i]
        if not self.ok(i):
            return b''
        return self.d[self.base + a:self.base + b]

    def put(self, i, data):
        assert self.ok(i) and self.span[i][1] > self.span[i][0], 'not a real asset'
        self.new[i] = bytes(data)

    def build(self):
        ch = sorted((self.span[i][0], self.span[i][1], i) for i in self.new)
        for (a1, b1, _), (a2, b2, _) in zip(ch, ch[1:]):
            assert b1 <= a2, 'overlapping changed assets'
        data = bytearray(); p = 0; marks = []
        acc = 0
        for a, b, i in ch:
            data += self.d[self.base + p:self.base + a]
            data += self.new[i]
            p = b
            acc += len(self.new[i]) - (b - a)
            marks.append((b, acc))                 # 오프셋 >= b 는 acc 만큼 민다
        data += self.d[self.base + p:]
        import bisect
        keys = [k for k, _ in marks]
        def f(o):
            if o > self.size:
                return o
            j = bisect.bisect_right(keys, o) - 1
            return o + (marks[j][1] if j >= 0 else 0)
        idx = [(f(v >> 6) << 6) | (v & 0x3F) for v in self.idx]
        return self.d[:8] + struct.pack('>%dI' % self.n, *idx) + bytes(data)


def parse_entries(b, o, end):
    cnt = b[o]; o += 1
    ent = []
    for _ in range(cnt):
        g, cmd = b[o], b[o + 1]
        if cmd == 3:
            spk, ln = b[o + 2], b[o + 3]
            ent.append((g, cmd, spk, b[o + 4:o + 4 + ln])); o += 4 + ln
        else:
            ln = b[o + 2]
            ent.append((g, cmd, None, b[o + 3:o + 3 + ln])); o += 3 + ln
        assert o <= end, 'entry past language end'
    return ent, o


def parse_dialog(b):
    """-> [언어별 [구역별 [(묶음, 명령, 화자|None, 자료)]]] (구역 1~2개), 꼬리(마지막 언어 뒤 남는 바이트)"""
    nl = b[0]
    offs = list(struct.unpack_from('<%dH' % nl, b, 1)) + [len(b)]
    langs = []
    tail = b''
    for k in range(nl):
        o, end = offs[k], offs[k + 1]
        secs = []
        while len(secs) < 2 and o < end:
            if secs and not any(b[o:end]):
                break
            e, o = parse_entries(b, o, end)
            secs.append(e)
        if k == nl - 1:
            tail = b[o:]
        else:
            assert not any(b[o:end]), 'gap inside language'
        langs.append((secs, b[o:end] if k < nl - 1 else b''))
    return langs, tail


def build_dialog(langs, tail):
    nl = len(langs)
    body = bytearray(); offs = []
    p = 1 + 2 * nl
    for secs, pad in langs:
        offs.append(p + len(body))
        for e in secs:
            assert len(e) < 256
            body.append(len(e))
            for g, cmd, spk, raw in e:
                assert len(raw) < 256
                if cmd == 3:
                    body += bytes([g, cmd, spk, len(raw)]) + raw
                else:
                    body += bytes([g, cmd, len(raw)]) + raw
        body += pad
    return bytes([nl]) + struct.pack('<%dH' % nl, *offs) + bytes(body) + tail


def is_dialog(kind, b):
    """종류 3·언어 6 이고 읽고 다시 쓴 결과가 같은 것만 (대사처럼 보이는 다른 자료 3개가 있다)"""
    if not (kind == 3 and len(b) > 13 and b[0] == 6):
        return False
    try:
        L, tail = parse_dialog(b)
    except Exception:
        return False
    return build_dialog(L, tail) == b


if __name__ == '__main__':
    db = DB()
    ok = 0
    for k in range(db.n):
        b = db.asset(k)
        if not is_dialog(db.kind[k], b):
            continue
        ok += 1
    print('dialog assets parsed + round trip', ok)
    assert db.build() == db.d
    k = next(k for k in range(db.n) if db.kind[k] == 3 and db.asset(k)[:1] == bytes([6]))
    db.put(k, db.asset(k) + bytes(5))
    tmp = os.path.join(X360, '_t.bin')
    open(tmp, 'wb').write(db.build())
    t, o = DB(tmp), DB()
    assert t.asset(k) == db.new[k] and t.asset(k + 1) == o.asset(k + 1) and t.asset(o.n - 2) == o.asset(o.n - 2)
    os.remove(tmp)
    print('db rebuild ok')
