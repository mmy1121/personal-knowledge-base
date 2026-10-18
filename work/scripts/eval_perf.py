"""S03 规模与性能评估：1k / 10k 文档下混合检索（关键词 + 语义 + RRF）的延迟 P50/P95。

运行（work 目录）：
    venv\\Scripts\\python.exe scripts\\eval_perf.py [文档数 ...]    默认 1000 10000
设计说明：
- 使用固定随机种子的合成语料与合成向量（512 维，同 bge-small-zh），只测检索链路延迟，
  不代表真实语义质量；不调用任何 LLM / 真实 embedding，无需密钥。
- 每篇文档 5 个切片，10k 文档即 5 万切片，对应规格 NFR-3 的上限规模。
- 使用临时数据库，不污染 data/kb.db。
"""
import os
import random
import statistics
import sys
import tempfile
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import db, hybrid, vectorstore  # noqa: E402

DIM = 512
CHUNKS_PER_DOC = 5
VOCAB = ("向量 数据库 检索 分类 标签 摘要 融合 排名 索引 分词 模型 嵌入 文档 笔记 悬浮框 "
         "备份 恢复 性能 缓存 事务 线程 队列 接口 前端 后端 算法 日志 配置 部署 测试 "
         "登山 日出 咖啡 旅行 预算 合同 报销 会议 课程 论文 实验 数据集 指标 误差 样本").split()


class FakeEmbedder:
    """返回固定种子随机向量的假 embedder，仅用于延迟测量。"""
    name = "perf-fake-512"

    def __init__(self):
        self.rng = np.random.default_rng(7)

    def embed(self, texts):
        v = self.rng.standard_normal((len(texts), DIM)).astype(np.float32)
        return v / np.linalg.norm(v, axis=1, keepdims=True)


def build(db_path: str, n: int, emb: FakeEmbedder):
    rnd = random.Random(42)
    t0 = time.time()
    with db.session(db_path) as conn:
        for i in range(n):
            text = " ".join(rnd.choice(VOCAB) for _ in range(60)) + f" 编号{i}"
            doc_id = db.add_document(conn, text, f"文档{i}", "paste")
            vecs = emb.embed([f"c{i}-{j}" for j in range(CHUNKS_PER_DOC)])
            chunks = [(0, 10, text[:10])] * CHUNKS_PER_DOC
            vectorstore.upsert(conn, doc_id, chunks, vecs, emb.name)
            conn.execute("UPDATE documents SET status='stored' WHERE id=?", (doc_id,))
            if i % 500 == 499:
                conn.commit()
    return time.time() - t0


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def measure(db_path: str, emb: FakeEmbedder, runs: int = 30):
    rnd = random.Random(1)
    queries = [" ".join(rnd.sample(VOCAB, 2)) for _ in range(runs)]
    kw, hy = [], []
    with db.session(db_path) as conn:
        for q in queries:  # 关键词路单独计时
            t = time.perf_counter()
            terms = list(dict.fromkeys(db.tokenize(q)))
            db._rank_ids(conn, db._fts_query(terms, "AND"), 50)
            db._rank_ids(conn, db._fts_query(terms, "OR"), 50)
            kw.append((time.perf_counter() - t) * 1000)
        for q in queries:  # 完整混合检索（含向量全量扫描）
            t = time.perf_counter()
            hybrid.hybrid_search(conn, q, 10, embedder=emb)
            hy.append((time.perf_counter() - t) * 1000)
    return kw, hy


def main(sizes):
    rows = []
    for n in sizes:
        tmp = tempfile.mkdtemp(prefix=f"kb_perf_{n}_")
        path = os.path.join(tmp, "kb.db")
        emb = FakeEmbedder()
        build_s = build(path, n, emb)
        size_mb = os.path.getsize(path) / 1024 / 1024
        kw, hy = measure(path, emb)
        row = (n, n * CHUNKS_PER_DOC, size_mb, build_s,
               statistics.median(kw), pct(kw, 95), statistics.median(hy), pct(hy, 95))
        rows.append(row)
        print(f"文档 {n} / 切片 {n*CHUNKS_PER_DOC} / 库 {size_mb:.1f}MB / 造数 {build_s:.1f}s | "
              f"关键词 P50 {row[4]:.1f}ms P95 {row[5]:.1f}ms | 混合 P50 {row[6]:.1f}ms P95 {row[7]:.1f}ms")
    print("\n| 文档数 | 切片数 | 库大小MB | 关键词 P50/P95 ms | 混合 P50/P95 ms | 亚秒级(P95<1000ms) |")
    print("|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r[0]} | {r[1]} | {r[2]:.1f} | {r[4]:.1f} / {r[5]:.1f} | {r[6]:.1f} / {r[7]:.1f} | "
              f"{'是' if r[7] < 1000 else '否'} |")


if __name__ == "__main__":
    main([int(x) for x in sys.argv[1:]] or [1000, 10000])
