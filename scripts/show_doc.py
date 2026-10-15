"""Print corpus documents by id, so you can read what a hit really is.

    python scripts\\show_doc.py '<urn:uuid:AAAA>' '<urn:uuid:BBBB>' ^
        --item mmlu:test:306 --find "required for any solar eclipse"

Streams the corpus until every id is found (a few minutes for a million documents). The page
URL is printed for your own inspection only; do not commit page text or URLs.
"""

from __future__ import annotations

import argparse
import importlib
import re

from contam.data.benchmarks import load_benchmark


def context(text: str, phrase: str, width: int = 400) -> str:
    words = [re.escape(word) for word in phrase.split()]
    match = re.search(r"\W+".join(words), text, flags=re.IGNORECASE)
    if match is None:
        return f"(phrase not found verbatim: {phrase!r})"
    start = max(0, match.start() - width)
    return text[start : match.end() + width].replace("\n", " | ")


def main() -> None:
    parser = argparse.ArgumentParser(description="Show corpus documents by id.")
    parser.add_argument("doc_ids", nargs="+")
    parser.add_argument("--path", default="HuggingFaceFW/fineweb-edu")
    parser.add_argument("--config", default="sample-10BT")
    parser.add_argument("--max-docs", type=int, default=1_100_000)
    parser.add_argument("--item", action="append", default=[], help="benchmark item id to print")
    parser.add_argument("--find", action="append", default=[], help="phrase to show in context")
    parser.add_argument("--chars", type=int, default=2500)
    args = parser.parse_args()

    for item_id in args.item:
        name = item_id.split(":", 1)[0]
        item = next(i for i in load_benchmark(name) if i.item_id == item_id)
        print(f"BENCHMARK ITEM {item_id}:\n{item.text()}\n")

    datasets = importlib.import_module("datasets")
    stream = datasets.load_dataset(args.path, args.config, split="train", streaming=True)
    remaining = set(args.doc_ids)
    for seen, row in enumerate(stream):
        if seen >= args.max_docs or not remaining:
            break
        if seen and seen % 100_000 == 0:
            print(f"  ...{seen:,} documents streamed, {len(remaining)} still to find")
        if row["id"] not in remaining:
            continue
        remaining.discard(row["id"])
        text = row["text"]
        print("=" * 78)
        print(f"DOCUMENT {row['id']}   url: {row.get('url', '?')}   {len(text):,} characters")
        for phrase in args.find:
            print(f"\nCONTEXT for {phrase!r}:\n{context(text, phrase)}")
        print(f"\nSTART OF PAGE:\n{text[: args.chars]}")
    for missing in sorted(remaining):
        print(f"not found in the first {args.max_docs:,} documents: {missing}")


if __name__ == "__main__":
    main()
