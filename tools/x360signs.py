"""반조-투이 XBLA: 일본판이 따로 그려 넣은 간판 그림(텍스처 104~144)을 한글로.

  python tools/x360signs.py            → work/x360/signs_preview.png (원본 | 한글 시안)

텍스처는 위아래가 뒤집혀 저장돼 있다(모델 UV) → 바로 세워 그린 뒤 다시 뒤집어 넣는다.
나뉜 간판(110+111 등)은 옆으로 이어 붙여 한 장으로 그린 뒤 잘라 나눈다.
글자 지우기 = 안쪽 상자에서 바탕색과 먼 화소(글자·그림자)를 표시 → 둘레 바탕으로 번지게 메움.
"""
import os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

sys.path.insert(0, os.path.dirname(__file__))
from x360tex import Textures

ROOT = os.path.join(os.path.dirname(__file__), '..')
X360 = os.path.join(ROOT, 'work', 'x360')
FONT = r'C:\claude\utils\font\logo\BlackHanSans.ttf'

# (텍스처 번호들(왼→오), 글(줄은 \n), 글자색, 테두리색, 안쪽 여백(px), 메울 상자 색 거리)
W, K, Y, O = (255, 255, 255), (20, 20, 20), (255, 230, 40), (255, 150, 40)
SIGNS = [
    ((104,), '쓰레기\n압축기', W, K, 22),
    ((105,), '업무용\n엘리베이터', W, K, 8),
    ((106,), '공조\n설비실', W, K, 8),
    ((107,), '일꾼\n숙소', W, K, 8),
    ((108,), '역\n그런티 산업', W, K, 8),
    ((109,), '폐기물\n처리장', W, K, 8),
    ((110, 111), '전자석실', W, K, 8),
    ((112, 113), '폐기물 처리 탱크', Y, K, 8),
    ((114, 115), '석유', (230, 20, 20), None, 10, {'max': 46}),
    ((116, 117), '물', (230, 20, 20), None, 10, {'max': 46}),
    ((118,), '불얼음 봉우리\n석유 파이프라인', K, None, 8),
    ((119, 120), '졸리 로저의 석호\n물 파이프라인', K, None, 8),
    ((121,), '보일러실', W, K, 8),
    ((122,), '하수\n시설', W, K, 8),
    ((123,), '품질\n관리실', W, K, 8),
    ((124,), '케이블실', W, K, 8),
    ((125,), '수리\n창고', W, K, 8),
    ((126,), '포장실', W, K, 8),
    ((127, 128), '거북 해변\n전망대', O, K, 8, {'arrow': True}),
    ((129,), '훈련장', (200, 200, 200), K, 6),
    ((130,), '위험!\n1000\n지기와트', O, K, 8),
    ((131, 132), '힘의\n선인장', (40, 230, 40), K, 6),
    ((133, 134), 'UFO\n놀이기구', Y, (200, 0, 200), 4),
    ((135,), '진저\n비어', (80, 220, 80), K, 16, {'thr': 30}),
    ((136,), '총포\n조종', W, K, 12, {'thr': 25}),
    ((137,), '보틀스의\n집', W, K, 4),
    ((138, 139), '고장 중', K, None, 0, {'sticker': True}),
    ((140,), '마녀성\n쪽문', (120, 230, 120), K, 12, {'thr': 25}),
    ((141, 142, 143, 144), '그런티 산업', (120, 230, 120), K, 2),
]


def load(T, ids):
    ims = [T.image(i).transpose(Image.FLIP_TOP_BOTTOM) for i in ids]
    w = sum(im.width for im in ims); h = max(im.height for im in ims)
    c = Image.new('RGBA', (w, h)); x = 0
    for im in ims:
        c.paste(im, (x, 0)); x += im.width
    return c, [im.size for im in ims]


