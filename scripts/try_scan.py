from contam.data.benchmarks import load_benchmark
from contam.data.corpus import stream_documents
from contam.exact import ExactIndex, ScanStats
from contam.items import View

items = load_benchmark("gsm8k") + load_benchmark("arc_challenge")
index = ExactIndex.build(items, view=View.QUESTION, n=8)
print("indexed", index.indexed_items, "skipped", len(index.skipped))
stats = ScanStats()
for hit in index.scan_corpus(stream_documents(max_docs=2000), stats=stats):
    print(hit.level.name, hit.item_id, hit.doc_id, round(hit.containment, 2))
print(stats)
