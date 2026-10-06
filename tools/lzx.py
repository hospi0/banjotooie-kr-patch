"""LZX decoder (port of CHMLib lzx.c) + XMemCompress chunk framing as used by XNB / 4J's .cmp.

Chunk framing (bnnm, gist 1d771a40): per chunk
   FF hi lo hi lo  -> dst_size(BE16), src_size(BE16)
   hi lo           -> dst_size = 0x8000, src_size(BE16)
then src_size bytes of LZX bitstream (bit buffer restarts every chunk, decoder state carries over).
"""
import struct

MIN_MATCH = 2
NUM_CHARS = 256
PRETREE_N, PRETREE_BITS = 20, 6
MAIN_MAX, MAIN_BITS = 256 + 50 * 8, 12
LEN_MAX, LEN_BITS = 250, 12
ALIGN_N, ALIGN_BITS = 8, 7
SAFETY = 64

EXTRA = [0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13,
         14, 14, 15, 15, 16, 16] + [17] * 15
POSBASE = [0]
for e in EXTRA[:-1]:
    POSBASE.append(POSBASE[-1] + (1 << e))


class LZXError(Exception):
    pass


def make_table(nsyms, nbits, length):
    table = [0] * ((1 << nbits) + nsyms * 2 + 4)
    pos = 0
    table_mask = 1 << nbits
    bit_mask = table_mask >> 1
    next_sym = bit_mask
    bit_num = 1
    while bit_num <= nbits:
        for sym in range(nsyms):
            if length[sym] == bit_num:
                leaf = pos
                pos += bit_mask
                if pos > table_mask:
                    raise LZXError('table overrun')
                for f in range(bit_mask):
                    table[leaf + f] = sym
        bit_mask >>= 1
        bit_num += 1
    if pos != table_mask:
        for s in range(pos, table_mask):
            table[s] = 0
        pos <<= 16
        table_mask <<= 16
        bit_mask = 1 << 15
        while bit_num <= 16:
            for sym in range(nsyms):
                if length[sym] == bit_num:
                    leaf = pos >> 16
                    for fill in range(bit_num - nbits):
                        if table[leaf] == 0:
                            need = (next_sym << 1) + 2
                            if need > len(table):
                                table += [0] * (need - len(table))
                            table[next_sym << 1] = 0
                            table[(next_sym << 1) + 1] = 0
                            table[leaf] = next_sym
                            next_sym += 1
                        leaf = table[leaf] << 1
                        if (pos >> (15 - fill)) & 1:
                            leaf += 1
                    if leaf >= len(table):
                        table += [0] * (leaf + 1 - len(table))
                    table[leaf] = sym
                    pos += bit_mask
                    if pos > table_mask:
                        raise LZXError('table overflow')
            bit_mask >>= 1
            bit_num += 1
    if pos == table_mask:
        return table
    if any(length[s] for s in range(nsyms)):
        raise LZXError('bad table')
    return table


class Bits:
    __slots__ = ('d', 'p', 'buf', 'left')

    def __init__(self, d, p):
        self.d, self.p, self.buf, self.left = d, p, 0, 0

    def ensure(self, n):
        d = self.d
        while self.left < n:
            p = self.p
            w = (d[p] if p < len(d) else 0) | ((d[p + 1] if p + 1 < len(d) else 0) << 8)
            self.buf = (self.buf << 16) | w
            self.left += 16
            self.p = p + 2

    def peek(self, n):
        return (self.buf >> (self.left - n)) & ((1 << n) - 1)

    def remove(self, n):
        self.left -= n
        self.buf &= (1 << self.left) - 1

    def read(self, n):
        if n == 0:
            return 0
        self.ensure(n)
        v = (self.buf >> (self.left - n)) & ((1 << n) - 1)
        self.left -= n
        self.buf &= (1 << self.left) - 1
        return v

    def sym(self, table, nbits, maxsym, lens):
        self.ensure(16)
        i = table[(self.buf >> (self.left - nbits)) & ((1 << nbits) - 1)]
        if i >= maxsym:
            k = self.left - nbits
            while True:
                k -= 1
                if k < 0:
                    raise LZXError('huff overrun')
                i = table[(i << 1) | ((self.buf >> k) & 1)]
                if i < maxsym:
                    break
        n = lens[i]
        self.left -= n
        self.buf &= (1 << self.left) - 1
        return i


