import zlib,sys
def apply(src,patch):
    assert patch[:4]==b'BPS1'; p=4
    def num():
        nonlocal p; d=0;s=1
        while True:
            x=patch[p];p+=1;d+=(x&0x7f)*s
            if x&0x80: return d
            s<<=7;d+=s
    ss=num();ts=num();ms=num(); meta=patch[p:p+ms];p+=ms
    assert ss==len(src)
    out=bytearray(ts);o=0;sr=0;tr=0;end=len(patch)-12
    while p<end:
        d=num();cmd=d&3;ln=(d>>2)+1
        if cmd==0: out[o:o+ln]=src[o:o+ln]
        elif cmd==1: out[o:o+ln]=patch[p:p+ln];p+=ln
        else:
            d=num();off=(-1 if d&1 else 1)*(d>>1)
            if cmd==2:
                sr+=off; out[o:o+ln]=src[sr:sr+ln]; sr+=ln
            else:
                tr+=off
                for i in range(ln): out[o+i]=out[tr];tr+=1
        o+=ln
    import struct
    sc,tc,pc=struct.unpack('<III',patch[-12:])
    assert zlib.crc32(src)==sc and zlib.crc32(out)==tc, 'crc'
    return bytes(out),meta
