# 반조-투이 한글 패치

N64 `Banjo-Tooie (USA).z64` · 엑스박스 360 XBLA(Xenia) 한글 패치.

## 내려받기

- 최신 **v0.9** — 릴리즈의 `BanjoTooie_KR_v0.9.zip`(xdelta + 패치적용.bat + readme)
- 원본 MD5 `40E98FAA24AC3EBE1D25CB5E5DDF49E4` → 패치 MD5 `A4F08294D7F6F1717A2C78BFA8BDD456` (64MB)
- **확장팩(메모리 8MB) 필수.**

### 엑스박스 360 XBLA (Xenia)

- 최신 **v0.9** — 릴리즈 `x360-v0.9` 의 `BanjoTooie_X360_KR_v0.9.zip`
- 압축을 푼 폴더에 원본 LIVE 패키지 파일(타이틀 ID 58410955, MD5 `C26DC55C00CCEA88446A85E81D21B0E4`)을 넣고 「패치적용.bat」 실행 → `Banjo Tooie KR` 폴더 생성
- Xenia 언어를 일본어로(`user_language = 2`) 바꾼 뒤 `Banjo Tooie KR\default.xex` 실행
- **패키지판**: 같은 릴리즈의 `BanjoTooie_X360_KR_v0.9_package.zip` — 원본 LIVE 패키지에 바로 적용해 한글 LIVE 패키지 파일 `Banjo Tooie [KR]` 하나를 만듦(패치md5 `663A5866914AD816D9FE9290098B75B2`) → Xenia 에서 그 파일을 엶. 내용은 폴더판과 같음(`tools/make_dist_x360_pkg.py`, 패키지 다시 쌓기 `tools/stfs.py`)
- 빌드: `python tools/x360build.py work/text/fixed <출력 폴더> --write` → 배포 `python tools/make_dist_x360.py`

## 작업 저장소

- 인계·빌드 절차: **`docs/00_이어하기.md`** 부터.
- 원문 TSV: `work/text/bt_text.tsv` (8,262행) · 다듬은 번역 `work/text/fixed/` (교정 도구 `tools/bt_fix.py`, 줄 교정 `work/text/bt_fixes.tsv`, 통일 `work/text/bt_unify.tsv`, 변경 목록 `work/text/교정_변경목록.tsv`)
- 배포 묶음: `python tools/make_dist.py`
- 빌드: `python tools/btbuild.py <번역 폴더> work/BT_KR.z64` — 규칙 검사 `tools/btrules.py`(오류면 빌드 안 함)
- ROM·빌드 결과물은 들어 있지 않다. 확장팩(메모리 8MB) 필수.
