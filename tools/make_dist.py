# -*- coding: utf-8 -*-
r"""배포 묶음 — dist/BanjoTooie_KR_v0.9/ (xdelta + xdelta.exe + readme.txt + 패치적용.bat)
     + 설치본 F:\hospi\roms\n64 Roms\Banjo-Tooie (K).zip

  python tools/btbuild.py work/text/fixed work/BT_KR_v0.9.z64   # 먼저 빌드
  python tools/make_dist.py                               # xdelta 생성 → 원본에 적용해 바이트 대조 → 설치본 zip

규칙: 해시는 MD5 대문자 · 한국어 문서는 CP949(CRLF) · 버전은 v0.9 한 자리 · bat 의 if 블록 안 echo 에 괄호 금지.
"""
import hashlib, os, shutil, subprocess, sys, zipfile

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)

VER = 'v0.9'
NAME = 'Banjo-Tooie (USA).z64'
SRC = os.path.join(r'C:\claude\roms\n64', NAME)
SRC_MD5 = '40e98faa24ac3ebe1d25cb5e5ddf49e4'
OUT = os.path.join(ROOT, 'work', 'BT_KR_' + VER + '.z64')
PKG = 'BanjoTooie_KR_' + VER
DIST = os.path.join(ROOT, 'dist', PKG)
PATCH = PKG + '.xdelta'
XDELTA = r'C:\claude\utils\xdelta.exe'
INSTALL = r'F:\hospi\roms\n64 Roms\Banjo-Tooie (K).zip'


def md5(p):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''):
            h.update(b)
    return h.hexdigest()


README = """반조-투이 (N64 북미판) 한글 패치 {ver}
==========================================

{name} 에
패치하시면 됩니다.

원본md5 : {src}
패치md5 : {dst}

입니다.


[ 적용 방법 ]

1. 원본 {name} 을 이 패치 묶음과 한 폴더에 둡니다.
   (.z64 빅엔디언 · {srcsize:,} 바이트 · .n64/.v64 는 먼저 .z64 로 바꿔 주세요)
2. 「패치적용.bat」 을 실행합니다.
3. 배치가 원본 MD5 를 먼저 확인하고, 끝난 뒤 결과 MD5 까지 검사합니다.
   원본은 .bak 으로 남겨 둡니다.
4. 패치 후 롬 크기가 {dstsize:,} 바이트(64MB)로 커집니다.


[ 꼭 필요한 것 ]

■ 확장팩(메모리 8MB)이 필요합니다. 한글 글꼴과 코드를 확장 메모리에 올립니다.
   에뮬레이터는 확장팩(Expansion Pak)을 켜 주세요. 실기는 확장팩을 꽂아 주세요.


[ 바뀌는 것 ]

■ 대사 전부(오프닝·등장인물 대화·표지판·그런티의 퀴즈)
■ 메뉴·일시정지·기술 목록·이동 메뉴·주크박스 곡 이름·멀티플레이 메뉴
■ 세계·지역 이름은 뜻으로 옮겼습니다(마녀섬·마야 대혼란 사원·반짝 협곡 광산 등)
■ 치트 코드는 돌 글자로 영어를 입력하므로 영어 그대로 두었습니다
"""

BAT = r"""@echo off
setlocal
set NAME={name}
set PATCH={patch}
set SRCMD5={src}
set DSTMD5={dst}

echo.
echo  ==============================================
echo    Banjo-Tooie ^(N64 USA^) Korean Patch {ver}
echo  ==============================================
echo.

if not exist "%NAME%" (
  echo  [!] "%NAME%" 파일이 이 폴더에 없습니다.
  echo      원본 .z64 와 같은 폴더에 두고 실행하세요.
  goto END
)
if not exist "%~dp0xdelta.exe" (
  echo  [!] xdelta.exe 가 없습니다. 패치 묶음을 그대로 풀고 실행하세요.
  goto END
)

echo  [1/3] 원본 검사 중...
set HASH=
for /f "skip=1 tokens=* delims=" %%H in ('certutil -hashfile "%NAME%" MD5') do (
  if not defined HASH set HASH=%%H
)
set HASH=%HASH: =%

if /I "%HASH%"=="%DSTMD5%" (
  echo.
  echo  [!] 이미 이 버전의 한글 패치가 적용된 파일입니다.
  goto END
)
if /I not "%HASH%"=="%SRCMD5%" (
  echo.
  echo  [!] 원본 MD5 가 다릅니다. 패치하지 않고 중단합니다.
  echo      필요 : %SRCMD5%
  echo      현재 : %HASH%
  goto END
)

echo  [2/3] 패치 적용 중...
"%~dp0xdelta.exe" -d -f -s "%NAME%" "%~dp0%PATCH%" "%NAME%.kr"
if errorlevel 1 (
  echo  [!] 패치에 실패했습니다.
  if exist "%NAME%.kr" del "%NAME%.kr"
  goto END
)

echo  [3/3] 결과 검사 중...
set HASH2=
for /f "skip=1 tokens=* delims=" %%H in ('certutil -hashfile "%NAME%.kr" MD5') do (
  if not defined HASH2 set HASH2=%%H
)
set HASH2=%HASH2: =%

if /I not "%HASH2%"=="%DSTMD5%" (
  echo  [!] 결과 MD5 가 다릅니다. 원본은 그대로 두고 중단합니다.
  del "%NAME%.kr"
  goto END
)

move /y "%NAME%" "%NAME%.bak" >nul
move /y "%NAME%.kr" "%NAME%" >nul
echo.
echo  [OK] 한글 패치 완료. 원본은 "%NAME%.bak" 으로 남겨 두었습니다.

:END
echo.
pause
endlocal
"""


def write_cp949(path, text):
    data = text.replace('\r\n', '\n').replace('\n', '\r\n').encode('cp949')
    with open(path, 'wb') as f:
        f.write(data)


def main():
    src_md5, dst_md5 = md5(SRC), md5(OUT)
    assert src_md5 == SRC_MD5, src_md5
    os.makedirs(DIST, exist_ok=True)
    patch = os.path.join(DIST, PATCH)
    subprocess.run([XDELTA, '-e', '-9', '-f', '-s', SRC, OUT, patch], check=True)
    shutil.copyfile(XDELTA, os.path.join(DIST, 'xdelta.exe'))
    chk = os.path.join(ROOT, 'work', 'dist_check.z64')
    subprocess.run([XDELTA, '-d', '-f', '-s', SRC, patch, chk], check=True)
    ok = md5(chk) == dst_md5
    os.remove(chk)
    if not ok:
        raise SystemExit('⛔ xdelta 되짚기 결과가 패치본과 다르다')
    v = dict(ver=VER, name=NAME, patch=PATCH, src=src_md5, dst=dst_md5,
             srcsize=os.path.getsize(SRC), dstsize=os.path.getsize(OUT))
    write_cp949(os.path.join(DIST, 'readme.txt'),
                README.format(**dict(v, src=src_md5.upper(), dst=dst_md5.upper())))
    write_cp949(os.path.join(DIST, '패치적용.bat'), BAT.format(**v))
    with zipfile.ZipFile(INSTALL, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(OUT, 'Banjo-Tooie (K).z64')
    print('✅ %s\n   xdelta %d B · 원본md5 %s · 패치md5 %s · 되짚기 일치\n   설치 %s'
          % (DIST, os.path.getsize(patch), src_md5.upper(), dst_md5.upper(), INSTALL))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
