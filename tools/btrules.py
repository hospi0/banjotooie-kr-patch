"""Banjo-Tooie translation rules — enforced when a translation is READ (the builder refuses to build on errors).

Engine facts (docs/00 «반조-투이 코드 조사»):
  * zoombox wraps by PIXEL width: glyphWidth summed per byte, cut back to the last SPACE when the line
    exceeds 192 px (216*scale - 24*scale, scale 1). No space in range -> the line cannot be cut.
  * font 0 (dialogue) widths: ASCII = frame advance of asset 0xC21, space 8, Hangul 13.
  * one entry = [len byte] -> <= 255 bytes incl. NUL. Hangul = 2 bytes.
  * {7F}..{87} are button icons, {0A} a line break, ~ a number/name the engine inserts.
"""
import re

LINE_PX = 192
HANGUL_PX = 13
SPACE_PX = 8
PUNCT = ',.!?:;)]}\'"'           # ~ is a placeholder, not punctuation
TOKEN = re.compile(r'\{[0-9A-F]{2}\}|~')
ICON = re.compile(r'\{(7F|8[0-7])\}')

BANNER = '''=== 반조-투이 번역 규칙 (적재기가 막음 — 하나라도 걸리면 빌드 안 함) ===
 1. 원문의 버튼 아이콘 {7F}~{87}·끼워 넣기 자리 ~ 는 개수 그대로 남길 것 ({0A} 줄바꿈은 줄 수를 바꿔도 됨)
 2. 문장부호 뒤 공백은 빌더가 지운다 → 대화창은 «공백»에서만 줄을 접으므로, 공백 없이 이어진 덩어리가
    한 줄(192px ≈ 한글 14자)을 넘으면 실패
 3. 한 항목 255바이트(한글 1자 = 2바이트, 끝 NUL 포함) — 대사는 넘으면 같은 화자 쪽으로 나눔, 목록형은 실패
 4. 쓸 수 있는 글자: 한글 완성형, 영문 대문자(소문자는 대문자로 바꿈), 숫자, 원본 글꼴 문장부호
 5. 한글은 전체 1,616자까지 (선행 0x88~0x97 × 후행 0x98~0xFC)
'''

AUTO_FIX = [('＿', ' '), ('…', '...'), ('‥', '..'), ('“', '"'), ('”', '"'), ('‘', "'"), ('’', "'"),
            ('～', '~'), ('　', ' ')]


def normalize(t, src=''):
    if not src.startswith(' '):
        t = t.lstrip()
    if not src.endswith(' '):            # "GAME ~: TIME " — the engine appends the time right after
        t = t.rstrip()
    for a, b in AUTO_FIX:
        t = t.replace(a, b)
    t = re.sub(r'[a-z]+', lambda m: m.group().upper(), t)      # dialogue font: capitals only
    return t if '  ' in src else re.sub(' {2,}', ' ', t)      # keep deliberate runs (intro " {0A}  {0A}…")


def squeeze(t):
    """no space after punctuation (전프로젝트 규칙) — but never touch leading/indent spaces before {0A}."""
    return re.sub('([' + re.escape(PUNCT) + '])[ ](?! )', r'\1', t)


def tokens(t):
    return TOKEN.findall(t)


def nbytes(t):
    t = re.sub(r'\{[0-9A-F]{2}\}', 'X', t)
    return sum(2 if ord(c) >= 0x80 else 1 for c in t) + 1


def px(t, adv):
    t = re.sub(r'\{[0-9A-F]{2}\}', '', t)
    return sum(SPACE_PX if c == ' ' else HANGUL_PX if ord(c) >= 0x80 else adv.get(c, 8) for c in t)


def wrap(t, adv):
    """zoombox wrap simulation on one paragraph -> lines, or ValueError."""
    lines = []
    for para in re.split(r'\{0A\}', t):
        words = para.split(' ')
        cur = ''
        for wd in words:
            if px(wd, adv) > LINE_PX:
                raise ValueError(f'공백 없는 덩어리가 한 줄({LINE_PX}px)을 넘음: {wd}')
            cand = wd if not cur else cur + ' ' + wd
            if px(cand, adv) > LINE_PX:
                lines.append(cur)
                cur = wd
            else:
                cur = cand
        lines.append(cur)
    return lines


def split_pages(t, limit=255):
    """over-long dialogue entry -> pages at a space (prefer after . ! ?, then the middle)."""
    if nbytes(t) <= limit:
        return [t]
    best = None
    for i, ch in enumerate(t):
        if ch != ' ':
            continue
        a, b = t[:i], t[i + 1:]
        if nbytes(a) > limit:
            break
        score = (0 if a[-1:] in '.!?' else 1, abs(nbytes(a) - nbytes(b)))
        if best is None or score < best[0]:
            best = (score, a, b)
    if best is None:
        raise ValueError(f'255바이트를 넘는데 나눌 공백이 없음: {t[:30]}')
    return [best[1]] + split_pages(best[2], limit)


def validate(src, kr, kind, adv, glyph_ok):
    """-> (text to insert, errors, warnings). kind = '대사' | '목록'."""
    err, warn = [], []
    k = squeeze(normalize(kr, src))
    if '\\n' in k or '\n' in k:
        err.append('실개행 금지 — 줄바꿈은 {0A}')
    si, ki = ICON.findall(src), ICON.findall(k)
    if sorted(si) != sorted(ki):
        err.append(f'버튼 아이콘 불일치 {si} -> {ki}')
    if src.count('~') != k.count('~'):
        err.append(f'~ 개수 불일치 {src.count("~")} -> {k.count("~")}')
    other = sorted(set(re.findall(r'\{([0-9A-F]{2})\}', k)) - {'0A', '7F'} - {f'8{i}' for i in range(8)})
    if other:
        err.append(f'알 수 없는 제어 코드 {other}')
    bad = sorted({c for c in TOKEN.sub('', k) if not glyph_ok(c)})
    if bad:
        err.append('글꼴에 없는 글자 ' + ''.join(bad))
    if src.count('{0A}') != k.count('{0A}'):
        warn.append(f'줄바꿈 {src.count("{0A}")} -> {k.count("{0A}")}')
    pages = [k]
    if nbytes(k) > 255:
        if kind == '대사':
            try:
                pages = split_pages(k)
                warn.append(f'{nbytes(k)}바이트 > 255 → 같은 화자 {len(pages)}쪽으로 나눔')
            except ValueError as e:
                err.append(str(e))
        else:
            err.append(f'{nbytes(k)}바이트 > 255 (목록형은 나눌 수 없음)')
    if kind == '대사':
        for pg in pages:
            try:
                wrap(pg, adv)
            except ValueError as e:
                err.append(str(e))
    if '~' in k:
        warn.append('~ 자리에 끼워질 글의 폭은 검사 못 함')
    return pages, err, warn
