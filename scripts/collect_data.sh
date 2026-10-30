#!/usr/bin/env bash
# 공개 신용평가 데이터셋 수집 스크립트 (재현용)
# - Kaggle/UCI 원본은 로그인·약관 동의가 필요해, 동일 파일을 올려둔 GitHub 미러에서 받는다.
# - 미러 2곳의 SHA-256이 같은지, 그리고 docs/DATA_SOURCES.md에 기록한 해시와 같은지 대조한다.
# 원 출처: Kaggle https://www.kaggle.com/c/GiveMeSomeCredit
#          LendingClub LoanStats3a (2007-2011)
#          UCI https://archive.ics.uci.edu/dataset/144/statlog+german+credit+data
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RAW="$ROOT/data/raw"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$RAW/gmsc" "$RAW/lending_club" "$RAW/german_credit"

fetch() {  # fetch <owner/repo> <path-in-repo> <dest>
  local repo="$1" path="$2" dest="$3" dir="$TMP/$(echo "$1" | tr / _)"
  [ -d "$dir" ] || git clone -q --depth 1 --filter=blob:none --no-checkout "https://github.com/$repo.git" "$dir"
  git -C "$dir" checkout -q HEAD -- "$path"
  cp "$dir/$path" "$dest"
}

check_same() {  # check_same <fileA> <fileB>
  local a b; a=$(sha256sum "$1" | cut -d' ' -f1); b=$(sha256sum "$2" | cut -d' ' -f1)
  [ "$a" = "$b" ] && echo "  OK  미러 해시 일치 ${a:0:16}…" || { echo "  !!  해시 불일치: $1 vs $2"; exit 1; }
}

check_expected() {  # check_expected <file> <sha256>  (2026-10-30 수집 시점 기록값)
  local a; a=$(sha256sum "$1" | cut -d' ' -f1)
  [ "$a" = "$2" ] && echo "  OK  기록된 해시와 일치 ($(basename "$1"))" || { echo "  !!  기록된 해시와 다름: $1"; exit 1; }
}

echo "[1/3] Give Me Some Credit (Kaggle 2011)"
fetch jwu424/GiveMeSomeCredit       cs-training.csv  "$RAW/gmsc/cs-training.csv"
fetch jwu424/GiveMeSomeCredit       cs-test.csv      "$RAW/gmsc/cs-test.csv"
fetch wang-weishuai/GiveMeSomeCredit cs-training.csv "$TMP/gmsc_mirror2.csv"
check_same "$RAW/gmsc/cs-training.csv" "$TMP/gmsc_mirror2.csv"
check_expected "$RAW/gmsc/cs-training.csv" 1bd46da486a5708c58c7b01a034fae2a13b327f6f7b62ea7ba4fe3b5824b24ac

echo "[2/3] Lending Club 2007-2011 (LoanStats3a)"
fetch jsabrams/default_risk_prediction  LoanStats3a.csv.zip          "$RAW/lending_club/LoanStats3a.csv.zip"
fetch jatinit056/banking-loan-analytics data/raw/LoanStats3a.csv.zip "$TMP/lc_mirror2.zip"
check_same "$RAW/lending_club/LoanStats3a.csv.zip" "$TMP/lc_mirror2.zip"
check_expected "$RAW/lending_club/LoanStats3a.csv.zip" 6e53451aca45fdc3265d01ea99e1543e3730c80a53b68cf098ef3db06ee3bc32
(cd "$RAW/lending_club" && unzip -o -q LoanStats3a.csv.zip)

echo "[3/3] German Credit (UCI Statlog)"
fetch rajarshighoshal/german-credit-data german.data "$RAW/german_credit/german.data"
check_expected "$RAW/german_credit/german.data" b21f3d81db8071257d5ff1deaeba1fd4303b62712e6fcc9715c7a86202cb5871

echo "완료 → $RAW"
