"""真实数据评估：今日头条中文新闻数据集（公开，约 38 万条，15 类）。

流程：每类抽样 N 条 -> 真实入库流水线（真实 bge-small-zh 向量）-> 三种检索对比。
查询构造（避免与标题同词，考察语义召回）：取该条新闻的关键词中"不出现在标题里"的 2 个词作为查询，
目标=该文档本身。指标：Recall@5 / Recall@10 / MRR；另报类别精确率@5（Top5 中与目标同类别的占比）。
用法：EMBEDDING_MODE=local venv\Scripts\python.exe scripts\eval_real_data.py [每类条数]
"""
import os, sys, random, tempfile, time, json
os.environ.setdefault("EMBEDDING_MODE", "local")
os.environ["LLM_PROVIDER"] = "mock"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
from app import db, pipeline, hybrid, vectorstore, embedding

N = int(sys.argv[1]) if len(sys.argv) > 1 else 100
NQ = 300
DATA = os.path.join(os.path.dirname(__file__), "..", "ext_data", "toutiao_cat_data.txt")
random.seed(42)
by_cat = {}
with open(DATA, encoding="utf-8") as f:
    for line in f:
        p = line.rstrip("\n").split("_!_")
        if len(p) < 5 or len(p[3]) < 12 or not p[4].strip():
            continue
        by_cat.setdefault(p[2], []).append((p[3], p[4].split(",")))
docs = []
for cat, rows in sorted(by_cat.items()):
    for t, kws in random.sample(rows, min(N, len(rows))):
        docs.append((cat, t, kws))
print(f"类别 {len(by_cat)}，抽样入库 {len(docs)} 条")

tmp = tempfile.mkdtemp()
conn = db.connect(os.path.join(tmp, "eval.db"))
emb = embedding.get_embedder()
llm = pipeline.MockLLM()
ids = []
t0 = time.time()
for cat, t, kws in docs:
    ids.append(db.add_document(conn, t, t, "paste"))
conn.commit()
for d in ids:
    pipeline.process_document(conn, d, llm, embedder=emb)
    conn.commit()
ing = time.time() - t0
print(f"入库+向量化耗时 {ing:.1f}s（{ing/len(ids)*1000:.0f} ms/篇）")

cat_of = {d: docs[i][0] for i, d in enumerate(ids)}
queries = []
for i, (cat, t, kws) in enumerate(docs):
    extra = [k for k in kws if k and k not in t]
    if len(extra) >= 2:
        queries.append((" ".join(extra[:2]), ids[i]))
random.shuffle(queries)
queries = queries[:NQ]
print(f"评估查询 {len(queries)} 条（关键词不在标题中）")

class NoVec(embedding.EmbeddingProvider):
    name = "none"
    def embed(self, texts): raise RuntimeError("off")

def rank_kw(q): return [r["id"] for r in hybrid.hybrid_search(conn, q, limit=10, embedder=NoVec())]
def rank_hy(q): return [r["id"] for r in hybrid.hybrid_search(conn, q, limit=10, embedder=emb)]
def rank_sem(q):
    v = emb.embed([q])[0]
    return [h["doc_id"] for h in vectorstore.search(conn, v, emb.name, 10)]

def evaluate(fn):
    r5 = r10 = mrr = prec = 0.0; lat = []
    for q, tgt in queries:
        s = time.time(); res = fn(q); lat.append(time.time() - s)
        if tgt in res:
            k = res.index(tgt) + 1
            r10 += 1; r5 += k <= 5; mrr += 1 / k
        top5 = res[:5]
        if top5: prec += sum(cat_of[x] == cat_of[tgt] for x in top5) / len(top5)
    n = len(queries)
    return r5 / n, r10 / n, mrr / n, prec / n, float(np.mean(lat)) * 1000

rows = [("纯关键词(FTS5)", rank_kw), ("纯语义(bge-small-zh)", rank_sem), ("混合 RRF", rank_hy)]
out = ["| 方法 | Recall@5 | Recall@10 | MRR | 类别精确率@5 | 平均延迟(ms) |", "|---|---|---|---|---|---|"]
for name, fn in rows:
    a = evaluate(fn)
    out.append(f"| {name} | {a[0]:.3f} | {a[1]:.3f} | {a[2]:.3f} | {a[3]:.3f} | {a[4]:.0f} |")
print("\n".join(out))
with open(os.path.join(os.path.dirname(__file__), "..", "eval_real_data_result.md"), "w", encoding="utf-8") as f:
    f.write(f"# 真实数据评估（今日头条新闻，{len(docs)} 篇，{len(queries)} 条查询）\n\n" + "\n".join(out) + "\n")