class LZX:
    def __init__(self, window_bits, x360=False):
        self.x360 = x360          # Xbox 360: no pad byte after odd-length uncompressed block (Gildor/UEViewer)
        self.wsize = 1 << window_bits
        self.window = bytearray(self.wsize)
        slots = 42 if window_bits == 20 else 50 if window_bits == 21 else window_bits << 1
        self.main_elements = NUM_CHARS + (slots << 3)
        self.R = [1, 1, 1]
        self.header_read = False
        self.frames = 0
        self.block_remaining = 0
        self.block_type = 0
        self.block_length = 0
        self.intel_curpos = 0
        self.intel_started = False
        self.intel_filesize = 0
        self.wpos = 0
        self.main_len = [0] * (MAIN_MAX + SAFETY)
        self.len_len = [0] * (LEN_MAX + SAFETY)
        self.align_len = [0] * ALIGN_N
        self.main_t = self.len_t = self.align_t = None

    def _read_lens(self, b, lens, first, last):
        pre = [b.read(4) for _ in range(20)]
        t = make_table(PRETREE_N, PRETREE_BITS, pre)
        x = first
        while x < last:
            z = b.sym(t, PRETREE_BITS, PRETREE_N, pre)
            if z == 17:
                y = b.read(4) + 4
                for _ in range(y):
                    lens[x] = 0; x += 1
            elif z == 18:
                y = b.read(5) + 20
                for _ in range(y):
                    lens[x] = 0; x += 1
            elif z == 19:
                y = b.read(1) + 4
                z = b.sym(t, PRETREE_BITS, PRETREE_N, pre)
                z = lens[x] - z
                if z < 0:
                    z += 17
                for _ in range(y):
                    lens[x] = z; x += 1
            else:
                z = lens[x] - z
                if z < 0:
                    z += 17
                lens[x] = z; x += 1

    def decompress(self, data, inpos, inlen, outlen, bits=None):
        """bits: pass a persistent Bits to read a continuous stream (libmspack style, realign per frame)."""
        b = bits if bits is not None else Bits(data, inpos)
        endinp = inpos + inlen if bits is None else len(data) + 4
        window, wsize = self.window, self.wsize
        R0, R1, R2 = self.R
        wpos = self.wpos
        if not self.header_read:
            i = j = 0
            if b.read(1):
                i = b.read(16); j = b.read(16)
            self.intel_filesize = (i << 16) | j
            self.header_read = True
        togo = outlen
        while togo > 0:
            if self.block_remaining == 0:
                if self.block_type == 3:
                    if self.block_length & 1 and not self.x360:
                        b.p += 1
                    b.buf = b.left = 0
                self.block_type = b.read(3)
                i = b.read(16); j = b.read(8)
                self.block_remaining = self.block_length = (i << 8) | j
                bt = self.block_type
                if bt == 2:
                    for k in range(8):
                        self.align_len[k] = b.read(3)
                    self.align_t = make_table(ALIGN_N, ALIGN_BITS, self.align_len)
                if bt in (1, 2):
                    self._read_lens(b, self.main_len, 0, 256)
                    self._read_lens(b, self.main_len, 256, self.main_elements)
                    self.main_t = make_table(MAIN_MAX, MAIN_BITS, self.main_len)
                    if self.main_len[0xE8]:
                        self.intel_started = True
                    self._read_lens(b, self.len_len, 0, 249)
                    self.len_t = make_table(LEN_MAX, LEN_BITS, self.len_len)
                elif bt == 3:
                    self.intel_started = True
                    b.ensure(16)
                    if b.left > 16:
                        b.p -= 2
                    R0, R1, R2 = struct.unpack_from('<III', data, b.p)
                    b.p += 12
                    b.buf = b.left = 0
                else:
                    raise LZXError('bad block type %d' % bt)
            if b.p > endinp and (b.p > endinp + 2 or b.left < 16):
                raise LZXError('input overrun')
            while self.block_remaining > 0 and togo > 0:
                this_run = min(self.block_remaining, togo)
                togo -= this_run
                self.block_remaining -= this_run
                wpos &= wsize - 1
                if wpos + this_run > wsize:
                    raise LZXError('run straddles window')
                bt = self.block_type
                if bt == 3:
                    window[wpos:wpos + this_run] = data[b.p:b.p + this_run]
                    b.p += this_run; wpos += this_run
                    continue
                main_t, main_len = self.main_t, self.main_len
                len_t, len_len = self.len_t, self.len_len
                while this_run > 0:
                    me = b.sym(main_t, MAIN_BITS, MAIN_MAX, main_len)
                    if me < NUM_CHARS:
                        window[wpos] = me; wpos += 1; this_run -= 1
                        continue
                    me -= NUM_CHARS
                    ml = me & 7
                    if ml == 7:
                        ml += b.sym(len_t, LEN_BITS, LEN_MAX, len_len)
                    ml += MIN_MATCH
                    mo = me >> 3
                    if mo > 2:
                        if bt == 1:
                            if mo != 3:
                                mo = POSBASE[mo] - 2 + b.read(EXTRA[mo])
                            else:
                                mo = 1
                        else:
                            extra = EXTRA[mo]
                            mo = POSBASE[mo] - 2
                            if extra > 3:
                                mo += b.read(extra - 3) << 3
                                mo += b.sym(self.align_t, ALIGN_BITS, ALIGN_N, self.align_len)
                            elif extra == 3:
                                mo += b.sym(self.align_t, ALIGN_BITS, ALIGN_N, self.align_len)
                            elif extra > 0:
                                mo += b.read(extra)
                            else:
                                mo = 1
                        R2, R1, R0 = R1, R0, mo
                    elif mo == 0:
                        mo = R0
                    elif mo == 1:
                        mo = R1; R1 = R0; R0 = mo
                    else:
                        mo = R2; R2 = R0; R0 = mo
                    dst = wpos
                    src = dst - mo
                    wpos += ml
                    if wpos > wsize:
                        raise LZXError('match past window')
                    this_run -= ml
                    if src >= 0 and src + ml <= dst:
                        window[dst:dst + ml] = window[src:src + ml]
                    else:
                        for k in range(ml):
                            s = src + k
                            window[dst + k] = window[s + wsize if s < 0 else s]
        if bits is not None:                      # frame end: re-align to 16 bits
            if b.left > 0:
                b.ensure(16)
            if b.left & 15:
                b.remove(b.left & 15)
        out = bytearray(window[(wsize if wpos == 0 else wpos) - outlen:(wsize if wpos == 0 else wpos)])
        self.wpos = wpos
        self.R = [R0, R1, R2]
        if self.frames < 32768 and self.intel_filesize:
            if outlen <= 6 or not self.intel_started:
                self.intel_curpos += outlen
            else:
                cur = self.intel_curpos
                fs = self.intel_filesize
                self.intel_curpos = cur + outlen
                i = 0
                end = outlen - 10
                while i < end:
                    if out[i] != 0xE8:
                        i += 1; cur += 1; continue
                    a = struct.unpack_from('<i', out, i + 1)[0]
                    if -cur <= a < fs:
                        r = a - cur if a >= 0 else a + fs
                        struct.pack_into('<i', out, i + 1, r)
                    i += 5; cur += 5
        self.frames += 1
        return bytes(out)


