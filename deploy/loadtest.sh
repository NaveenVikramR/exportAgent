#!/usr/bin/env bash
# Quick load test: N concurrent risk-agent runs (POST /api/emails/{id}/agent?force=true) on the demo
# emails that have an order. Most model responses come from the cache; prompts not cached yet are
# live calls, about $0.03-0.04 per test (counted against the $1 daily cap). Stays under the rate
# limit (10 per minute per IP) for N <= 8. Watch `docker stats` and `free -m` in a second SSH
# window while it runs (see DEPLOY.md). Restores the demo data at the end.
#   bash loadtest.sh            # 5 concurrent runs against https://$SITE_ADDRESS
#   bash loadtest.sh 3 http://localhost:8000
set -euo pipefail
cd "$(dirname "$0")"

N="${1:-5}"
if [[ -n "${2:-}" ]]; then
  BASE="$2"
else
  BASE="https://$(grep -E '^SITE_ADDRESS=' .env | cut -d= -f2)"
fi

ids=$(curl -sf "$BASE/api/emails" | python3 -c '
import json, sys
rows = [e for e in json.load(sys.stdin) if e.get("order_id")]
print(" ".join(str(e["id"]) for e in rows))')
read -ra ids <<< "$ids"
if [[ ${#ids[@]} -eq 0 ]]; then
  echo "No demo emails with an order found at $BASE" >&2
  exit 1
fi

echo "One run on its own first, for a baseline:"
curl -s -o /dev/null -w "  email ${ids[0]}: HTTP %{http_code} in %{time_total}s\n" -X POST "$BASE/api/emails/${ids[0]}/agent?force=true"

echo "Now $N at once:"
start=$(date +%s.%N)
for i in $(seq 0 $((N - 1))); do
  id=${ids[$((i % ${#ids[@]}))]}
  curl -s -o /dev/null -w "  email $id: HTTP %{http_code} in %{time_total}s\n" -X POST "$BASE/api/emails/$id/agent?force=true" &
done
wait
echo "  all $N done in $(python3 -c "print(round($(date +%s.%N) - $start, 1))")s"

echo
echo "Restoring the demo data (forced runs replaced the stored assessments):"
curl -s -o /dev/null -w "  POST /api/demo/reset: HTTP %{http_code}\n" -X POST "$BASE/api/demo/reset"

echo
echo "Health after the test:"
curl -s "$BASE/api/health"
echo
if command -v docker >/dev/null; then
  echo "Containers killed for memory (should all be false):"
  for c in $(docker compose ps -q); do
    docker inspect --format '  {{.Name}}: OOMKilled={{.State.OOMKilled}} restarts={{.RestartCount}}' "$c"
  done
fi