def erase(img, margin, thr0=40.0):
    """안쪽 상자의 글자를 지운다: 바탕 = 안쪽 상자 화소의 중앙값, 바탕과 먼 화소를 표시 → 둘레 평균으로 번지게."""
    a = np.array(img).astype(np.float32)
    h, w = a.shape[:2]
    box = np.zeros((h, w), bool)
    box[margin:h - margin, margin:w - margin] = True
    inner = a[box][:, :3]
    bg = np.median(inner, axis=0)
    d = np.sqrt(((a[..., :3] - bg) ** 2).sum(-1))
    thr = thr0 if thr0 < 40 else max(thr0, np.percentile(d[box], 55) * 1.6)
    mask = (d > thr) & box
    m = Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5))
    mask = (np.array(m) > 0) & box
    known = ~mask
    out = a.copy()
    for _ in range(400):                                    # 둘레에서 안쪽으로 번지기
        if known.all():
            break
        acc = np.zeros_like(out); cnt = np.zeros((h, w), np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            sk = np.roll(known, (dy, dx), (0, 1)); so = np.roll(out, (dy, dx), (0, 1))
            acc += so * sk[..., None]; cnt += sk
        new = (~known) & (cnt > 0)
        out[new] = acc[new] / cnt[new][:, None]
        known = known | new
    out = Image.fromarray(out.clip(0, 255).astype(np.uint8))
    return out.filter(ImageFilter.GaussianBlur(0.6)) if False else out


def draw_text(img, text, fg, outline, margin, maxsize=200, left=0, right=0):
    w0, h = img.size
    w = int(w0 - left - right)
    lines = text.split('\n')
    box_w, box_h = w - 2 * margin - 6, h - 2 * margin - 4
    size = maxsize
    while size > 6:
        f = ImageFont.truetype(FONT, size)
        sp = max(1, size // 10)
        bbs = [f.getbbox(l) for l in lines]
        lw = max(b[2] - b[0] for b in bbs); lh = sum(b[3] - b[1] for b in bbs) + sp * (len(lines) - 1)
        if lw <= box_w and lh <= box_h:
            break
        size -= 1
    d = ImageDraw.Draw(img)
    y = (h - lh) // 2
    sw = max(1, size // 12) if outline else 0
    for l, b in zip(lines, bbs):
        x = int(left) + (w - (b[2] - b[0])) // 2 - b[0]
        if outline:
            d.text((x + sw, y - b[1] + sw), l, font=f, fill=outline + (255,))          # 그림자
        d.text((x, y - b[1]), l, font=f, fill=fg + (255,), stroke_width=sw, stroke_fill=(outline or fg) + (255,))
        y += b[3] - b[1] + sp
    return img


def sticker(img, text):
    """138+139 «고장 중» 띠: 비스듬한 흰 띠(원래 자리) 위에 검은 글자 — 해골 그림은 그대로"""
    w, h = img.size
    band = Image.new('RGBA', (int(w * 0.82), int(h * 0.3)), (0, 0, 0, 0))
    d = ImageDraw.Draw(band)
    d.rounded_rectangle((0, 0, band.width - 1, band.height - 1), 4, fill=(235, 235, 230, 255), outline=(90, 90, 90, 255))
    draw_text(band, text, K, None, 1, 60)
    band = band.rotate(22, expand=True, resample=Image.BICUBIC)
    img.alpha_composite(band, (int(w * 0.6 - band.width / 2), int(h * 0.64 - band.height / 2)))
    return img


def arrow(img, fg, outline):
    w, h = img.size
    d = ImageDraw.Draw(img)
    y = int(h * 0.7); x0, x1 = int(w * 0.66), int(w * 0.93); t = max(3, h // 22); hd = h // 7
    pts = [(x0, y - t), (x1 - hd, y - t), (x1 - hd, y - hd), (x1, y), (x1 - hd, y + hd), (x1 - hd, y + t), (x0, y + t)]
    d.polygon([(px + 2, py + 2) for px, py in pts], fill=outline + (255,))
    d.polygon(pts, fill=fg + (255,))
    return img


def render(T, ids, text, fg, outline, margin, opt=None):
    opt = opt or {}
    img, sizes = load(T, ids)
    a = np.array(img)
    if opt.get('sticker'):
        out = sticker(img.copy(), text)
    elif opt.get('arrow'):
        out = arrow(draw_text(erase(img, margin, opt.get('thr', 40.0)), text, fg, outline, margin, right=img.width * 0.36), fg, outline)
    else:
        out = draw_text(erase(img, margin, opt.get('thr', 40.0)), text, fg, outline, margin, opt.get('max', 200))
    o = np.array(out); o[..., 3] = a[..., 3]                  # 투명도는 원래 그대로
    out = Image.fromarray(o)
    parts, x = [], 0
    for (pw, ph) in sizes:
        parts.append(out.crop((x, 0, x + pw, ph)).transpose(Image.FLIP_TOP_BOTTOM)); x += pw
    return img, out, parts


LOGO_EN, LOGO_JP = 11, 69          # 타이틀 로고(영어 586×320 / 일본어 640×308) — 하스피 «일본판 타이틀은 영문판으로»
BIG = [(13, '게임 오버', (255, 120, 20), (120, 40, 0)), (14, '끝', (70, 60, 230), (230, 140, 40))]   # GAME OVER · THE END


def big_text(w, h, text, fg, ol):
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    return draw_text(img, text, fg, ol, 4, 200)


def logo(T):
    en = T.image(LOGO_EN)
    _, w, h, _, _ = T.entry(LOGO_JP)
    sc = min(w / en.width, h / en.height)
    en = en.resize((round(en.width * sc), round(en.height * sc)), Image.LANCZOS)
    out = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    out.paste(en, ((w - en.width) // 2, (h - en.height) // 2))
    return out


def images(T):
    """{텍스처 번호: 새 그림(저장 방향 그대로)}"""
    out = {LOGO_JP: logo(T)}
    for tid, text, fg, ol in BIG:
        _, w, h, _, _ = T.entry(tid)
        out[tid] = big_text(w, h, text, fg, ol)
    for ids, text, fg, ol, mg, *opt in SIGNS:
        _, _, parts = render(T, ids, text, fg, ol, mg, *opt)
        out.update(zip(ids, parts))
    return out


def patch(tex_bin, tile_argb):
    """textures.bin 바이트에 그림을 제자리로: 기본 단계만 새로 쓰고 밉 단계 수 0(옛 일본어 축소판이 안 섞이게)"""
    import struct
    T = Textures.__new__(Textures); T.d = tex_bin; T.n = struct.unpack('>I', tex_bin[:4])[0]
    d = bytearray(tex_bin)
    H, base = T.hdr0(), T.base()
    for tid, img in images(T).items():
        o, w, h, size, _ = T.entry(tid)
        f = list(struct.unpack_from('>6I', d, H + tid * 0x34 + 0x1C))
        pitch = ((f[0] >> 22) & 0x1FF) * 32
        assert (f[2] & 0x1FFF) + 1 == w and ((f[2] >> 13) & 0x1FFF) + 1 == h and (f[1] & 0x3F) == 6, tid
        assert img.size == (w, h), (tid, img.size)
        px = tile_argb(img, pitch)
        assert len(px) <= size, tid
        d[base + o:base + o + len(px)] = px
        f[4] &= ~(0xF << 6)
        struct.pack_into('>6I', d, H + tid * 0x34 + 0x1C, *f)
    return bytes(d), len(images(T))


def main():
    T = Textures(os.path.join(X360, 'textures.bin'))
    rows = []
    for ids, text, fg, ol, mg, *opt in SIGNS:
        before, after, _ = render(T, ids, text, fg, ol, mg, *opt)
        sc = 2 if before.width <= 256 else 1
        rows.append((ids, before.resize((before.width * sc, before.height * sc)), after.resize((after.width * sc, after.height * sc))))
    W_ = 1300; sheet = Image.new('RGB', (W_, 6000), (30, 30, 30)); y = 0; x = 0; rh = 0
    d = ImageDraw.Draw(sheet)
    for ids, b, a in rows:
        bw = b.width * 2 + 10
        if x + bw > W_:
            x = 0; y += rh + 14; rh = 0
        d.text((x, y), ','.join(map(str, ids)), fill=(255, 255, 0))
        for k, im in enumerate((b, a)):
            bg = Image.new('RGBA', im.size, (70, 70, 70, 255)); bg.alpha_composite(im)
            sheet.paste(bg.convert('RGB'), (x + k * (im.width + 4), y + 12))
        x += bw + 16; rh = max(rh, b.height + 12)
    sheet.crop((0, 0, W_, y + rh + 4)).save(os.path.join(X360, 'signs_preview.png'))
    g = Image.new('RGBA', (1300, 760), (70, 70, 70, 255))
    g.alpha_composite(logo(T), (0, 0))
    for k, (tid, text, fg, ol) in enumerate(BIG):
        _, w, h, _, _ = T.entry(tid)
        g.alpha_composite(big_text(w, h, text, fg, ol), (660 if k == 0 else 0, 330 + 140 * k if k else 330))
    g.convert('RGB').save(os.path.join(X360, 'logo_preview.png'))
    print('→ work/x360/signs_preview.png')


if __name__ == '__main__':
    main()
