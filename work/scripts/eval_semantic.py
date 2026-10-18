"""评估实验：语义检索效果对比（词面匹配 vs Mock 哈希词袋 vs 真实 bge-small-zh）。

目的：Mock 向量只能证明词面相似，本实验用"语义近义但用词不同"的查询，
验证真实 Embedding 才具备的近义召回能力，并如实报告 Mock 的局限。

用法（需联网首次下载模型，约 100MB）：
    venv\\Scripts\\python.exe scripts\\eval_semantic.py
若 fastembed 未安装或模型下载失败，真实模型一列显示 N/A，其余照常输出。
指标：Recall@3 / MRR。
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import db  # noqa: E402
from app.embedding import FastEmbedProvider, MockEmbedding  # noqa: E402

# (文档编号, 正文)
CORPUS = [
    ("轿车", "这款轿车的发动机排量为两升，油耗较低，适合家庭日常通勤使用。"),
    ("数据库", "关系型数据库通过索引加速查询，事务保证数据的一致性与持久性。"),
    ("烹饪", "红烧肉需要先焯水，再加入冰糖炒出糖色，小火慢炖一个小时。"),
    ("健身", "每周三次力量训练配合充足蛋白质摄入，有助于增加肌肉并减少脂肪。"),
    ("投资", "分散配置股票与债券可以降低组合波动，长期持有指数基金回报稳定。"),
    ("天气", "明天受冷空气影响，气温骤降，北方地区有大风并伴随小雪。"),
    ("编程", "使用 Python 编写脚本可以自动处理重复的文件整理工作，提高效率。"),
    ("旅行", "去海边度假要提前订好酒店和机票，旺季价格会明显上涨。"),
    ("睡眠", "保持规律作息，睡前不看手机，有助于改善失眠和提高睡眠质量。"),
    ("医疗", "感冒发烧时应多喝水休息，持续高烧不退需要及时就医检查。"),
    ("教育", "孩子的阅读习惯需要从小培养，家长陪伴阅读能提升语言表达能力。"),
    ("环保", "垃圾分类和减少一次性塑料制品，是降低环境污染的有效做法。"),
]
# (查询, 目标文档标题, 类型)：近义组刻意避开与正文相同的词
QUERIES = [
    ("汽车的油耗怎么样", "轿车", "近义"),
    ("怎么让查询变快", "数据库", "近义"),
    ("做肉的步骤", "烹饪", "近义"),
    ("怎样练出肌肉", "健身", "近义"),
    ("理财怎么控制风险", "投资", "近义"),
    ("下周会不会变冷", "天气", "近义"),
    ("用代码自动整理资料", "编程", "近义"),
    ("夜里睡不着怎么办", "睡眠", "近义"),
    ("发烧了该怎么处理", "医疗", "近义"),
    ("发动机排量", "轿车", "字面"),
    ("红烧肉冰糖", "烹饪", "字面"),
    ("垃圾分类", "环保", "字面"),
]
K = 3


def rank_by_scores(scores: np.ndarray) -> list[int]:
    return list(np.argsort(-scores, kind="stable"))


def lexical_scores(query: str) -> np.ndarray:
    """词面基线：查询分词与文档分词的重叠数（与 FTS5 关键词路同一分词器）。"""
    qt = set(db.tokenize(query))
    return np.array([len(qt & set(db.tokenize(t))) for _, t in CORPUS], dtype=np.float32)


def embed_scores(provider):
    docs = provider.embed([t for _, t in CORPUS])

    def f(query):
        q = provider.embed([query])[0]
        return docs @ q
    return f


def evaluate(score_fn, kind: str | None):
    hits, rr, n = 0, 0.0, 0
    for q, target, typ in QUERIES:
        if kind and typ != kind:
            continue
        order = rank_by_scores(score_fn(q))
        titles = [CORPUS[i][0] for i in order]
        pos = titles.index(target) + 1
        n += 1
        hits += pos <= K
        rr += 1.0 / pos
    return n, hits / n, rr / n


def main():
    methods = {"词面重叠": lexical_scores, "Mock哈希词袋": embed_scores(MockEmbedding())}
    real_err = None
    try:
        methods["bge-small-zh"] = embed_scores(FastEmbedProvider())
        methods["bge-small-zh"]("预热")  # 触发模型加载，失败则进入 except
    except Exception as e:  # noqa: BLE001
        methods.pop("bge-small-zh", None)
        real_err = f"{type(e).__name__}: {e}"

    names = ["词面重叠", "Mock哈希词袋", "bge-small-zh"]
    print("# 评估结果：语义检索方案对比\n")
    print(f"语料 {len(CORPUS)} 篇，查询 {len(QUERIES)} 条。指标：Recall@{K} / MRR。\n")
    print("| 分组(查询数) | " + " | ".join(names) + " |")
    print("|---|" + "---|" * len(names))
    for label, kind in (("近义(用词不同)", "近义"), ("字面(用词相同)", "字面"), ("全部", None)):
        n = sum(1 for _, _, t in QUERIES if kind is None or t == kind)
        cells = []
        for m in names:
            if m in methods:
                _, rec, mrr = evaluate(methods[m], kind)
                cells.append(f"{rec:.2f} / {mrr:.2f}")
            else:
                cells.append("N/A")
        print(f"| {label}({n}) | " + " | ".join(cells) + " |")
    print("\n说明：小语料仅做机制对比，不代表大规模表现；Mock 为哈希词袋，近义组预期接近词面基线。")
    if real_err:
        print(f"\n[提示] 真实模型不可用，已跳过：{real_err}\n"
              "请先 pip install fastembed 并联网下载模型后重跑。")


if __name__ == "__main__":
    main()
