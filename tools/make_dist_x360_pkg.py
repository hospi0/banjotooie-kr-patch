# -*- coding: utf-8 -*-
r"""XBLA(엑스박스 360) «패키지판» 배포 묶음 (2026-10-07) — 원본 LIVE 패키지 → 한글 LIVE 패키지 xdelta 하나
  dist/<이름>_X360_KR_<VER>_package/ : xdelta + xdelta.exe + readme.txt(CP949) + 패치적용.bat(CP949)
  한글 패키지 = tools/stfs.py rebuild(원본 패키지, 한글판 폴더에서 바뀐 파일) — 서명은 원본 그대로라 Xenia 전용.
  검증: ①원본 그대로 다시 쌓기 = 원본 바이트 ②xdelta 를 원본에 적용 = 만든 패키지 ③만든 패키지에서 꺼낸 파일 = 한글판 폴더 파일(전부)
  python tools/make_dist_x360_pkg.py [bk|bt]   (먼저 x360build 로 한글판 폴더를 만들 것 — 기존 make_dist_x360 의 OUT_DIR)
  규칙: 해시는 MD5 대문자 · 한국어 문서는 CP949(CRLF) · 버전 v0.9 꼴 · bat 의 if 블록 안 echo 에 괄호 금지."""
import hashlib, os, shutil, subprocess, sys, zipfile
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import stfs

XDELTA = r'C:\claude\utils\xdelta.exe'
CFG = {
    'bk': dict(title='반조-카주이', en='Banjo-Kazooie', tid='58410954', name='BanjoKazooie', ver='v0.9',
               src=r'F:\hospi\roms\xbox360 roms\Banjo Kazooie', src_md5='7B79170FA9D7847C8422934BC2A59E98',
               kr=r'F:\hospi\roms\xbox360 roms\Banjo Kazooie KR', out='Banjo Kazooie [KR]', mb=50, win=64 << 20,
               old=r'dist\BanjoKazooie_X360_KR_v0.9\readme.txt'),
    'bt': dict(title='반조-투이', en='Banjo-Tooie', tid='58410955', name='BanjoTooie', ver='v0.9',
               src=r'F:\hospi\roms\xbox360 roms\Banjo Tooie', src_md5='C26DC55C00CCEA88446A85E81D21B0E4',
               kr=r'F:\hospi\roms\xbox360 roms\Banjo Tooie KR', out='Banjo Tooie [KR]', mb=98, win=128 << 20,
               old=r'dist\BanjoTooie_X360_KR_v0.9\readme.txt'),
}


def md5(p):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''):
            h.update(b)
    return h.hexdigest().upper()


README = """{title} (엑스박스 360 XBLA) 한글 패치 {ver} - 패키지판
==========================================

엑스박스 라이브 아케이드판 {en} (타이틀 ID {tid}) 용입니다.
Xenia 에뮬레이터 전용입니다(실기는 시험하지 않았습니다).
원본 LIVE 패키지 파일에 바로 적용해 한글판 LIVE 패키지 파일 하나를 만듭니다.
(폴더로 풀어 쓰는 "폴더판" 과 내용은 같습니다)

한글은 게임의 「일본어」 언어 자리에 들어갑니다.


[ 적용 방법 ]

1. 이 패치 묶음을 푼 폴더에 원본 LIVE 패키지 파일을 넣습니다.
   (약 {mb}MB, 확장자 없는 파일 · 파일 이름은 아무래도 됩니다)

   원본md5 : {src_md5}
   패치md5 : {dst_md5}

2. 「패치적용.bat」 을 실행합니다.
   배치가 패키지를 MD5 로 찾아 「{out}」 패키지 파일을 만들고
   결과 MD5 까지 검사합니다. 원본 패키지는 그대로 둡니다.

   직접 적용:
     xdelta.exe -d -B {win} -s "원본 패키지" "{patch}" "{out}"

3. Xenia 의 이 게임 설정 파일에서 언어를 일본어로 바꿉니다.

   [XConfig]
   user_language = 2

4. Xenia 에서 「{out}」 파일을 엽니다(File - Open).


"""

