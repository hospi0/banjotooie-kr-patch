# -*- coding: utf-8 -*-
r"""XBLA(엑스박스 360) 배포 묶음 — dist/BanjoTooie_X360_KR_v0.9/
  (patch\ 파일별 xdelta 36개 + xdelta.exe + readme.txt + 패치적용.bat)

  python tools/x360build.py work/text/fixed <출력폴더> --write   # 먼저 빌드(출력 = 패키지 전체를 푼 폴더 + 한글 파일)
  python tools/make_dist_x360.py [출력폴더]                       # xdelta 생성 → 원본 패키지에 적용해 바이트 대조

★사용자는 원본 LIVE 패키지 파일만 옆에 두면 된다: xdelta 의 원본 = «LIVE 패키지 파일 자체»,
  결과 = 한글판 폴더의 파일 하나하나(안 바뀐 그림·소리 파일도 패키지에서 꺼내 만든다) → 추출 도구 불필요.
Xenia 전용(암호화·서명 안 함), 언어는 일본어로.
규칙: 해시는 MD5 대문자 · 한국어 문서는 CP949(CRLF) · 버전은 v0.9 한 자리 · bat 의 if 블록 안 echo 에 괄호 금지.
"""
import hashlib, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)

VER = 'v0.9'
SRC_PKG = r'F:\hospi\roms\xbox360 roms\Banjo Tooie'          # 원본 LIVE 패키지 파일(읽기만)
SRC_PKG_MD5 = 'c26dc55c00ccea88446a85e81d21b0e4'
OUT_DIR = r'F:\hospi\roms\xbox360 roms\Banjo Tooie KR'
OUT_NAME = 'Banjo Tooie KR'                                  # bat 가 만드는 폴더 이름
PKG = 'BanjoTooie_X360_KR_' + VER
DIST = os.path.join(ROOT, 'dist', PKG)
XDELTA = r'C:\claude\utils\xdelta.exe'
WIN = str(128 << 20)                                           # 원본 창 128MB(패키지 98MB 통째로)


def md5(p):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''):
            h.update(b)
    return h.hexdigest()


README = """반조-투이 (엑스박스 360 XBLA) 한글 패치 {ver}
==========================================

엑스박스 라이브 아케이드판 Banjo-Tooie (타이틀 ID 58410955) 용입니다.
Xenia 에뮬레이터 전용입니다(실기는 시험하지 않았습니다).

한글은 게임의 「일본어」 언어 자리에 들어갑니다.


[ 적용 방법 ]

1. 이 패치 묶음을 푼 폴더에 원본 LIVE 패키지 파일을 넣습니다.
   (약 98MB, 확장자 없는 파일 · 파일 이름은 아무래도 됩니다)

   원본md5 : {src}

2. 「패치적용.bat」 을 실행합니다.
   배치가 패키지를 MD5 로 찾아 「{out}」 폴더에 한글판 게임 파일
   {n}개를 만들고, 파일마다 결과 MD5 까지 검사합니다. 원본 패키지는 그대로 둡니다.
   (패키지를 따로 풀 필요가 없습니다)

3. Xenia 의 이 게임 설정 파일에서 언어를 일본어로 바꿉니다.

   [XConfig]
   user_language = 2

4. Xenia 에서 「{out}」 폴더의 default.xex 를 엽니다.


[ 바뀌는 것 ]

■ 대사 전부(오프닝 데모·등장인물 대화·표지판·그런티의 퀴즈), 360 전용 대사(헤기의 알 등)
■ 360판에서 바뀐 버튼 설명, 버튼 뒤 조사는 360 버튼 이름에 맞춤(A를·B로)
■ 타이틀·메뉴·설정·조작법·도움말(기술·미니게임 설명)·파일 선택·일시정지·순위표·시스템 메시지
■ 오프닝 문구·지역 이름 등 글자가 하나씩 날아드는 연출
■ 일본판이 따로 그려 넣은 간판 그림 41장(그런티 산업·마녀랜드 등), GAME OVER·THE END 그림
■ 타이틀 로고는 영문 로고로 바뀝니다


[ 알려진 사항 ]

■ 엔딩 크레딧·출연진 목록, 돌비·저작권 고지는 영어 그대로입니다.
■ 1st FLOOR 등 일본판에서도 영어였던 간판 그림은 영어 그대로입니다.


[ 한글판 파일 MD5 ]

{table}
"""

