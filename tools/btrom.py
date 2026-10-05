"""Banjo-Tooie (USA) ROM access: asset table + rarezip (BE16 size>>4 + raw deflate)."""
import struct, zlib

ROM_PATH = r'C:\claude\roms\n64\Banjo-Tooie (USA).z64'
TABLE = 0x5180      # [BE32 count][ffffffff] + count * BE32 ((offset/4) << 8 | flags)
DATA = 0x12B24      # offsets are relative to this


def load_rom(path=ROM_PATH):
    return open(path, 'rb').read()


def asset_table(rom):
    n = struct.unpack_from('>I', rom, TABLE)[0]
    ent = [struct.unpack_from('>I', rom, TABLE + 8 + 4 * k)[0] for k in range(n)]
    out = []
    for k, e in enumerate(ent):
        off = (e >> 8) * 4
        nxt = (ent[k + 1] >> 8) * 4 if k + 1 < n else off
        out.append((DATA + off, nxt - off, e & 0xFF))
    return out


def unzip(blob):
    """-> bytes or None if blob is not a rarezip stream."""
    if len(blob) < 4:
        return None
    size = struct.unpack_from('>H', blob, 0)[0] << 4
    if not size:
        return None
    try:
        o = zlib.decompressobj(-15)
        r = o.decompress(blob[2:])
    except zlib.error:
        return None
    if not o.eof or not (size - 16 < len(r) <= size):
        return None
    return r


def asset(rom, tab, k):
    p, size, flags = tab[k]
    blob = rom[p:p + size]
    r = unzip(blob)
    return r if r is not None else blob


def parse_dialog(r):
    """Tooie dialogue: [nlang][u16le off]*nlang, at offset two sections, each [count] + entries:
         cmd >= 0x80        : speaker cmd, [len][text]          (as in Banjo-Kazooie)
         cmd == 0x03        : extended speaker, [speaker][len][text]
         other              : control, [len][data]
    -> (nlang, [[(cmd, speaker_or_None, raw)]], end)"""
    nlang = r[0]
    p = struct.unpack_from('<H', r, 1)[0]
    secs = []
    while len(secs) < 2 and p < len(r):        # list-type blocks (menus, cheat lists) have one section
        if secs and not any(r[p:]):
            break
        cnt = r[p]; p += 1
        ent = []
        for _ in range(cnt):
            cmd = r[p]
            if cmd == 3:
                spk, ln = r[p + 1], r[p + 2]
                ent.append((cmd, spk, r[p + 3:p + 3 + ln])); p += 3 + ln
            else:
                ln = r[p + 1]
                ent.append((cmd, None, r[p + 2:p + 2 + ln])); p += 2 + ln
        secs.append(ent)
    return nlang, secs, p


def is_dialog(r):
    if len(r) < 8 or r[:3] != b'\x01\x03\x00':
        return False
    try:
        _, secs, end = parse_dialog(r)
    except IndexError:
        return False
    return end <= len(r) and len(r) - end < 16 and any(secs)


def is_text_entry(cmd, raw):
    return (cmd >= 0x80 or cmd == 3) and raw[-1:] == b'\0' and any(0x20 < x < 0x7F for x in raw)
