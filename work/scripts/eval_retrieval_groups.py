"""S02 评估：按查询类型分组的检索对比（关键词 / 语义 / 混合）。

分组：关键词重合型 / 同义改写型 / 长问句型 / 专有名词型。
指标：Recall@1/5/10、MRR、nDCG@10（每个查询只有 1 个标准答案文档，nDCG 即 1/log2(rank+1)）。
嵌入：优先真实 bge-small-zh（fastembed）；不可用时退回 Mock，并在输出中标明，
Mock 的"语义"列只代表词面哈希，不得当作真实语义结果。
局限：小语料、单次运行、无置信区间；仅做机制对比，不代表真实笔记场景的搜索质量。

用法（work 目录）：
    venv\\Scripts\\python.exe scripts\\eval_retrieval_groups.py
"""
import math
import os
import sys
import tempfile

os.environ.setdefault("LLM_PROVIDER", "mock")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import db, hybrid, vectorstore  # noqa: E402
from app.embedding import FastEmbedProvider, MockEmbedding  # noqa: E402

CORPUS = {
    "轿车": "这款轿车的发动机排量为两升，油耗较低，适合家庭日常通勤使用。",
    "数据库": "关系型数据库通过索引加速查询，事务保证数据的一致性与持久性。",
    "烹饪": "红烧肉需要先焯水，再加入冰糖炒出糖色，小火慢炖一个小时。",
    "健身": "每周三次力量训练配合充足蛋白质摄入，有助于增加肌肉并减少脂肪。",
    "投资": "分散配置股票与债券可以降低组合波动，长期持有指数基金回报稳定。",
    "天气": "明天受冷空气影响，气温骤降，北方地区有大风并伴随小雪。",
    "编程": "使用 Python 编写脚本可以自动处理重复的文件整理工作，提高效率。",
    "旅行": "去海边度假要提前订好酒店和机票，旺季价格会明显上涨。",
    "睡眠": "保持规律作息，睡前不看手机，有助于改善失眠和提高睡眠质量。",
    "医疗": "感冒发烧时应多喝水休息，持续高烧不退需要及时就医检查。",
    "教育": "孩子的阅读习惯需要从小培养，家长陪伴阅读能提升语言表达能力。",
    "环保": "垃圾分类和减少一次性塑料制品，是降低环境污染的有效做法。",
    "向量库": "ChromaDB 与 Qdrant 都是向量库，选型时要比较部署成本与过滤能力。",
    "接口": "FastAPI 基于 Pydantic 做请求校验，并自动生成 OpenAPI 文档。",
    "检索": "RRF 倒数排名融合只使用排名，可以合并 BM25 与余弦相似度两路结果。",
    "备份": "SQLite 的 Backup API 可以在数据库使用中生成一致性的时间点快照。",
}
# (查询, 目标标题, 分组)
QUERIES = [
    ("发动机排量", "轿车", "关键词重合"), ("红烧肉冰糖", "烹饪", "关键词重合"),
    ("垃圾分类", "环保", "关键词重合"), ("事务一致性", "数据库", "关键词重合"),
    ("汽车的油耗怎么样", "轿车", "同义改写"), ("怎么让查询变快", "数据库", "同义改写"),
    ("怎样练出肌肉", "健身", "同义改写"), ("夜里睡不着怎么办", "睡眠", "同义改写"),
    ("理财怎么控制风险", "投资", "同义改写"), ("下周会不会变冷", "天气", "同义改写"),
    ("我想找一份讲家庭日常通勤开车省油的内容", "轿车", "长问句"),
    ("有没有关于孩子从小养成读书习惯的笔记", "教育", "长问句"),
    ("之前记过感冒发烧该怎么处理还有什么时候去医院", "医疗", "长问句"),
    ("帮我找讲怎样合并两路检索结果而不用调权重系数的文章", "检索", "长问句"),
    ("ChromaDB Qdrant", "向量库", "专有名词"), ("FastAPI Pydantic", "接口", "专有名词"),
    ("RRF BM25", "检索", "专有名词"), ("SQLite Backup API", "备份", "专有名词"),
]
KS = (1, 5, 10)


def metrics(ranks: list[int | None]) -> dict:
    n = len(ranks)
    out = {f"R@{k}": sum(1 for r in ranks if r and r <= k) / n for k in KS}
    out["MRR"] = sum(1 / r for r in ranks if r) / n
    out["nDCG@10"] = sum(1 / math.log2(r + 1) for r in ranks if r and r <= 10) / n
    return out


def rank_of(ids: list[int], target: int) -> int | None:
    return ids.index(target) + 1 if target in ids else None


def main():
    try:
        emb = FastEmbedProvider()
        emb.embed(["预热"])
        real = True
    except Exception as e:  # noqa: BLE001
        print(f"[提示] 真实模型不可用，退回 Mock：{type(e).__name__}: {e}")
        emb, real = MockEmbedding(), False

    tmp = tempfile.mkdtemp(prefix="kb_evalgrp_")
    with db.session(os.path.join(tmp, "kb.db")) as conn:
        ids = {}
        for title, text in CORPUS.items():
            ids[title] = db.add_document(conn, text, title, "paste")
            vec = emb.embed([text])
            vectorstore.upsert(conn, ids[title], [(0, len(text), text)], vec, emb.name)
        conn.commit()

        def kw(q):
            return [r.get("id", r.get("doc_id")) for r in db.search(conn, q, 10)]

        def sem(q):  # 纯语义：不设相似度下限，看原始排名能力
            hits = vectorstore.search(conn, emb.embed([q])[0], emb.name, 10)
            return [h["doc_id"] for h in hits]

        def hyb(q):
            return [r["id"] for r in hybrid.hybrid_search(conn, q, 10, embedder=emb)]

        methods = {"关键词": kw, "语义": sem, "混合": hyb}
        groups = ["关键词重合", "同义改写", "长问句", "专有名词", None]
        print(f"# S02 分组检索评估（嵌入：{emb.name}，{'真实' if real else 'Mock，语义列仅代表词面哈希'}）\n")
        print(f"语料 {len(CORPUS)} 篇，查询 {len(QUERIES)} 条，单次运行，无置信区间。\n")
        print("| 分组(n) | 方法 | R@1 | R@5 | R@10 | MRR | nDCG@10 |")
        print("|---|---|---|---|---|---|---|")
        for g in groups:
            qs = [q for q in QUERIES if g is None or q[2] == g]
            for name, fn in methods.items():
                ranks = [rank_of(fn(q), ids[t]) for q, t, _ in qs]
                m = metrics(ranks)
                print(f"| {g or '全部'}({len(qs)}) | {name} | " + " | ".join(
                    f"{m[c]:.2f}" for c in ("R@1", "R@5", "R@10", "MRR", "nDCG@10")) + " |")
        print("\n误例（混合未进 Top-1 的查询）：")
        for q, t, g in QUERIES:
            r = rank_of(hyb(q), ids[t])
            if r != 1:
                print(f"- [{g}] {q} → 目标「{t}」排名 {r}；关键词 {rank_of(kw(q), ids[t])}，语义 {rank_of(sem(q), ids[t])}")


if __name__ == "__main__":
    main()
