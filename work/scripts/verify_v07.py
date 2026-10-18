"""V0.5 分类验证：两段式分类、分类树约束、centroid 增量维护、失败不丢数据。

运行（在 work 目录下）：
    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe scripts/verify_v07.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402

from app import classify, db, embedding, pipeline  # noqa: E402

passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"[PASS] {name}")
    else:
        failed += 1
        print(f"[FAIL] {name} {detail}")


def new_conn():
    d = tempfile.mkdtemp(prefix="kb_v07_")
    return db.connect(os.path.join(d, "kb.db"))


emb = embedding.MockEmbedding()

# 1. 分类树约束
conn = new_conn()
classify.create_category(conn, "技术/数据库/向量库")
check("三级分类可创建", classify.get_by_path(conn, "技术/数据库/向量库") is not None)
check("逐级创建父节点", classify.get_by_path(conn, "技术") is not None
      and classify.get_by_path(conn, "技术/数据库")["depth"] == 2)
try:
    classify.create_category(conn, "a/b/c/d")
    check("深度超过 3 被拒绝", False)
except classify.CategoryLimitError:
    check("深度超过 3 被拒绝", True)
for i in range(12):
    classify.create_category(conn, f"生活/子{i}")
try:
    classify.create_category(conn, "生活/子12")
    check("单节点子分类超过 12 被拒绝", False)
except classify.CategoryLimitError:
    check("单节点子分类超过 12 被拒绝", True)

# 2. centroid 增量维护
conn = new_conn()
cid = classify.create_category(conn, "测试/甲")
v1 = emb.embed(["向量数据库选型"])[0]
v2 = emb.embed(["周末爬山看日出"])[0]
classify.add_to_centroid(conn, cid, v1, emb.name)
classify.add_to_centroid(conn, cid, v2, emb.name)
row = conn.execute("SELECT centroid, doc_count FROM categories WHERE id=?", (cid,)).fetchone()
check("加入两篇后 doc_count=2", row["doc_count"] == 2)
c = np.frombuffer(row["centroid"], dtype=np.float32)
check("centroid 已归一化", abs(float(np.linalg.norm(c)) - 1.0) < 1e-4)
expect = (v1 + v2) / np.linalg.norm(v1 + v2)
check("增量 centroid 等于均值方向", float(c @ expect) > 0.999)
classify.remove_from_centroid(conn, cid, v2, emb.name)
row = conn.execute("SELECT centroid, doc_count FROM categories WHERE id=?", (cid,)).fetchone()
c = np.frombuffer(row["centroid"], dtype=np.float32)
check("移除一篇后 doc_count=1 且 centroid 回到剩余向量", row["doc_count"] == 1 and float(c @ v1) > 0.999)
classify.remove_from_centroid(conn, cid, v1, emb.name)
row = conn.execute("SELECT centroid, doc_count FROM categories WHERE id=?", (cid,)).fetchone()
check("清空后 centroid 为空且 doc_count=0", row["centroid"] is None and row["doc_count"] == 0)

# 3. 流水线：冷启动新建 -> 候选命中归入
conn = new_conn()
llm = pipeline.MockLLM()
d1 = db.add_document(conn, "向量数据库 向量数据库 选型 对比 ChromaDB", None, "paste")
conn.commit()
check("处理成功转 stored", pipeline.process_document(conn, d1, llm, emb) == "stored")
r1 = conn.execute("SELECT category_id, category_path, needs_review FROM documents WHERE id=?", (d1,)).fetchone()
check("冷启动由 LLM 新建分类", r1["category_path"] is not None and r1["category_path"].startswith("通用/"),
      str(dict(r1)))
leaf = (r1["category_path"] or "通用/x").rsplit("/", 1)[-1]
cat = conn.execute("SELECT centroid, doc_count FROM categories WHERE id=?", (r1["category_id"],)).fetchone()
check("分类 centroid 已写入且 doc_count=1", cat["centroid"] is not None and cat["doc_count"] == 1)
d2 = db.add_document(conn, f"另一篇笔记也提到 {leaf} 的使用经验", None, "paste")
conn.commit()
pipeline.process_document(conn, d2, llm, emb)
r2 = conn.execute("SELECT category_path FROM documents WHERE id=?", (d2,)).fetchone()
check("第二篇经候选筛选归入已有分类", r2["category_path"] == r1["category_path"], str(dict(r2)))
n = conn.execute("SELECT doc_count FROM categories WHERE id=?", (r1["category_id"],)).fetchone()[0]
check("doc_count 随归入递增为 2", n == 2, str(n))

# 4. 重试不重复计数
pipeline.process_document(conn, d2, llm, emb)
n = conn.execute("SELECT doc_count FROM categories WHERE id=?", (r1["category_id"],)).fetchone()[0]
check("重复处理不重复计数", n == 2, str(n))

# 5. 约束被突破：退回最相近候选并置 needs_review，不丢数据
class BadDepthLLM(pipeline.MockLLM):
    def classify(self, text, summary, candidates):
        return {"action": "create", "new_category": "a/b/c/d"}


d3 = db.add_document(conn, "向量数据库 选型 的第三篇", None, "paste")
conn.commit()
st = pipeline.process_document(conn, d3, BadDepthLLM(), emb)
r3 = conn.execute("SELECT category_path, needs_review FROM documents WHERE id=?", (d3,)).fetchone()
check("深度违规时仍 stored", st == "stored")
check("退回已有候选分类", r3["category_path"] == r1["category_path"], str(dict(r3)))
check("needs_review 置位", r3["needs_review"] == 1)

conn = new_conn()
d4 = db.add_document(conn, "冷启动且无法新建的文档", None, "paste")
conn.commit()
pipeline.process_document(conn, d4, BadDepthLLM(), emb)
r4 = conn.execute("SELECT category_path, needs_review FROM documents WHERE id=?", (d4,)).fetchone()
check("冷启动无法新建落到系统『未分类』", r4["category_path"] == "未分类" and r4["needs_review"] == 1,
      str(dict(r4)))
sysrow = classify.get_by_path(conn, "未分类")
check("『未分类』标记为系统分类", sysrow is not None and sysrow["is_system"] == 1)

# 6. 分类步骤故障：failed、正文与摘要保留、可重试
class FailClassifyLLM(pipeline.MockLLM):
    def classify(self, text, summary, candidates):
        raise RuntimeError("分类服务故障")


conn = new_conn()
d5 = db.add_document(conn, "分类故障测试 向量数据库", None, "paste")
conn.commit()
st = pipeline.process_document(conn, d5, FailClassifyLLM(), emb)
r5 = conn.execute("SELECT status, summary, error_message, category_id FROM documents WHERE id=?", (d5,)).fetchone()
check("分类故障转 failed 不抛异常", st == "failed")
check("摘要已保留", bool(r5["summary"]))
check("失败原因被记录", "分类服务故障" in (r5["error_message"] or ""))
check("失败文档无分类", r5["category_id"] is None)
check("失败后关键词检索仍可用", any(x["id"] == d5 for x in db.search(conn, "分类故障")))
st = pipeline.process_document(conn, d5, pipeline.MockLLM(), emb)
r5 = conn.execute("SELECT status, category_path, error_message FROM documents WHERE id=?", (d5,)).fetchone()
check("重试后转 stored 且有分类", st == "stored" and r5["category_path"] is not None, str(dict(r5)))
check("重试后清空错误", not r5["error_message"])

print(f"\n通过 {passed} / 失败 {failed}")
sys.exit(1 if failed else 0)
