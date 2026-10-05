"""Banjo-Tooie translation TSVs.
  work/text/bt_text.tsv           — whole file
  my files/tsv/bt_text_NNN.tsv    — split at 29 KB (UTF-8) for the user
Columns: ID  위치  구분  화자  원문  번역
  위치: asset:sec:idx (asset id hex)
  구분: 대사 (2 sections: bottom/top box) / 목록 (one-section string lists: menus, help, cheats)
  화자: speaker byte (hex); extended speakers (entry type 03) are written 03:XX
  Bytes outside printable ASCII are shown as {XX} (button icons 0x86/0x87, controls)."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import btrom

ROOT = os.path.join(os.path.dirname(__file__), '..')
WHOLE = os.path.join(ROOT, 'work', 'text', 'bt_text.tsv')
SPLIT = os.path.join(ROOT, 'my files', 'tsv')
HEAD = 'ID\t위치\t구분\t화자\t원문\t번역\n'
LIMIT = 29 * 1024


def show(b):
    return ''.join(chr(x) if 0x20 <= x < 0x7F and x not in (0x7B, 0x7D) else '{%02X}' % x
                   for x in b.rstrip(b'\0'))


def rows():
    rom = btrom.load_rom()
    tab = btrom.asset_table(rom)
    out = []
    for k, (p, sz, f) in enumerate(tab):
        if not sz:
            continue
        r = btrom.asset(rom, tab, k)
        if not btrom.is_dialog(r):
            continue
        _, secs, _ = btrom.parse_dialog(r)
        kind = '대사' if len(secs) == 2 else '목록'
        for si, sec in enumerate(secs):
            for i, (cmd, spk, raw) in enumerate(sec):
                if btrom.is_text_entry(cmd, raw):
                    who = '03:%02X' % spk if cmd == 3 else '%02X' % cmd
                    out.append(('%04X:%d:%d' % (k, si, i), kind, who, show(raw)))
    return out


def main():
    lines = ['%05d\t%s\t%s\t%s\t%s\t\n' % ((n + 1,) + r) for n, r in enumerate(rows())]
    os.makedirs(os.path.dirname(WHOLE), exist_ok=True)
    with open(WHOLE, 'w', encoding='utf-8', newline='\n') as f:
        f.write(HEAD + ''.join(lines))
    os.makedirs(SPLIT, exist_ok=True)
    for f in os.listdir(SPLIT):
        if f.startswith('bt_text_') and f.endswith('.tsv'):
            os.remove(os.path.join(SPLIT, f))
    files, cur, size = [], [], len(HEAD.encode())
    for ln in lines:
        b = len(ln.encode())
        if cur and size + b > LIMIT:
            files.append(cur); cur, size = [], len(HEAD.encode())
        cur.append(ln); size += b
    if cur:
        files.append(cur)
    for i, fl in enumerate(files):
        with open(os.path.join(SPLIT, 'bt_text_%03d.tsv' % (i + 1)), 'w', encoding='utf-8', newline='\n') as f:
            f.write(HEAD + ''.join(fl))
    print(len(lines), 'rows ->', len(files), 'files')


if __name__ == '__main__':
    main()