BAT = r"""@echo off
setlocal
cd /d "%~dp0"
set XD=%~dp0xdelta.exe
set SRCMD5={src}
set OUT={out}

echo.
echo  ==============================================
echo    Banjo-Tooie ^(XBLA^) Korean Patch {ver}
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

echo  [2/3] 한글판 파일 만드는 중...
if not exist "%OUT%" mkdir "%OUT%"
if not exist "%OUT%\RAWFiles" mkdir "%OUT%\RAWFiles"
{calls}

echo  [3/3] 완료.
echo.
echo  [OK] "%OUT%" 폴더에 한글판을 만들었습니다.
echo       Xenia 언어를 일본어 user_language = 2 로 바꾼 뒤
echo       "%OUT%\default.xex" 를 여세요.
goto END

:CHECK
if defined PKGFILE exit /b 0
if /I "%~x1"==".bat" exit /b 0
if /I "%~x1"==".exe" exit /b 0
if /I "%~x1"==".txt" exit /b 0
if %~z1 LSS 90000000 exit /b 0
set HASH=
for /f "skip=1 tokens=* delims=" %%H in ('certutil -hashfile "%~1" MD5') do (
  if not defined HASH set HASH=%%H
)
set HASH=%HASH: =%
if /I "%HASH%"=="%SRCMD5%" set PKGFILE=%~1
exit /b 0

:MAKE
set NAME=%~1
set DSTMD5=%~2
"%XD%" -d -f -B {win} -s "%PKGFILE%" "patch\%NAME%.xdelta" "%OUT%\%NAME%"
if errorlevel 1 (
  echo  [!] %NAME% 만들기에 실패했습니다.
  goto FAIL
)
set HASH2=
for /f "skip=1 tokens=* delims=" %%H in ('certutil -hashfile "%OUT%\%NAME%" MD5') do (
  if not defined HASH2 set HASH2=%%H
)
set HASH2=%HASH2: =%
if /I not "%HASH2%"=="%DSTMD5%" (
  echo  [!] %NAME% 결과 MD5 가 다릅니다.
  goto FAIL
)
echo      %NAME%
exit /b 0

:FAIL
echo.
echo  중단했습니다.
pause
exit

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
    out_dir = sys.argv[1] if len(sys.argv) > 1 else OUT_DIR
    assert md5(SRC_PKG) == SRC_PKG_MD5, '원본 패키지 MD5 다름'
    files = sorted(os.path.relpath(os.path.join(r, f), out_dir) for r, _, fs in os.walk(out_dir) for f in fs)
    assert any(f == 'default.xex' for f in files) and all(os.sep not in f or f.startswith('RAWFiles' + os.sep) for f in files), files
    if os.path.exists(DIST):
        shutil.rmtree(DIST)
    os.makedirs(os.path.join(DIST, 'patch', 'RAWFiles'))
    chk = os.path.join(ROOT, 'work', 'dist_check.bin')
    rows, calls, total = [], [], 0
    for f in files:
        dst = os.path.join(out_dir, f)
        patch = os.path.join(DIST, 'patch', f + '.xdelta')
        subprocess.run([XDELTA, '-e', '-9', '-S', 'djw', '-B', WIN, '-f', '-s', SRC_PKG, dst, patch], check=True)
        subprocess.run([XDELTA, '-d', '-f', '-B', WIN, '-s', SRC_PKG, patch, chk], check=True)
        dm = md5(dst).upper()
        if md5(chk).upper() != dm:
            raise SystemExit('⛔ xdelta 되짚기 결과가 다르다: ' + f)
        total += os.path.getsize(patch)
        rows.append((f, dm, os.path.getsize(patch)))
        calls.append('call :MAKE "%s" %s' % (f, dm))
    os.remove(chk)
    shutil.copyfile(XDELTA, os.path.join(DIST, 'xdelta.exe'))
    table = '\n'.join('  %-30s %s' % (f, d) for f, d, _ in rows)
    write_cp949(os.path.join(DIST, 'readme.txt'),
                README.format(ver=VER, src=SRC_PKG_MD5.upper(), out=OUT_NAME, n=len(rows), table=table))
    write_cp949(os.path.join(DIST, '패치적용.bat'),
                BAT.format(ver=VER, src=SRC_PKG_MD5.upper(), out=OUT_NAME, win=WIN, calls='\n'.join(calls)))
    zp = shutil.make_archive(DIST, 'zip', os.path.dirname(DIST), PKG)
    print('✅ %s (파일 %d개, 패치 합계 %s B, 되짚기 일치)' % (DIST, len(rows), format(total, ',')))
    for f, d, n in rows:
        if n > 100000:
            print('   %-30s %s  xdelta %s B' % (f, d, format(n, ',')))
    print('   zip %s (%s B)' % (zp, format(os.path.getsize(zp), ',')))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
