import zlib,struct
def scan(rom,lo,hi,align=4):
    out=[];p=lo
    while p<hi-4:
        sz=struct.unpack_from('>H',rom,p)[0]<<4; ok=False
        if sz>=0x20:
            try:
                o=zlib.decompressobj(-15); r=o.decompress(rom[p+2:p+2+sz+0x2000])
                if o.eof and sz-16<len(r)<=sz:
                    used=min(sz+0x2000,len(rom)-p-2)-len(o.unused_data)
                    out.append((p,used+2,r)); p+=used+2; p=(p+3)&~3; ok=True
            except zlib.error: pass
        if not ok: p+=align
    return out
