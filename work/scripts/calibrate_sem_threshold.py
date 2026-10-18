"""标定真实 Embedding 的语义相似度下限 SEM_MIN_SIM：统计相关对与无关对的余弦分布。"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import importlib.util
spec = importlib.util.spec_from_file_location("ev", os.path.join(os.path.dirname(__file__), "eval_semantic.py"))
src = open(spec.origin, encoding="utf-8").read().split("def ")[0]
ns = {"__file__": spec.origin}
exec(compile(src, spec.origin, "exec"), ns)
from app.embedding import FastEmbedProvider
CORPUS, QUERIES = ns["CORPUS"], ns["QUERIES"]
emb = FastEmbedProvider("BAAI/bge-small-zh-v1.5")
D = emb.embed([t for _, t in CORPUS]); titles = [k for k, _ in CORPUS]
Q = emb.embed([q[0] for q in QUERIES])
pos, neg = [], []
for i, q in enumerate(QUERIES):
    sims = D @ Q[i]
    for j, t in enumerate(titles):
        (pos if t == q[1] else neg).append(float(sims[j]))
pos, neg = np.array(pos), np.array(neg)
print(f"相关对 n={len(pos)} min={pos.min():.3f} mean={pos.mean():.3f}")
print(f"无关对 n={len(neg)} max={neg.max():.3f} mean={neg.mean():.3f} p95={np.percentile(neg,95):.3f}")
for th in (0.3, 0.4, 0.5, 0.55, 0.6, 0.65):
    r = (pos >= th).mean(); fp = (neg >= th).mean()
    print(f"阈值 {th}: 相关保留 {r:.2f} 无关误入 {fp:.2f}")
