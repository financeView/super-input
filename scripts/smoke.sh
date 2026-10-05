#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${SUPER_INPUT_BASE_URL:-http://127.0.0.1:47625}"
TOKEN_FILE="${SUPER_INPUT_TOKEN_FILE:-${HOME}/Library/Application Support/super-input/token}"
WAIT_ATTEMPTS="${SUPER_INPUT_SMOKE_ATTEMPTS:-60}"

[[ -r "${TOKEN_FILE}" ]] || { echo "token file not readable: ${TOKEN_FILE}" >&2; exit 1; }
TOKEN="$(<"${TOKEN_FILE}")"
[[ -n "${TOKEN}" ]] || { echo "token file is empty" >&2; exit 1; }

umask 077
CURL_CONFIG="$(mktemp)"
trap 'rm -f "${CURL_CONFIG}"' EXIT
printf 'header = "X-SuperInput-Protocol: 1"\nheader = "Authorization: Bearer %s"\n' \
  "${TOKEN}" >"${CURL_CONFIG}"
unset TOKEN

READY=""
for ((attempt = 1; attempt <= WAIT_ATTEMPTS; attempt++)); do
  READY="$(curl --silent --show-error --fail --config "${CURL_CONFIG}" "${BASE_URL}/health" 2>/dev/null || true)"
  if python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin).get("ready") is True else 1)' <<<"${READY}" 2>/dev/null; then
    break
  fi
  sleep 5
done
python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin).get("ready") is True else 1)' <<<"${READY}" 2>/dev/null || {
  echo "service did not become ready after $((WAIT_ATTEMPTS * 5)) seconds" >&2
  exit 1
}

BODY='{"session_id":"smoke","request_id":1,"keys":"fenjinghenmei","preedit":"","candidates":["分静很没","风景很美","风景很每"],"context":"登高望远","trust":"T0"}'
RESPONSE="$(curl --silent --show-error --fail --config "${CURL_CONFIG}" \
  -H 'Content-Type: application/json' --data "${BODY}" "${BASE_URL}/rerank")"
python3 -c 'import json,sys; result=json.load(sys.stdin); assert result.get("mode") in {"L1", "L2", "fastpath"}; assert isinstance(result.get("order"), list)' <<<"${RESPONSE}"
echo "SMOKE_OK"
