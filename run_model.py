#!/usr/bin/env python3
"""Collect one fresh PromQL answer, save it, then grade it with the demo fixtures."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from demo import CASES


def collect(base_url, model, prompt):
    headers = {"Content-Type": "application/json"}
    if token := os.environ.get("LLM_API_KEY"):
        headers["Authorization"] = "Bearer " + token
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    request = Request(base_url.rstrip("/") + "/chat/completions",
                      json.dumps(payload).encode(), headers)
    with urlopen(request, timeout=90) as response:
        return json.load(response)


def extract_query(answer):
    query = answer.strip()
    lines = query.splitlines()
    if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].strip() == "```":
        query = "\n".join(lines[1:-1]).strip()
    if not query:
        raise ValueError("The model returned no query.")
    return query


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("--model", required=True, help="Model ID accepted by the provider")
    parser.add_argument("--base-url", required=True, help="Chat Completions base URL including /v1")
    parser.add_argument("--out", required=True, type=Path, help="New JSON file for this trial")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Output already exists. Use a new filename for each trial.")
    if not args.out.parent.is_dir():
        parser.error("Output directory does not exist.")
    prompt = CASES[args.case]["prompt"] + " Return only the PromQL expression."
    reply = collect(args.base_url, args.model, prompt)
    answer = reply["choices"][0]["message"]["content"]
    if not isinstance(answer, str):
        raise ValueError("Expected a text answer from the provider.")
    with args.out.open("x", encoding="utf-8") as output:
        json.dump({"case": args.case, "requested_model": args.model, "model": reply.get("model"),
                   "created": reply.get("created"), "prompt": prompt, "answer": answer,
                   "usage": reply.get("usage")}, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(f"Saved the raw answer in {args.out}", flush=True)
    query = extract_query(answer)
    print(query, flush=True)
    return subprocess.run([sys.executable, str(Path(__file__).with_name("demo.py")),
                           "--case", args.case, "--query", query], check=False).returncode


if __name__ == "__main__":
    try:
        sys.exit(main())
    except HTTPError as error:
        sys.exit(f"Provider returned HTTP {error.code}: {error.reason}")
    except (URLError, OSError, ValueError, KeyError, IndexError, TypeError) as error:
        sys.exit(f"Could not complete the trial: {error}")
