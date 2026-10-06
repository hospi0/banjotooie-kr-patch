"""Minimal XEX2 loader (retail-encrypted, basic/normal compression) -> PE image bytes + load address.
Layout per Xenia (xex2_info.h). Read-only; used to find/emulate code inside default.xex."""
import struct, sys, os
from Crypto.Cipher import AES
sys.path.insert(0, os.path.dirname(__file__))
import lzx

RETAIL_KEY = bytes.fromhex('20B185A59D28FDC340583FBB0896BF91')
DEVKIT_KEY = bytes(16)


def load(path):
    d = open(path, 'rb').read()
    assert d[:4] == b'XEX2'
    flags, pe_off, _, sec_off, nhdr = struct.unpack_from('>IIIII', d, 4)
    hdrs = {}
    for i in range(nhdr):
        k, v = struct.unpack_from('>II', d, 0x18 + i * 8)
        hdrs[k] = v
    image_size = struct.unpack_from('>I', d, sec_off + 4)[0]
    load_addr = struct.unpack_from('>I', d, sec_off + 0x110)[0]
    enc_key = d[sec_off + 0x150:sec_off + 0x160]
    ffi = hdrs[0x3FF]                                # file format info (offset)
    info_size, enc_type, comp_type = struct.unpack_from('>IHH', d, ffi)
    data = d[pe_off:]
    if enc_type == 1:
        for key in (RETAIL_KEY, DEVKIT_KEY):
            sess = AES.new(key, AES.MODE_ECB).decrypt(enc_key)
            dec = AES.new(sess, AES.MODE_CBC, bytes(16)).decrypt(data[:len(data) // 16 * 16])
            if comp_type != 1 or True:
                break
        data = dec
    if comp_type == 1:                               # basic: (data_size, zero_size) blocks
        n = (info_size - 8) // 8
        out = bytearray(); p = 0
        for i in range(n):
            ds, zs = struct.unpack_from('>II', d, ffi + 8 + i * 8)
            out += data[p:p + ds] + bytes(zs); p += ds
        out += bytes(max(0, image_size - len(out)))   # 반조-투이: 블록 합계 뒤 0x8000 이 0 (이미지 크기까지 채움)
        image = bytes(out)
    elif comp_type == 2:                             # normal: chained blocks of LZX chunks
        window = struct.unpack_from('>I', d, ffi + 8)[0]
        block_size = struct.unpack_from('>I', d, ffi + 12)[0]
        comp = bytearray(); p = 0
        while block_size:
            nxt = struct.unpack_from('>I', data, p)[0]
            q = p + 24
            while True:
                cs = struct.unpack_from('>H', data, q)[0]; q += 2
                if not cs:
                    break
                comp += data[q:q + cs]; q += cs
            p += block_size
            block_size = nxt
        wb = window.bit_length() - 1
        st = lzx.LZX(wb, x360=True)
        b = lzx.Bits(bytes(comp), 0)
        out = bytearray()
        while len(out) < image_size:
            out += st.decompress(bytes(comp), 0, 0, min(0x8000, image_size - len(out)), bits=b)
        image = bytes(out)
    else:
        image = data
    return image, load_addr, hdrs


if __name__ == '__main__':
    img, base, hdrs = load(sys.argv[1])
    print('image', len(img), 'load', hex(base), 'MZ' if img[:2] == b'MZ' else img[:4])
    if len(sys.argv) > 2:
        open(sys.argv[2], 'wb').write(img)


def write_plain(src_path, image, out_path):
    """원본 XEX2 머리를 그대로 두고 본문을 «암호화 없음 + basic 압축(블록 1개)»으로 바꿔 쓴다 (Xenia 용)."""
    d = bytearray(open(src_path, 'rb').read())
    flags, pe_off, _, sec_off, nhdr = struct.unpack_from('>IIIII', d, 4)
    hdrs = {}
    for i in range(nhdr):
        k, v = struct.unpack_from('>II', d, 0x18 + i * 8)
        hdrs[k] = v
    image_size = struct.unpack_from('>I', d, sec_off + 4)[0]
    assert len(image) == image_size, (len(image), image_size)
    ffi = hdrs[0x3FF]
    old_size = struct.unpack_from('>I', d, ffi)[0]
    assert old_size >= 16
    struct.pack_into('>IHHII', d, ffi, 16, 0, 1, len(image), 0)
    hdr = bytes(d[:pe_off])
    open(out_path, 'wb').write(hdr + bytes(image))
