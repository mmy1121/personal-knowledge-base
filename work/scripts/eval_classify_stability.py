"""S02 评估：自组织分类的稳定性（复用已有分类 / 过度新增 / 纯度 / needs_review）。

用法（work 目录）：
    venv\Scripts\python.exe -I -X utf8 scripts\eval_classify_stability.py
真实 LLM（密钥只从环境变量读取，不落盘）：
    set LLM_PROVIDER=deepseek & set LLM_API_KEY=... & set EMBEDDING_MODE=fastembed

做法：5 个主题 x 4 篇，共 20 篇，按交错顺序逐篇走 pipeline.process_document，
统计：
- 创建分类数（理想接近主题数 5，远大于 5 即过度新增）
- 复用率：非该主题首篇的文档中，被归入"已有分类"的比例
- 纯度：每个主题的文档是否落在同一分类（多数分类占比）
- needs_review 数量
单次运行，样本小，仅作机制观察，不给统计显著性结论。
"""
import os
import sys
import tempfile
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("EMBEDDING_MODE", "mock")
os.environ["AUTO_PROCESS"] = "0"
from app import db, pipeline  # noqa: E402

TOPICS = {
    "数据库": [
        "关系型数据库通过 B+ 树索引加速查询，事务具备 ACID 特性。",
        "SQLite 是嵌入式数据库，单文件存储，适合本地应用。",
        "向量数据库用余弦相似度检索语义相近的文本片段。",
        "数据库慢查询优化可以从索引、执行计划和表结构入手。",
    ],
    "烹饪": [
        "红烧肉先焯水再炒糖色，小火慢炖一个小时。",
        "煮米饭水量约为米的 1.2 倍，焖十分钟口感更好。",
        "炒青菜要大火快炒，出锅前再放盐保持脆嫩。",
        "番茄炒蛋先炒蛋盛出，再炒番茄汁后合并。",
    ],
    "健身": [
        "每周三次力量训练配合蛋白质摄入有助于增肌。",
        "深蹲与硬拉是复合动作，能同时锻炼多个肌群。",
        "跑步前要热身，避免膝盖与脚踝受伤。",
        "训练后拉伸并保证睡眠，有利于肌肉恢复。",
    ],
    "旅行": [
        "去海边度假要提前订酒店和机票，旺季价格上涨。",
        "东京地铁线路复杂，建议购买交通卡节省时间。",
        "高原旅行要注意防晒和高原反应，循序渐进。",
        "出境游需提前办理签证并确认护照有效期。",
    ],
    "理财": [
        "分散配置股票与债券可以降低组合波动。",
        "长期定投指数基金，能平滑买入成本。",
        "应急资金建议留足六个月的生活开支。",
        "通货膨胀会侵蚀现金购买力，需关注实际收益率。",
    ],
}


def main():
    path = os.path.join(tempfile.mkdtemp(prefix="cls_stab_"), "kb.db")
    # 交错顺序：每轮各主题取一篇，更接近真实录入
    order = []
    for i in range(4):
        for t in TOPICS:
            order.append((t, TOPICS[t][i]))
    assigned = defaultdict(list)
    first_seen = {}
    reuse = total_after_first = review = 0
    with db.session(path) as conn:
        for t, text in order:
            doc_id = db.add_document(conn, text, None, "paste")
            conn.commit()
            before = {r[0] for r in conn.execute("SELECT id FROM categories")}
            status = pipeline.process_document(conn, doc_id)
            conn.commit()
            row = conn.execute("SELECT category_id, category_path, needs_review FROM documents WHERE id=?",
                               (doc_id,)).fetchone()
            assigned[t].append(row["category_path"])
            review += row["needs_review"] or 0
            if t in first_seen:
                total_after_first += 1
                if row["category_id"] in before:
                    reuse += 1
            else:
                first_seen[t] = doc_id
            if status != "stored":
                err = conn.execute("SELECT error_message FROM documents WHERE id=?", (doc_id,)).fetchone()[0]
                print(f"[警告] 文档 {doc_id} 状态 {status}：{(err or '')[:200]}")
        n_cat = conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
        paths = [r[0] for r in conn.execute("SELECT path FROM categories ORDER BY path")]
    pur = {}
    for t, ps in assigned.items():
        c = Counter(ps)
        pur[t] = (c.most_common(1)[0][1] / len(ps), dict(c))
    lines = [f"# S02 分类稳定性评估（LLM={os.environ['LLM_PROVIDER']}，Embedding={os.environ['EMBEDDING_MODE']}）", "",
             f"文档 {len(order)} 篇，主题 {len(TOPICS)} 个，单次运行，无置信区间。", "",
             f"- 创建分类数：{n_cat}（理想≈{len(TOPICS)}，越大越说明过度新增）",
             f"- 复用已有分类：{reuse}/{total_after_first} = {reuse / max(1, total_after_first):.2f}",
             f"- needs_review：{review} 篇", "",
             "| 主题 | 同类聚合度 | 分类分布 |", "|---|---|---|"]
    for t, (p, dist) in pur.items():
        lines.append(f"| {t} | {p:.2f} | {dist} |")
    lines += ["", "全部分类：" + "、".join(paths), "",
              "说明：Mock LLM/哈希向量只验证机制，不代表真实模型的分类稳定性；"
              "真实结论需用 deepseek + fastembed 复跑并另行标注。"]
    print("\n".join(lines))


if __name__ == "__main__":
    main()
