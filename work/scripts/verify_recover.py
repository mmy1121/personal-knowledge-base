"""S03 强杀恢复验证：pending / processing 的遗留文档在重启恢复后应回到 stored，且正文不丢、可关键词检索。

运行（work 目录）：venv\\Scripts\\python.exe scripts\\verify_recover.py
说明：用临时数据库并固定 Mock，不触碰用户数据，也不使用任何真实 key。
模拟方式：正常入库后，把状态改回 pending / processing 并清掉处理产物，
等价于“请求已返回但后台任务未执行 / 处理中途进程被杀”，再调用 pipeline.recover。
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
_tmp = tempfile.mkdtemp(prefix="kb_recover_")
os.environ["DB_PATH"] = os.path.join(_tmp, "kb.db")
os.environ["LLM_PROVIDER"] = "mock"
os.environ["EMBEDDING_MODE"] = "mock"
os.environ.pop("LLM_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from app import db, pipeline  # noqa: E402
from app.main import app  # noqa: E402

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    passed += bool(cond)
    failed += (not cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {'' if cond else detail}")


def status_of(conn, i):
    return conn.execute("SELECT status FROM documents WHERE id=?", (i,)).fetchone()[0]


with TestClient(app) as client:
    ids = []
    for t in ["向量数据库选型对比 ChromaDB 与 Qdrant", "周末爬山看日出", "Python 异步编程笔记"]:
        ids.append(client.post("/api/v1/documents/text", json={"text": t}).json()["data"]["doc_id"])
    d_pending, d_processing, d_ok = ids

    path = os.environ["DB_PATH"]
    # 模拟 1：任务尚未开始就被杀 -> pending，无任何处理产物
    # 模拟 2：处理到一半被杀 -> processing，且有残缺产物
    with db.session(path) as conn:
        for i in (d_pending, d_processing):
            conn.execute("DELETE FROM chunks WHERE doc_id=?", (i,))
            conn.execute("UPDATE documents SET summary=NULL, key_points=NULL, category_id=NULL, "
                         "category_path=NULL WHERE id=?", (i,))
        conn.execute("UPDATE documents SET status='pending' WHERE id=?", (d_pending,))
        conn.execute("UPDATE documents SET status='processing' WHERE id=?", (d_processing,))
        check("模拟后状态为 pending / processing",
              status_of(conn, d_pending) == "pending" and status_of(conn, d_processing) == "processing")

    # 恢复前：正文仍在，且可关键词检索（数据先行）
    r = client.post("/api/v1/search", json={"query": "爬山"}).json()["data"]["results"]
    check("未恢复时正文可关键词检索", any(x["id"] == d_processing for x in r))

    recovered = pipeline.recover(path)
    check("recover 返回两篇遗留文档", sorted(recovered) == sorted([d_pending, d_processing]), str(recovered))

    with db.session(path) as conn:
        check("pending 恢复为 stored", status_of(conn, d_pending) == "stored")
        check("processing 恢复为 stored", status_of(conn, d_processing) == "stored")
        check("已完成文档未被重复处理", status_of(conn, d_ok) == "stored" and d_ok not in recovered)
        check("恢复后补全摘要", bool(conn.execute(
            "SELECT summary FROM documents WHERE id=?", (d_pending,)).fetchone()[0]))
        check("恢复后补全分类", conn.execute(
            "SELECT category_id FROM documents WHERE id=?", (d_processing,)).fetchone()[0] is not None)
        check("恢复后生成切片", conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE doc_id=?", (d_pending,)).fetchone()[0] > 0)
        check("正文未丢失", conn.execute(
            "SELECT COUNT(*) FROM document_bodies WHERE doc_id IN (?,?)",
            (d_pending, d_processing)).fetchone()[0] == 2)

    # 重复恢复应幂等：不再有遗留，也不产生重复切片
    with db.session(path) as conn:
        before = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    again = pipeline.recover(path)
    with db.session(path) as conn:
        after = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    check("再次 recover 无遗留文档", again == [])
    check("重复恢复不产生重复切片", before == after, f"{before}->{after}")

print(f"\n通过 {passed} / 失败 {failed}")
sys.exit(1 if failed else 0)