def xmem_chunks(data, p, window_bits=16, limit=None, x360=True):
    """Decode chunked XMemCompress/LZX starting at p. -> (bytes, end)"""
    st = LZX(window_bits, x360)
    out = bytearray()
    while p < len(data) and (limit is None or len(out) < limit):
        hi = data[p]
        if hi == 0xFF:
            dst = (data[p + 1] << 8) | data[p + 2]
            src = (data[p + 3] << 8) | data[p + 4]
            p += 5
        else:
            dst = 0x8000
            src = (hi << 8) | data[p + 1]
            p += 2
        if src == 0 or dst == 0:
            break
        out += st.decompress(data, p, src, dst)
        p += src
    return bytes(out), p


def xmem_stream(data, p, window_bits=17, limit=None, x360=True, total=None):
    """libmspack/UEViewer style: strip chunk headers into one continuous stream, decode 32 KB frames."""
    payload = bytearray()
    while p < len(data):
        hi = data[p]
        if hi == 0xFF:
            src = (data[p + 3] << 8) | data[p + 4]; p += 5
        else:
            src = (hi << 8) | data[p + 1]; p += 2
        if src == 0:
            break
        payload += data[p:p + src]
        p += src
    payload = bytes(payload)
    st = LZX(window_bits, x360)
    b = Bits(payload, 0)
    out = bytearray()
    while (limit is None or len(out) < limit) and (total is None or len(out) < total):
        n = 0x8000 if total is None else min(0x8000, total - len(out))
        if b.p >= len(payload) and b.left < 16:
            break
        out += st.decompress(payload, 0, 0, n, bits=b)
    return bytes(out), p


def _last_frame(st, data, q, src):
    """Final frame of an XCTD segment: output size is not stored. Find the largest size whose
    decode succeeds without reading past the chunk (binary search on a copy of the state)."""
    import copy
    lo, hi, best = 1, 0x8000, None
    while lo <= hi:
        mid = (lo + hi) // 2
        t = copy.deepcopy(st)
        b = Bits(data, q)
        try:
            out = t.decompress(data, q, src, mid, bits=None)
            ok = True
        except LZXError:
            ok = False
        if ok:
            best = (mid, out, t); lo = mid + 1
        else:
            hi = mid - 1
    return best


def xctd_decompress(data, first=0x78, seg=0x20000, window_bits=17, log=None):
    """Xbox 360 XCTD file (magic 0FF512ED, e.g. Banjo-Kazooie XBLA db360.cmp):
    every 128 KB of the compressed file is an independent LZX stream (fresh state) of XMem frames.
    All frames are 32 KB except the segment's last one, whose (smaller) size is not stored."""
    out = bytearray()
    start = first
    while start < len(data):
        end = min((start // seg + 1) * seg, len(data))
        st = LZX(window_bits, x360=True)
        p = start
        while p < end:
            hi = data[p]
            if hi == 0xFF:
                dst = (data[p + 1] << 8) | data[p + 2]; src = (data[p + 3] << 8) | data[p + 4]; q = p + 5
            else:
                dst = 0x8000; src = (hi << 8) | data[p + 1]; q = p + 2
            if src == 0:
                break
            last = q + src >= end or not any(data[q + src:end])
            if not last:
                out += st.decompress(data, q, src, dst)
            else:
                best = _last_frame(st, data, q, src)
                if best is None:
                    raise LZXError('last frame of segment %X undecodable' % start)
                n, o, st = best
                out += o
                if log is not None:
                    log.append((start, n))
                break
            p = q + src
        start = end
    return bytes(out)
