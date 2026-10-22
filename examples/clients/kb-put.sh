#!/usr/bin/env bash
# Create or update a document in Outline from a Markdown file.
#
#   OUTLINE_URL=https://notes.example.com OUTLINE_API_KEY=ol_api_... \
#     kb-put.sh --collection <collectionId> --title "Plan 2026-10" < plan.md
#
# Idempotent: the document id is a UUIDv5 of (client name, title), so running
# twice updates instead of duplicating. From a machine that reaches Outline
# through Cloudflare instead of the tailnet, also export CF_ACCESS_CLIENT_ID and
# CF_ACCESS_CLIENT_SECRET (a Cloudflare Access service token).
set -euo pipefail

collection="" title="" client="${KB_CLIENT_NAME:-$(hostname)}" publish=true
while [ $# -gt 0 ]; do
  case "$1" in
    --collection) collection="$2"; shift 2 ;;
    --title) title="$2"; shift 2 ;;
    --client) client="$2"; shift 2 ;;
    --draft) publish=false; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "$collection" ] && [ -n "$title" ] || { echo "need --collection and --title" >&2; exit 2; }
: "${OUTLINE_URL:?}" "${OUTLINE_API_KEY:?}"

text=$(cat)
doc_id=$(python3 -c 'import sys,uuid; print(uuid.uuid5(uuid.NAMESPACE_URL, sys.argv[1]+"/"+sys.argv[2]))' "$client" "$title")

headers=(-H "Authorization: Bearer $OUTLINE_API_KEY" -H "Content-Type: application/json")
if [ -n "${CF_ACCESS_CLIENT_ID:-}" ]; then
  headers+=(-H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET")
fi

api() { curl -fsS "${headers[@]}" -X POST "$OUTLINE_URL/api/$1" --data-binary @-; }

payload=$(python3 -c 'import json,sys; print(json.dumps({"id":sys.argv[1],"title":sys.argv[2],"collectionId":sys.argv[3],"publish":sys.argv[4]=="true","text":sys.stdin.read()}))' \
  "$doc_id" "$title" "$collection" "$publish" <<<"$text")

if printf '{"id":"%s"}' "$doc_id" | api documents.info >/dev/null 2>&1; then
  printf '%s' "$payload" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps({"id":d["id"],"title":d["title"],"text":d["text"],"publish":d["publish"]}))' | api documents.update >/dev/null
  echo "updated $doc_id"
else
  printf '%s' "$payload" | api documents.create >/dev/null
  echo "created $doc_id"
fi
