#!/bin/sh
# test-usage.sh — offline suite for usage.sh. Fakes curl/security/uname; never touches the network, keychain, or real HOME.
set -u

SCRIPT=$(cd "$(dirname "$0")" && pwd)/usage.sh
TOKEN='tok-FAKE-1234567890'
URL='https://api.anthropic.com/api/oauth/usage'
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin" "$T/c" "$T/h" "$T/out"
REAL_PATH=$PATH

cat > "$T/bin/curl" <<FAKE
#!/bin/sh
echo "curl \$*" >> "\${FAKE_CURL_LOG:-/dev/null}"
for a in "\$@"; do
  case \$a in *$TOKEN*) echo "fake curl: token in argv" >&2; exit 99 ;; esac
done
stdin=\$(cat)
case \$stdin in
  *'header = "Authorization: Bearer $TOKEN"'*) ;;
  *) echo "fake curl: bad stdin config" >&2; exit 98 ;;
esac
case " \$* " in
  *" $URL "*) ;;
  *) echo "fake curl: bad url" >&2; exit 97 ;;
esac
case "\$*" in
  *'anthropic-beta: oauth-2025-04-20'*) ;;
  *) echo "fake curl: missing beta header" >&2; exit 97 ;;
esac
if [ "\${FAKE_CURL_FAIL:-0}" = 1 ]; then
  echo "curl: (6) Could not resolve host: api.anthropic.com" >&2
  exit 6
