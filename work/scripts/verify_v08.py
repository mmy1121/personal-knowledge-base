"""V0.8 验证脚本：知识管理（改标题/分类/标签、corrections、级联删除）与分类树管理。

运行（需在 work 目录下，用 venv 解释器）：
    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe scripts/verify_v08.py
使用临时数据库，不污染 data/kb.db。
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
_tmp = tempfile.mkdtemp(prefix="kb_verify08_")
os.environ["DB_PATH"] = os.path.join(_tmp, "kb.db")
# 固定 Mock，避免外部环境变量（如真实 LLM 的 key/provider）改变分类结果而影响断言
os.environ["LLM_PROVIDER"] = "mock"
os.environ["EMBEDDING_MODE"] = "mock"
os.environ.pop("LLM_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from app import classify, db, manage, pipeline  # noqa: E402
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


def one(conn, sql, *a):
    r = conn.execute(sql, a).fetchone()
    return r[0] if r else None


with TestClient(app) as client:
    # ---- 准备：入库并处理 ----
    ids = []
    for t in ["向量数据库选型对比 ChromaDB", "周末爬山看日出", "Python 异步编程笔记"]:
        r = client.post("/api/v1/documents/text", json={"text": t}).json()
        ids.append(r["data"]["doc_id"])
        client.post(f"/api/v1/documents/{ids[-1]}/reprocess")
    d1, d2, d3 = ids

    # ---- 文档修正 ----
    r = client.patch(f"/api/v1/documents/{d1}", json={"title": "新标题 向量选型"})
    check("PATCH 改标题成功", r.status_code == 200 and r.json()["data"]["title"] == "新标题 向量选型")
    s = client.post("/api/v1/search", json={"query": "向量选型"}).json()["data"]["results"]
    check("改标题后 FTS 可按新标题检索", any(x["id"] == d1 for x in s))
    check("空标题返回 400", client.patch(f"/api/v1/documents/{d1}", json={"title": "  "}).status_code == 400)
    check("不存在文档返回 404", client.patch("/api/v1/documents/99999", json={"title": "x"}).status_code == 404)

    r = client.patch(f"/api/v1/documents/{d1}", json={"category_path": "技术/数据库"})
    check("PATCH 改分类成功", r.status_code == 200 and r.json()["data"]["category_path"] == "技术/数据库")
    r = client.patch(f"/api/v1/documents/{d1}", json={"tags": ["向量检索", "FastAPI", "向量检索"]})
    check("PATCH 改标签并去重", r.status_code == 200 and r.json()["data"]["tags"] == "向量检索,FastAPI")

    with db.session(os.environ["DB_PATH"]) as conn:
        check("分类变更写入 corrections", one(conn, "SELECT COUNT(*) FROM corrections WHERE doc_id=? AND kind='category'", d1) == 1)
        check("标签变更写入 corrections", one(conn, "SELECT COUNT(*) FROM corrections WHERE doc_id=? AND kind='tags'", d1) == 1)
        check("用户标签来源为 user",
              one(conn, "SELECT COUNT(*) FROM document_tags WHERE doc_id=? AND source='user'", d1) == 2)
        check("旧 llm 标签已被替换",
              one(conn, "SELECT COUNT(*) FROM document_tags WHERE doc_id=? AND source='llm'", d1) == 0)
        check("目标分类 doc_count=1", one(conn, "SELECT doc_count FROM categories WHERE path='技术/数据库'") == 1)

    r = client.patch(f"/api/v1/documents/{d1}", json={"category_path": "a/b/c/d"})
    check("分类深度超限返回 400", r.status_code == 400)
    # 再次提交相同分类不产生新的 corrections
    client.patch(f"/api/v1/documents/{d1}", json={"category_path": "技术/数据库"})
    with db.session(os.environ["DB_PATH"]) as conn:
        check("相同分类不重复记 corrections",
              one(conn, "SELECT COUNT(*) FROM corrections WHERE doc_id=? AND kind='category'", d1) == 1)

    tags = client.get("/api/v1/tags").json()["data"]["items"]
    check("标签列表含用户标签", any(t["name"] == "FastAPI" for t in tags))

    # ---- 分类树 ----
    client.patch(f"/api/v1/documents/{d2}", json={"category_path": "生活/户外"})
    client.patch(f"/api/v1/documents/{d3}", json={"category_path": "技术/编程"})
    tree = client.get("/api/v1/categories").json()["data"]["tree"]
    roots = {n["name"] for n in tree}
    check("分类树含根节点", {"技术", "生活"} <= roots)
    tech = next(n for n in tree if n["name"] == "技术")
    check("分类树含子节点", {c["name"] for c in tech["children"]} >= {"数据库", "编程"})

    r = client.post("/api/v1/categories", json={"path": "技术/网络"})
    check("新建分类成功", r.status_code == 200)

    cid = next(c["id"] for c in tech["children"] if c["name"] == "编程")
    r = client.patch(f"/api/v1/categories/{cid}", json={"name": "软件开发"})
    check("重命名成功", r.status_code == 200 and r.json()["data"]["path"] == "技术/软件开发")
    with db.session(os.environ["DB_PATH"]) as conn:
        check("重命名同步 documents.category_path",
              one(conn, "SELECT category_path FROM documents WHERE id=?", d3) == "技术/软件开发")
    check("重命名含 '/' 返回 400",
          client.patch(f"/api/v1/categories/{cid}", json={"name": "a/b"}).status_code == 400)
    check("重命名不存在返回 404",
          client.patch("/api/v1/categories/99999", json={"name": "x"}).status_code == 404)

    with db.session(os.environ["DB_PATH"]) as conn:
        db_id = one(conn, "SELECT id FROM categories WHERE path='技术/数据库'")
        dev_id = one(conn, "SELECT id FROM categories WHERE path='技术/软件开发'")
    r = client.patch(f"/api/v1/categories/{dev_id}", json={"merge_into": db_id})
    check("合并分类成功", r.status_code == 200)
    with db.session(os.environ["DB_PATH"]) as conn:
        check("合并后文档迁移到目标分类",
              one(conn, "SELECT category_path FROM documents WHERE id=?", d3) == "技术/数据库")
        check("合并后源分类被删除", one(conn, "SELECT COUNT(*) FROM categories WHERE id=?", dev_id) == 0)
        check("合并后目标 doc_count=2", one(conn, "SELECT doc_count FROM categories WHERE id=?", db_id) == 2)
    check("合并到自身返回 400",
          client.patch(f"/api/v1/categories/{db_id}", json={"merge_into": db_id}).status_code == 400)
    with db.session(os.environ["DB_PATH"]) as conn:
        tech_id = one(conn, "SELECT id FROM categories WHERE path='技术'")
    check("含子分类者不可合并",
          client.patch(f"/api/v1/categories/{tech_id}", json={"merge_into": db_id}).status_code == 400)

    # ---- 级联删除 ----
    with db.session(os.environ["DB_PATH"]) as conn:
        n_chunks = one(conn, "SELECT COUNT(*) FROM chunks WHERE doc_id=?", d1)
        tag_cnt_before = one(conn, "SELECT doc_count FROM tags WHERE name='FastAPI'")
    check("删除前有切片", n_chunks >= 1)
    check("删除成功", client.delete(f"/api/v1/documents/{d1}").status_code == 200)
    with db.session(os.environ["DB_PATH"]) as conn:
        check("删除后切片无残留", one(conn, "SELECT COUNT(*) FROM chunks WHERE doc_id=?", d1) == 0)
        check("删除后正文无残留", one(conn, "SELECT COUNT(*) FROM document_bodies WHERE doc_id=?", d1) == 0)
        check("删除后 FTS 无残留", one(conn, "SELECT COUNT(*) FROM fts_docs WHERE rowid=?", d1) == 0)
        check("删除后 document_tags 无残留", one(conn, "SELECT COUNT(*) FROM document_tags WHERE doc_id=?", d1) == 0)
        check("删除后标签 doc_count 回退",
              one(conn, "SELECT doc_count FROM tags WHERE name='FastAPI'") == tag_cnt_before - 1)
        check("删除后分类 doc_count 回退为 1", one(conn, "SELECT doc_count FROM categories WHERE id=?", db_id) == 1)
    check("删除不存在返回 404", client.delete(f"/api/v1/documents/{d1}").status_code == 404)

    # ---- 删除分类 ----
    from app import classify as _cl
    with db.session(os.environ["DB_PATH"]) as conn:
        empty_id = _cl.create_category(conn, "临时/空分类")
        full_id = _cl.create_category(conn, "临时/有文档")
        conn.execute("UPDATE documents SET category_id=?, category_path='临时/有文档' WHERE id=?", (full_id, d3))
        conn.execute("UPDATE categories SET doc_count=1 WHERE id=?", (full_id,))
        sys_id = _cl.create_category(conn, "未分类", is_system=1)
        parent_id = one(conn, "SELECT id FROM categories WHERE path='临时'")
    check("含子分类者不可删除",
          client.delete(f"/api/v1/categories/{parent_id}").status_code == 400)
    check("系统分类不可删除",
          client.delete(f"/api/v1/categories/{sys_id}").status_code == 400)
    check("有文档且未指定迁移目标返回 400",
          client.delete(f"/api/v1/categories/{full_id}").status_code == 400)
    check("删除空分类成功", client.delete(f"/api/v1/categories/{empty_id}").status_code == 200)
    r = client.delete(f"/api/v1/categories/{full_id}", params={"migrate_to": db_id})
    check("指定 migrate_to 后删除成功", r.status_code == 200, str(r.text))
    with db.session(os.environ["DB_PATH"]) as conn:
        check("文档已迁移到目标分类",
              one(conn, "SELECT category_path FROM documents WHERE id=?", d3) == "技术/数据库")
        check("被删分类已不存在", one(conn, "SELECT COUNT(*) FROM categories WHERE id=?", full_id) == 0)
    check("删除不存在分类返回 404", client.delete("/api/v1/categories/99999").status_code == 404)

print(f"\n通过 {passed} / 失败 {failed}")
sys.exit(1 if failed else 0)
