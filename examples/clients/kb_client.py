#!/usr/bin/env python3
"""Tiny Outline API client for agents and scripts. Standard library only.

    export OUTLINE_URL=https://notes.example.com OUTLINE_API_KEY=ol_api_...
    kb_client.py search "quarterly plan"
    kb_client.py put --collection <id> --title "Plan 2026-10" < plan.md
    kb_client.py get <documentId>

Idempotent writes: the document id is a UUIDv5 of (client name, title), so a
re-run updates the same document. Behind Cloudflare (no tailnet), also set
CF_ACCESS_CLIENT_ID / CF_ACCESS_CLIENT_SECRET (an Access service token).
"""
import argparse
import json
import os
import socket
import sys
import urllib.error
import urllib.request
import uuid


class Outline:
    def __init__(self):
        self.url = os.environ["OUTLINE_URL"].rstrip("/")
        self.headers = {
            "Authorization": "Bearer " + os.environ["OUTLINE_API_KEY"],
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if os.environ.get("CF_ACCESS_CLIENT_ID"):
            self.headers["CF-Access-Client-Id"] = os.environ["CF_ACCESS_CLIENT_ID"]
            self.headers["CF-Access-Client-Secret"] = os.environ["CF_ACCESS_CLIENT_SECRET"]

    def call(self, method, **params):
        request = urllib.request.Request(f"{self.url}/api/{method}", data=json.dumps(params).encode(),
                                         headers=self.headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)["data"]
        except urllib.error.HTTPError as error:
            body = error.read().decode(errors="replace")
            if error.code == 404:
                return None
            raise SystemExit(f"{method}: HTTP {error.code} {body[:300]}")

    def put(self, collection_id, title, text, client, publish=True):
        doc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{client}/{title}"))
        if self.call("documents.info", id=doc_id):
            self.call("documents.update", id=doc_id, title=title, text=text, publish=publish)
            return "updated", doc_id
        self.call("documents.create", id=doc_id, title=title, text=text,
                  collectionId=collection_id, publish=publish)
        return "created", doc_id


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    put = sub.add_parser("put", help="create or update a document from stdin (Markdown)")
    put.add_argument("--collection", required=True)
    put.add_argument("--title", required=True)
    put.add_argument("--client", default=os.environ.get("KB_CLIENT_NAME", socket.gethostname()))
    put.add_argument("--draft", action="store_true")
    search = sub.add_parser("search", help="full-text search")
    search.add_argument("query")
    get = sub.add_parser("get", help="print a document as Markdown")
    get.add_argument("id")
    sub.add_parser("collections", help="list collections")
    args = parser.parse_args()

    api = Outline()
    if args.command == "put":
        action, doc_id = api.put(args.collection, args.title, sys.stdin.read(), args.client, not args.draft)
        print(action, doc_id)
    elif args.command == "search":
        for hit in api.call("documents.search", query=args.query, limit=10) or []:
            doc = hit["document"]
            print(f"{doc['id']}  {doc['title']}")
    elif args.command == "get":
        print(api.call("documents.info", id=args.id)["text"])
    elif args.command == "collections":
        for collection in api.call("collections.list", limit=100) or []:
            print(f"{collection['id']}  {collection['name']}")


if __name__ == "__main__":
    main()
