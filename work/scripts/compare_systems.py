"""系统对比实验：本系统（jieba+FTS5 与向量的 RRF 混合检索）与同类产品"检索范式"的对照。

说明（诚实边界）：NotebookLM、ima、ChatGPT 项目等云端产品无法在本地复现，不能直接跑分。
本实验把同类产品常见的检索范式作为可复现的基线，在同一语料、同一查询、同一指标下对比：
  A. 普通笔记软件式：SQLite FTS5 unicode61（未做中文分词），对应只做关键词匹配的笔记工具
  B. 纯向量 RAG 式：只做 bge-small-zh 向量余弦，对应 AnythingLLM 等"上传即向量化"的工具
  C. 本系统：jieba 预分词关键词 + 向量，RRF 融合
数据集：cmrc2018 长文本（自然语言问句、用词与原文重合）与 头条新闻（查询用词不出现在标题，考察语义召回）。
另含"LLM 故障时数据是否丢失"的鲁棒性对照（LLM 优先流程为模拟基线，已在输出中标注）。
用法：EMBEDDING_MODE=local venv\\Scripts\\python.exe scripts\\compare_systems.py [头条每类条数]
结果写入 ../对比实验结果.md
"""
import os, sys, random, tempfile, time
os.environ.setdefault("EMBEDDING_MODE", "local")
os.environ["LLM_PROVIDER"] = "mock"
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
import numpy as np
import pandas as pd
from app import db, pipeline, hybrid, vectorstore, embedding

N_CAT = int(sys.argv[1]) if len(sys.argv) > 1 else 50
NQ = 300
emb = embedding.get_embedder()
llm = pipeline.MockLLM()


class NoVec(embedding.EmbeddingProvider):
    name = "none"
    def embed(self, texts): raise RuntimeError("off")


def build(items):
    """items: [(title, text)] -> conn, ids。落库并向量化。"""
    tmp = tempfile.mkdtemp()
    conn = db.connect(os.path.join(tmp, "cmp.db"))
    ids = [db.add_document(conn, t, x, "paste") for t, x in items]
    conn.commit()
    for d in ids:
        pipeline.process_document(conn, d, llm, embedder=emb)
        conn.commit()
    # 基线 A：未分词的 unicode61 FTS5（标题+正文原文）
    conn.execute("CREATE VIRTUAL TABLE base_fts USING fts5(body, tokenize='unicode61')")
    for d, (t, x) in zip(ids, items):
        conn.execute("INSERT INTO base_fts(rowid, body) VALUES(?,?)", (d, t + "\n" + x))
    conn.commit()
    return conn, ids


def methods(conn):
    def a(q):
        toks = [w for w in q.split() if w] or [q]
        m = " OR ".join('"' + w.replace('"', '""') + '"' for w in toks)
        try:
            return [r[0] for r in conn.execute(
                "SELECT rowid FROM base_fts WHERE base_fts MATCH ? ORDER BY rank LIMIT 10", (m,))]
        except Exception:
            return []
    def b(q):
        v = emb.embed([q])[0]
        return [h["doc_id"] for h in vectorstore.search(conn, v, emb.name, 10)]
    def c(q):
        return [r["id"] for r in hybrid.hybrid_search(conn, q, limit=10, embedder=emb)]
    def c_kw(q):
        return [r["id"] for r in hybrid.hybrid_search(conn, q, limit=10, embedder=NoVec())]
    return [("A 笔记软件式（unicode61 关键词）", a), ("B 纯向量 RAG 式", b),
            ("本系统：jieba 关键词（不含向量）", c_kw), ("C 本系统：混合 RRF", c)]


def evaluate(fn, queries):
    r1 = r5 = r10 = mrr = 0.0; lat = []
    for q, tgt in queries:
        s = time.time(); res = fn(q); lat.append(time.time() - s)
        if tgt in res:
            k = res.index(tgt) + 1
            r10 += 1; r5 += k <= 5; r1 += k == 1; mrr += 1 / k
    n = len(queries)
    return r1 / n, r5 / n, r10 / n, mrr / n, float(np.mean(lat)) * 1000


def table(conn, queries):
    rows = ["| 方法 | Recall@1 | Recall@5 | Recall@10 | MRR | 延迟(ms) |", "|---|---|---|---|---|---|"]
    for name, fn in methods(conn):
        r = evaluate(fn, queries)
        rows.append(f"| {name} | {r[0]:.3f} | {r[1]:.3f} | {r[2]:.3f} | {r[3]:.3f} | {r[4]:.0f} |")
    return "\n".join(rows)