BAT = r"""@echo off
setlocal
cd /d "%~dp0"
set XD=%~dp0xdelta.exe
set SRCMD5={src_md5}
set DSTMD5={dst_md5}
set OUT={out}

echo.
echo  ==============================================
echo    {en} ^(XBLA^) Korean Patch {ver} - package
echo  ==============================================
echo.

if not exist "xdelta.exe" (
  echo  [!] xdelta.exe 가 없습니다. 패치 묶음을 그대로 풀고 실행하세요.
  goto END
)

echo  [1/3] 원본 LIVE 패키지를 찾는 중...
set PKGFILE=
for %%F in (*) do call :CHECK "%%F"
if not defined PKGFILE (
  echo.
  echo  [!] 이 폴더에서 원본 LIVE 패키지를 찾지 못했습니다.
  echo      MD5 %SRCMD5% 인 패키지 파일을 이 폴더에 넣고 다시 실행하세요.
  goto END
)
echo      찾음: %PKGFILE%

echo  [2/3] 한글판 패키지 만드는 중...
"%XD%" -d -f -B {win} -s "%PKGFILE%" "{patch}" "%OUT%"
if errorlevel 1 (
  echo  [!] 패키지 만들기에 실패했습니다.
  goto FAIL
)
set HASH2=
for /f "skip=1 tokens=* delims=" %%H in ('certutil -hashfile "%OUT%" MD5') do (
  if not defined HASH2 set HASH2=%%H
)
set HASH2=%HASH2: =%
if /I not "%HASH2%"=="%DSTMD5%" (
  echo  [!] 결과 MD5 가 다릅니다.
  goto FAIL
)

echo  [3/3] 완료.
echo.
echo  [OK] "%OUT%" 패키지를 만들었습니다.
echo       Xenia 언어를 일본어 user_language = 2 로 바꾼 뒤
echo       "%OUT%" 파일을 여세요.
goto END

:CHECK
if defined PKGFILE exit /b 0
if /I "%~nx1"=="%OUT%" exit /b 0
if /I "%~x1"==".bat" exit /b 0
if /I "%~x1"==".exe" exit /b 0
if /I "%~x1"==".txt" exit /b 0
if /I "%~x1"==".xdelta" exit /b 0
if %~z1 LSS 40000000 exit /b 0
set HASH=
for /f "skip=1 tokens=* delims=" %%H in ('certutil -hashfile "%~1" MD5') do (
  if not defined HASH set HASH=%%H
)
set HASH=%HASH: =%
if /I "%HASH%"=="%SRCMD5%" set PKGFILE=%~1
exit /b 0

:FAIL
echo.
echo  중단했습니다.
pause
exit

:END
echo.
pause
"""


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    g = sys.argv[1] if len(sys.argv) > 1 else 'bt'
    c = CFG[g]
    assert md5(c['src']) == c['src_md5'], '원본 패키지 MD5 다름'
    s = stfs.STFS(c['src'])
    orig = open(c['src'], 'rb').read()
    assert stfs.rebuild(s, {}) == orig, '⛔원본 그대로 다시 쌓기가 원본과 다름(stfs.py)'
    files = {}; changed = []
    for e in s.entries:
        if e['dir']:
            continue
        p = os.path.join(c['kr'], e['path'].replace('/', os.sep))
        b = open(p, 'rb').read()
        files[e['path']] = b
        if b != s.get(e):
            changed.append(e['path'])
    new = stfs.rebuild(s, files)
    pkg = '%s_X360_KR_%s_package' % (c['name'], c['ver'])
    d = os.path.join(ROOT, 'dist', pkg)
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(d)
    tmp = os.path.join(d, '_new.bin'); open(tmp, 'wb').write(new)
    s2 = stfs.STFS(tmp)                                                   # ③ 만든 패키지에서 다시 꺼내 대조
    for e in s2.entries:
        if not e['dir']:
            assert s2.get(e) == files[e['path']], ('되읽기 불일치', e['path'])
    s2.f.close()
    patch = '%s_X360_KR_%s.xdelta' % (c['name'], c['ver'])
    pp = os.path.join(d, patch)
    subprocess.run([XDELTA, '-e', '-9', '-f', '-B', str(c['win']), '-s', c['src'], tmp, pp], check=True)
    chk = os.path.join(d, '_chk.bin')
    subprocess.run([XDELTA, '-d', '-f', '-B', str(c['win']), '-s', c['src'], pp, chk], check=True)
    dst_md5 = md5(tmp)
    assert md5(chk) == dst_md5, '⛔xdelta 적용 결과가 만든 패키지와 다름'
    os.remove(chk); os.remove(tmp)
    shutil.copy2(XDELTA, os.path.join(d, 'xdelta.exe'))
    v = dict(c, dst_md5=dst_md5, patch=patch)
    rd = README.format(**v)
    old = open(os.path.join(ROOT, c['old']), 'rb').read().decode('cp949').replace('\r\n', '\n')   # «바뀌는 것»·«알려진 사항»은 폴더판 readme 그대로
    a = old.index('[ 바뀌는 것 ]'); b = old.index('[ 한글판 파일 MD5 ]') if '[ 한글판 파일 MD5 ]' in old else len(old)
    rd += old[a:b].rstrip() + '\n'
    open(os.path.join(d, 'readme.txt'), 'wb').write(rd.replace('\n', '\r\n').encode('cp949'))
    open(os.path.join(d, '패치적용.bat'), 'wb').write(BAT.format(**v).replace('\n', '\r\n').encode('cp949'))
    z = os.path.join(ROOT, 'dist', pkg + '.zip')
    with zipfile.ZipFile(z, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(os.listdir(d)):
            zf.write(os.path.join(d, f), pkg + '/' + f)
    print('바뀐 파일', changed)
    print('원본md5 %s → 패치md5 %s · 패키지 %d B' % (c['src_md5'], dst_md5, len(new)))
    for f in sorted(os.listdir(d)):
        print('  %-44s %12d' % (f, os.path.getsize(os.path.join(d, f))))
    print('  zip %s %d B · md5 %s' % (os.path.basename(z), os.path.getsize(z), md5(z)))


if __name__ == '__main__':
    main()
