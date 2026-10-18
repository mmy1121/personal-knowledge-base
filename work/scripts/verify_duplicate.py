"""重复导入行为验证：相同正文仍入库，但响应返回 duplicate_of；不覆盖已有文档的人工修正。

运行（work 目录）：venv\\Scripts\\python.exe scripts\\verify_duplicate.py
使用临时数据库与 Mock，不触碰用户数据。
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
_tmp = tempfile.mkdtemp(prefix="kb_verify_dup_")
os.environ["DB_PATH"] = os.path.join(_tmp, "kb.db")
os.environ["LLM_PROVIDER"] = "mock"
os.environ["EMBEDDING_MODE"] = "mock"

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402

passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"[PASS] {name}")
    else:
        failed += 1
        print(f"[FAIL] {name} {detail}")


with TestClient(app) as client:
    text = "向量数据库选型笔记：ChromaDB 与 Qdrant 的对比。"
    r1 = client.post("/api/v1/documents/text", json={"text": text}).json()["data"]
    check("首次录入 duplicate_of 为空", r1.get("duplicate_of") is None)
    d1 = r1["doc_id"]

    client.patch(f"/api/v1/documents/{d1}", json={"category_path": "技术/数据库", "tags": ["手工标签"]})

    r2 = client.post("/api/v1/documents/text", json={"text": text}).json()["data"]
    check("重复录入返回 duplicate_of=首篇 id", r2.get("duplicate_of") == d1, str(r2))
    check("重复内容仍入库（不丢数据）", r2["doc_id"] != d1)

    r3 = client.post("/api/v1/documents/text", json={"text": text + "（改动）"}).json()["data"]
    check("内容不同不判为重复", r3.get("duplicate_of") is None)

    r4 = client.post("/api/v1/documents/text", json={"text": "  " + text + "\n"}).json()["data"]
    check("首尾空白不影响判重", r4.get("duplicate_of") == d1)

    doc = client.get(f"/api/v1/documents/{d1}").json()["data"]
    check("重复导入未覆盖人工分类", doc.get("category_path") == "技术/数据库", str(doc.get("category_path")))
    check("重复导入未覆盖人工标签", "手工标签" in (doc.get("tags") or ""), str(doc.get("tags")))

    up = client.post("/api/v1/documents/upload",
                     files={"file": ("dup.txt", text.encode("utf-8"), "text/plain")}).json()["data"]
    check("文件上传同样返回 duplicate_of", up.get("duplicate_of") == d1, str(up))

    with db.session(os.environ["DB_PATH"]) as conn:
        n = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    check("文档总数 = 5（全部保留）", n == 5, str(n))

print(f"\n通过 {passed} / 失败 {failed}")
sys.exit(1 if failed else 0)
