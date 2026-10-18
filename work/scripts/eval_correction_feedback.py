"""评估：用户修正反馈对自动分类准确率的影响（头条数据集，真实 bge 向量）。

设计（如实说明：LLM 用确定性替身，隔离"候选排序"这一机制本身，不含真实 LLM 的判断能力）：
- 每类取 K 篇"种子文档"：先由 MockLLM 随意分类，再模拟用户手动改到正确分类（写入 corrections）。
- 每类再取 T 篇测试文档，按随机顺序依次入库分类；替身 LLM 总是选候选列表第一名。
- 对照：开启修正反馈（CORR_MIN_SIM=0.5） vs 关闭（CORR_MIN_SIM=1.1，等价于无修正候选）。
- 指标：测试文档最终分类路径 == 真实类别路径 的比例。
用法：EMBEDDING_MODE=local venv\\Scripts\\python.exe scripts\\eval_correction_feedback.py
"""
import os, sys, random, tempfile
os.environ.setdefault("EMBEDDING_MODE", "local")
os.environ["LLM_PROVIDER"] = "mock"
os.environ["AUTO_PROCESS"] = "0"
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
from app import db, pipeline, manage, embedding

T = 20
KS = [0, 1, 3, 5]
DATA = os.path.join(ROOT, "ext_data", "toutiao_cat_data.txt")
random.seed(7)
by_cat = {}
with open(DATA, encoding="utf-8") as f:
    for line in f:
        p = line.rstrip("\n").split("_!_")
        if len(p) >= 5 and len(p[3]) >= 12:
            by_cat.setdefault(p[2], []).append(p[3])
cats = sorted(by_cat)
emb = embedding.get_embedder()


class FirstCandLLM(pipeline.MockLLM):
    """总是选第一个候选；无候选则新建『杂项/未知』。"""
    def classify(self, text, summary, candidates):
        self.calls += 1
        if candidates:
            return {"action": "assign", "category_path": candidates[0]["path"]}
        return {"action": "create", "new_category": "杂项/未知"}


def run(k, feedback, seeds, tests):
    os.environ["CORR_MIN_SIM"] = "0.5" if feedback else "1.1"
    conn = db.connect(os.path.join(tempfile.mkdtemp(), "e.db"))
    mock = pipeline.MockLLM()
    for cat, titles in seeds.items():
        for t in titles[:k]:
            d = db.add_document(conn, t, t, "paste"); conn.commit()
            pipeline.process_document(conn, d, mock, embedder=emb); conn.commit()
            manage.update_document(conn, d, category_path=cat); conn.commit()  # 用一级分类，避免 15 类挤在同一父节点触发 12 子类上限
    llm = FirstCandLLM()
    hit = 0
    for cat, t in tests:
        d = db.add_document(conn, t, t, "paste"); conn.commit()
        pipeline.process_document(conn, d, llm, embedder=emb); conn.commit()
        got = conn.execute("SELECT category_path FROM documents WHERE id=?", (d,)).fetchone()[0]
        hit += got == cat
    return hit / len(tests)


seeds, tests = {}, []
for c in cats:
    pool = random.sample(by_cat[c], 5 + T)
    seeds[c] = pool[:5]
    tests += [(c, t) for t in pool[5:]]
random.shuffle(tests)

rows = ["| 每类修正篇数 K | 关闭反馈 | 开启反馈 | 提升 |", "|---|---|---|---|"]
for k in KS:
    off = run(k, False, seeds, tests)
    on = run(k, True, seeds, tests)
    rows.append(f"| {k} | {off:.3f} | {on:.3f} | {on-off:+.3f} |")
    print(rows[-1], flush=True)
txt = ("# 修正反馈对分类准确率的影响（头条 15 类，每类 %d 篇测试，共 %d 篇）\n\n" % (T, len(tests))
       + "\n".join(rows)
       + "\n\n说明：LLM 为确定性替身（总选首位候选），只评估候选排序机制；单次运行，未做多种子置信区间。\n")
print(txt)
with open(os.path.join(ROOT, "eval_correction_feedback_result.md"), "w", encoding="utf-8") as f:
    f.write(txt)