fi
out=
while [ \$# -gt 0 ]; do
  if [ "\$1" = -o ]; then out=\$2; fi
  shift
done
cp "\$FAKE_CURL_BODY" "\$out"
printf '%s' "\$FAKE_CURL_STATUS"
FAKE
cat > "$T/bin/security" <<'FAKE'
#!/bin/sh
if [ -n "${FAKE_SECURITY_OUT:-}" ]; then printf '%s' "$FAKE_SECURITY_OUT"; exit 0; fi
exit 44
FAKE
cat > "$T/bin/uname" <<'FAKE'
#!/bin/sh
echo "${FAKE_UNAME:-Linux}"
FAKE
chmod +x "$T/bin/curl" "$T/bin/security" "$T/bin/uname"

PATH="$T/bin:$PATH"
export PATH
unset XDG_CACHE_HOME CLAUDE_USAGE_CACHE_DIR
for c in security curl; do
  case $(command -v "$c") in "$T"/bin/*) ;; *) echo "abort: $c does not resolve to the fake" >&2; exit 1 ;; esac
done
FAKE_CURL_LOG="$T/curl.log"
export FAKE_CURL_LOG

pass=0
fail=0
nl='
'

# leak_check <outfile> <errfile> <cachedir>
leak_check() {
  if grep -q "$TOKEN" "$1" "$2" 2>/dev/null; then echo "token leaked to output"; return 1; fi
  if [ -d "$3" ] && grep -rq "$TOKEN" "$3" 2>/dev/null; then echo "token leaked to cache dir"; return 1; fi
  return 0
}

# run_case <name> <expected_exit> [args...]; per-case env via CASE_ENV (space separated assignments)
run_case() {
  name=$1 want=$2
  shift 2
  CDIR="$T/c/$name"
  CHOME="$T/h/$name"
  OUT="$T/out/$name.out"
  ERR="$T/out/$name.err"
  : > "$FAKE_CURL_LOG"
  # shellcheck disable=SC2086
  env HOME="$CHOME" CLAUDE_USAGE_CACHE_DIR="$CDIR" ${CASE_ENV:-} sh "$SCRIPT" "$@" > "$OUT" 2> "$ERR"
  got=$?
  CASE_FAIL=
  [ "$got" -eq "$want" ] || CASE_FAIL="exit $got, want $want"
  if [ -z "$CASE_FAIL" ]; then CASE_FAIL=$(leak_check "$OUT" "$ERR" "$CDIR") || true; fi
  CASE_NAME=$name
}

# finish: records result; extra checks set CASE_FAIL before calling
finish() {
  if [ -z "$CASE_FAIL" ]; then pass=$((pass + 1)); echo "PASS $CASE_NAME"
  else fail=$((fail + 1)); echo "FAIL $CASE_NAME: $CASE_FAIL"; fi
}

fail_if() { [ -n "$CASE_FAIL" ] || CASE_FAIL=$1; }
out_starts() { case $(cat "$OUT") in "$1"*) ;; *) fail_if "stdout does not start with '$1': $(cat "$OUT")" ;; esac; }
out_is() { [ "$(cat "$OUT")" = "$1" ] || fail_if "stdout is '$(cat "$OUT")', want '$1'"; }
out_empty() { [ ! -s "$OUT" ] || fail_if "stdout not empty"; }
out_lacks() { if grep -q -- "$1" "$OUT"; then fail_if "stdout contains '$1'"; fi; }
out_has() { grep -q -- "$1" "$OUT" || fail_if "stdout lacks '$1': $(cat "$OUT")"; }
err_has() { grep -q -- "$1" "$ERR" || fail_if "stderr lacks '$1': $(cat "$ERR")"; }
err_lacks() { if grep -q -- "$1" "$ERR"; then fail_if "stderr contains '$1'"; fi; }
err_starts() { case $(cat "$ERR") in "$1"*) ;; *) fail_if "stderr does not start with '$1'" ;; esac; }
curl_calls() { [ "$(wc -l < "$FAKE_CURL_LOG" | tr -d ' ')" = "$1" ] || fail_if "curl calls $(wc -l < "$FAKE_CURL_LOG" | tr -d ' '), want $1"; }
mode_is() { [ "$(ls -ld "$1" 2>/dev/null | cut -c1-10)" = "$2" ] || fail_if "mode of $1 is $(ls -ld "$1" 2>/dev/null | cut -c1-10), want $2"; }

# ---- Task 1: CLI ----
CASE_ENV= ; run_case help 0 -h; out_starts "usage:"; finish
run_case bad-arg 2 --nope; out_empty; err_starts "usage:"; finish
run_case bad-arg-extra 2 --json extra; finish

CASE_NAME=fake-rejects-argv-token; CASE_FAIL=
printf 'header = "Authorization: Bearer %s"\n' "$TOKEN" | curl -sS "$TOKEN" >/dev/null 2>&1
[ $? -eq 99 ] || CASE_FAIL="fake curl accepted token in argv"
finish

CASE_NAME=missing-jq; CASE_FAIL=
mkdir -p "$T/nojq" "$T/h/missing-jq"
cp "$T/bin/curl" "$T/nojq/curl"
HOME="$T/h/missing-jq" CLAUDE_USAGE_CACHE_DIR="$T/c/missing-jq" PATH="$T/nojq" /bin/sh "$SCRIPT" > "$T/out/mj.out" 2> "$T/out/mj.err"
got=$?
[ "$got" -eq 3 ] || CASE_FAIL="exit $got, want 3"
grep -q jq "$T/out/mj.err" || fail_if "stderr lacks jq"
leak_check "$T/out/mj.out" "$T/out/mj.err" "$T/c/missing-jq" >/dev/null || fail_if "leak"
finish

# ---- Task 2: warm cache + formatting ----
# warm <name> <jq-expr producing the body>; pre-creates the cache dir and usage.json
warm() {
  mkdir -p "$T/h/$1"; mkdir -m 700 "$T/c/$1"
  jq -n "$2" > "$T/c/$1/usage.json"
}
R2H='(now+8030|todate)'
R4D='(now+4*86400+6*3600+1800|todate)'
FULL="{five_hour:{utilization:51.0,resets_at:$R2H},seven_day:{utilization:27,resets_at:$R4D},seven_day_opus:{utilization:12,resets_at:null},seven_day_sonnet:{utilization:3,resets_at:null}}"

warm warm-full "$FULL"
run_case warm-full 0
out_is "5h 51% (resets in 2h13m) · 7d 27% (resets in 4d6h) · opus 12% · sonnet 3%"; curl_calls 0; finish

warm warm-null-models "{five_hour:{utilization:51,resets_at:$R2H},seven_day:{utilization:27,resets_at:$R4D},seven_day_opus:null,seven_day_sonnet:null}"
run_case warm-null-models 0; out_lacks opus; out_lacks sonnet; out_has '7d 27%'; curl_calls 0; finish

warm warm-null-5h "{five_hour:null,seven_day:{utilization:27,resets_at:$R4D}}"
run_case warm-null-5h 0; out_starts "5h n/a · 7d"; curl_calls 0; finish

warm warm-float "{five_hour:{utilization:50.6,resets_at:null},seven_day:null}"
run_case warm-float 0; out_starts "5h 51%"; curl_calls 0; finish

warm warm-frac-offset "{five_hour:{utilization:51,resets_at:(now+8030|todate|sub(\"Z\$\";\".123456+00:00\"))},seven_day:null}"
run_case warm-frac-offset 0; out_has 'resets in 2h13m'; curl_calls 0; finish

warm warm-nonutc-offset "{five_hour:{utilization:51,resets_at:(now+8030+18000|todate|sub(\"Z\$\";\"+05:00\"))},seven_day:null}"
run_case warm-nonutc-offset 0; out_has 'resets in 2h13m'; curl_calls 0; finish

warm warm-bad-reset '{five_hour:{utilization:51,resets_at:"soon"},seven_day:null}'
run_case warm-bad-reset 0; out_has '(resets soon)'; finish

warm warm-null-reset '{five_hour:{utilization:51,resets_at:null},seven_day:null}'
run_case warm-null-reset 0; out_is "5h 51% · 7d n/a"; finish

warm warm-nonnumeric '{five_hour:{utilization:"x",resets_at:null},seven_day:null}'
run_case warm-nonnumeric 0; out_starts "5h ?%"; finish

warm warm-json "$FULL"
run_case warm-json 0 --json; cmp -s "$OUT" "$T/c/warm-json/usage.json" || fail_if "json output differs from fixture"; curl_calls 0; finish

warm warm-bucket-string '{five_hour:"x",seven_day:null}'
run_case warm-bucket-string 0; out_starts "5h n/a"; finish

mkdir -p "$T/h/unsafe-dir"; mkdir -m 700 "$T/c/unsafe-dir"; chmod 770 "$T/c/unsafe-dir"
run_case unsafe-dir 3; err_has "$T/c/unsafe-dir"; mode_is "$T/c/unsafe-dir" drwxrwx---; finish

echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
