"""V0.3 验证脚本：处理流水线状态机、LLM 故障不丢数据、重试、启动恢复、重试接口。

运行（在 work 目录下）：
    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe scripts/verify_v03.py
使用临时数据库，不污染 data/kb.db。
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
_tmp = tempfile.mkdtemp(prefix="kb_verify_v03_")
DB = os.path.join(_tmp, "kb.db")
os.environ["DB_PATH"] = DB

from fastapi.testclient import TestClient  # noqa: E402

from app import db, pipeline  # noqa: E402
from app.main import app  # noqa: E402

passed, failed = 0, 0


def check(name: str, cond: bool, detail: str = ""):
    global passed, failed
    if cond:
        passed += 1
        print(f"[PASS] {name}")
    else:
        failed += 1
        print(f"[FAIL] {name} {detail}")


def status_of(doc_id):
    with db.session(DB) as c:
        r = c.execute("SELECT status, summary, error_message FROM documents WHERE id=?",
                      (doc_id,)).fetchone()
        return dict(r)


def add(text, title=None):
    with db.session(DB) as c:
        return db.add_document(c, text, title)


# 1. 正常路径：pending -> stored，写入摘要与要点
d1 = add("向量数据库选型笔记\n对比 ChromaDB 与 sqlite-vec\n结论：个人规模用 sqlite-vec")
check("入库初始为 pending", status_of(d1)["status"] == "pending")
llm_ok = pipeline.MockLLM()
res = pipeline.process_by_id(DB, d1, llm_ok)
s = status_of(d1)
check("处理成功转 stored", res == "stored" and s["status"] == "stored")
check("摘要已写入", bool(s["summary"]))
check("无 error_message", s["error_message"] is None)

# 2. LLM 故障：文档不丢、状态 failed、记录错误、关键词仍可检索
d2 = add("分类体系需要随内容生长，深度上限为三级", "分类设计")
res = pipeline.process_by_id(DB, d2, pipeline.MockLLM(fail=True))
s = status_of(d2)
check("LLM 故障转 failed 不抛异常", res == "failed" and s["status"] == "failed")
check("失败原因被记录", bool(s["error_message"]) and "Mock LLM" in s["error_message"])
check("失败文档无摘要", not s["summary"])
with db.session(DB) as c:
    hits = [r["id"] for r in db.search(c, "分类体系")]
check("无摘要时关键词检索仍可命中", d2 in hits)
with db.session(DB) as c:
    body = c.execute("SELECT clean_text FROM document_bodies WHERE doc_id=?", (d2,)).fetchone()
check("失败后正文未丢失", body is not None and "分类体系" in body[0])

# 3. 重试：LLM 恢复后同一文档转 stored，错误信息清空
llm2 = pipeline.MockLLM()
res = pipeline.process_by_id(DB, d2, llm2)
s = status_of(d2)
check("重试后转 stored", res == "stored" and s["status"] == "stored")
check("重试后摘要写入且错误清空", bool(s["summary"]) and s["error_message"] is None)

# 4. 重试只重做缺失步骤：已有摘要的文档再次处理不再调用 LLM
llm3 = pipeline.MockLLM()
pipeline.process_by_id(DB, d1, llm3)
check("已完成步骤不重复调用 LLM", llm3.calls == 0, f"calls={llm3.calls}")

# 5. 不存在的文档
with db.session(DB) as c:
    check("处理不存在文档返回 missing", pipeline.process_document(c, 99999) == "missing")

# 6. 启动恢复：遗留 pending / processing 被重新投递，stored 不动
d3 = add("遗留 pending 文档 甲")
d4 = add("遗留 processing 文档 乙")
with db.session(DB) as c:
    c.execute("UPDATE documents SET status='processing' WHERE id=?", (d4,))
ids = pipeline.recover(DB, pipeline.MockLLM())
check("recover 只处理 pending/processing", set(ids) == {d3, d4}, f"ids={ids}")
check("遗留文档全部转 stored", status_of(d3)["status"] == "stored" and status_of(d4)["status"] == "stored")

# 7. 重试接口 + 启动事件（with 块才会触发 startup）
pipeline.set_llm(pipeline.MockLLM(fail=True))
with TestClient(app) as client:
    r = client.post("/api/v1/documents/text", json={"text": "接口重试测试文档 丙"}).json()
    d5 = r["data"]["doc_id"]
    check("接口录入返回 pending", r["data"]["status"] == "pending")
    r1 = client.post(f"/api/v1/documents/{d5}/reprocess").json()
    check("reprocess 在 LLM 故障时返回 failed 且 code=200",
          r1["code"] == 200 and r1["data"]["status"] == "failed" and bool(r1["data"]["error_message"]))
    pipeline.set_llm(pipeline.MockLLM())
    r2 = client.post(f"/api/v1/documents/{d5}/reprocess").json()
    check("LLM 恢复后 reprocess 转 stored", r2["data"]["status"] == "stored")
    r3 = client.post("/api/v1/documents/99999/reprocess")
    check("reprocess 不存在文档返回 404", r3.status_code == 404)
    det = client.get(f"/api/v1/documents/{d5}").json()["data"]
    check("详情含摘要与 stored 状态", det["status"] == "stored" and bool(det["summary"]))

# 8. 启动恢复集成：关闭后重启应用，遗留 pending 被自动处理
pipeline.set_llm(pipeline.MockLLM())
d6 = add("重启前遗留文档 丁")
check("重启前为 pending", status_of(d6)["status"] == "pending")
with TestClient(app):
    pass
check("应用启动事件自动恢复遗留文档", status_of(d6)["status"] == "stored")

print(f"\n通过 {passed} / 失败 {failed}")
sys.exit(1 if failed else 0)
