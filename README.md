# 반조-투이 한글 패치

N64 `Banjo-Tooie (USA).z64` 한글 패치.

## 내려받기

- 최신 **v0.9** — 릴리즈의 `BanjoTooie_KR_v0.9.zip`(xdelta + 패치적용.bat + readme)
- 원본 MD5 `40E98FAA24AC3EBE1D25CB5E5DDF49E4` → 패치 MD5 `E82085394F42BD0217BEE2328861748B` (64MB)
- **확장팩(메모리 8MB) 필수.**

## 작업 저장소

- 인계·빌드 절차: **`docs/00_이어하기.md`** 부터.
- 원문 TSV: `work/text/bt_text.tsv` (8,262행) · 다듬은 번역 `work/text/fixed/` (교정 도구 `tools/bt_fix.py`, 줄 교정 `work/text/bt_fixes.tsv`, 통일 `work/text/bt_unify.tsv`, 변경 목록 `work/text/교정_변경목록.tsv`)
- 배포 묶음: `python tools/make_dist.py`
- 빌드: `python tools/btbuild.py <번역 폴더> work/BT_KR.z64` — 규칙 검사 `tools/btrules.py`(오류면 빌드 안 함)
- ROM·빌드 결과물은 들어 있지 않다. 확장팩(메모리 8MB) 필수.
