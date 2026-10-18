"""公开数据集评估：jinaai/longcontext-cmrc2018-zh（1149 篇中文长文本语料 + 1149 条自然语言问题，
每条问题有唯一标准答案文档，qrels 来自 C-MTEB 同源）。
与头条评估不同：查询是真实的自然语言问句，更贴近"用自然语言找回文档"的目标场景。
流程：全部语料真实入库（真实 bge-small-zh 向量）-> 抽样 NQ 条问题 -> 纯关键词 / 纯语义 / 混合 RRF 三路对比。
指标：Recall@1 / Recall@5 / Recall@10 / MRR / 平均延迟。
用法：EMBEDDING_MODE=local venv\\Scripts\\python.exe scripts\\eval_cmrc_long.py [查询条数]
"""
import os, sys, random, tempfile, time
os.environ.setdefault("EMBEDDING_MODE", "local")
os.environ["LLM_PROVIDER"] = "mock"
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
import numpy as np
import pandas as pd
from app import db, pipeline, hybrid, vectorstore, embedding

NQ = int(sys.argv[1]) if len(sys.argv) > 1 else 300
D = os.path.join(ROOT, "ext_data")
corpus = pd.read_parquet(os.path.join(D, "cmrc_long", "corpus-00000-of-00001.parquet"))
queries = pd.read_parquet(os.path.join(D, "cmrc_long", "queries-00000-of-00001.parquet"))
qrels = pd.read_parquet(os.path.join(D, "cmrc_long_qrels", "dev.parquet"))
gold = dict(zip(qrels["qid"], qrels["pid"]))
print(f"语料 {len(corpus)} 篇，查询 {len(queries)} 条")

tmp = tempfile.mkdtemp()
conn = db.connect(os.path.join(tmp, "eval.db"))
emb = embedding.get_embedder()
llm = pipeline.MockLLM()
pid2doc = {}
t0 = time.time()
for pid, text in zip(corpus["id"], corpus["text"]):
    title = text.strip().replace("\n", " ")[:20]
    pid2doc[pid] = db.add_document(conn, title, text, "paste")
conn.commit()
for d in pid2doc.values():
    pipeline.process_document(conn, d, llm, embedder=emb)
    conn.commit()
ing = time.time() - t0
print(f"入库+向量化耗时 {ing:.1f}s（{ing/len(pid2doc)*1000:.0f} ms/篇）")

random.seed(42)
qs = [(t, pid2doc[gold[q]]) for q, t in zip(queries["id"], queries["text"]) if q in gold and gold[q] in pid2doc]
random.shuffle(qs)
qs = qs[:NQ]


class NoVec(embedding.EmbeddingProvider):
    name = "none"
    def embed(self, texts): raise RuntimeError("off")


def rank_kw(q): return [r["id"] for r in hybrid.hybrid_search(conn, q, limit=10, embedder=NoVec())]
def rank_hy(q): return [r["id"] for r in hybrid.hybrid_search(conn, q, limit=10, embedder=emb)]
def rank_sem(q):
    v = emb.embed([q])[0]
    return [h["doc_id"] for h in vectorstore.search(conn, v, emb.name, 10)]


def evaluate(fn):
    r1 = r5 = r10 = mrr = 0.0; lat = []
    for q, tgt in qs:
        s = time.time(); res = fn(q); lat.append(time.time() - s)
        if tgt in res:
            k = res.index(tgt) + 1
            r10 += 1; r5 += k <= 5; r1 += k == 1; mrr += 1 / k
    n = len(qs)
    return r1 / n, r5 / n, r10 / n, mrr / n, float(np.mean(lat)) * 1000


out = ["| 方法 | Recall@1 | Recall@5 | Recall@10 | MRR | 平均延迟(ms) |", "|---|---|---|---|---|---|"]
for name, fn in [("纯关键词(FTS5)", rank_kw), ("纯语义(bge-small-zh)", rank_sem), ("混合 RRF", rank_hy)]:
    a = evaluate(fn)
    out.append(f"| {name} | {a[0]:.3f} | {a[1]:.3f} | {a[2]:.3f} | {a[3]:.3f} | {a[4]:.0f} |")
print("\n".join(out))
with open(os.path.join(ROOT, "eval_cmrc_long_result.md"), "w", encoding="utf-8") as f:
    f.write(f"# 公开数据集评估：longcontext-cmrc2018-zh（{len(corpus)} 篇语料，{len(qs)} 条自然语言问题）\n\n"
            + "\n".join(out) + "\n")