random.seed(42)
out = ["# 系统对比实验结果", "",
       "同一语料、同一查询、同一指标下对比三种检索范式。云端产品无法本地复现，故以其常见范式作基线。", ""]

# ---- 实验 1：cmrc2018 ----
D = os.path.join(ROOT, "ext_data")
corpus = pd.read_parquet(os.path.join(D, "cmrc_long", "corpus-00000-of-00001.parquet"))
queries = pd.read_parquet(os.path.join(D, "cmrc_long", "queries-00000-of-00001.parquet"))
qrels = pd.read_parquet(os.path.join(D, "cmrc_long_qrels", "dev.parquet"))
gold = dict(zip(qrels["qid"], qrels["pid"]))
items = [(x.strip().replace("\n", " ")[:20], x) for x in corpus["text"]]
conn, ids = build(items)
pid2doc = dict(zip(corpus["id"], ids))
qs = [(t, pid2doc[gold[q]]) for q, t in zip(queries["id"], queries["text"])
      if q in gold and gold[q] in pid2doc]
random.shuffle(qs); qs = qs[:NQ]
t1 = table(conn, qs)
print(t1)
out += [f"## 实验 1：cmrc2018 长文本（{len(items)} 篇，{len(qs)} 条自然语言问句）", "", t1, ""]

# ---- 实验 2：头条 ----
path = os.path.join(D, "toutiao_cat_data.txt")
by_cat = {}
with open(path, encoding="utf-8") as f:
    for line in f:
        p = line.rstrip("\n").split("_!_")
        if len(p) < 5 or len(p[3]) < 12 or not p[4].strip():
            continue
        by_cat.setdefault(p[2], []).append((p[3], p[4].split(",")))
docs = []
for cat, rows in sorted(by_cat.items()):
    for t, kws in random.sample(rows, min(N_CAT, len(rows))):
        docs.append((t, kws))
conn2, ids2 = build([(t, t) for t, _ in docs])
q2 = []
for (t, kws), d in zip(docs, ids2):
    extra = [k for k in kws if k and k not in t]
    if len(extra) >= 2:
        q2.append((" ".join(extra[:2]), d))
random.shuffle(q2); q2 = q2[:NQ]
t2 = table(conn2, q2)
print(t2)
out += [f"## 实验 2：头条新闻（{len(docs)} 篇，{len(q2)} 条查询，查询词不在标题中）", "", t2, ""]

# ---- 实验 3：LLM 故障鲁棒性 ----
texts = [f"测试文档{i}：向量数据库与混合检索笔记，编号{i}" for i in range(30)]
tmp = tempfile.mkdtemp()
c3 = db.connect(os.path.join(tmp, "rob.db"))
bad = pipeline.MockLLM(fail=True)
ids3 = [db.add_document(c3, x[:12], x, "paste") for x in texts]
c3.commit()
for d in ids3:
    pipeline.process_document(c3, d, bad, embedder=emb)
    c3.commit()
stored_ours = c3.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
failed = c3.execute("SELECT COUNT(*) FROM documents WHERE status='failed'").fetchone()[0]
kw_hit = len(hybrid.hybrid_search(c3, "向量数据库", limit=30, embedder=NoVec()))
# 重试：LLM 恢复后同一批文档重新处理
for d in ids3:
    pipeline.process_document(c3, d, llm, embedder=emb)
    c3.commit()
recovered = c3.execute("SELECT COUNT(*) FROM documents WHERE status='stored'").fetchone()[0]
# 模拟基线：LLM 优先流程（先摘要、成功才入库）
base_saved = 0
for x in texts:
    try:
        bad.summarize(x); base_saved += 1
    except Exception:
        pass
out += ["## 实验 3：LLM 全部故障时的数据安全（30 篇）", "",
        "| 流程 | 入库篇数 | 可关键词检索篇数 | 重试后 stored |", "|---|---|---|---|",
        f"| 本系统（数据先行） | {stored_ours}（其中 failed {failed}） | {kw_hit} | {recovered} |",
        f"| LLM 优先流程（模拟基线） | {base_saved} | {base_saved} | 需用户重新录入 |", "",
        "注：LLM 优先流程为按设计模拟，不是对某个具体产品的实测。", ""]
print(out[-6:])

with open(os.path.join(ROOT, "..", "对比实验结果.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("done")
