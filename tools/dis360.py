"""disassemble a range of a decrypted 360 PE image: python tools/dis360.py <pe> <start va> <count>"""
import sys, capstone
md = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_32 | capstone.CS_MODE_BIG_ENDIAN)
d = open(sys.argv[1], 'rb').read()
va = int(sys.argv[2], 16); n = int(sys.argv[3])
for i in md.disasm(d[va - 0x82000000:va - 0x82000000 + 4 * n], va):
    print(f'{i.address:08x}: {i.mnemonic} {i.op_str}')
