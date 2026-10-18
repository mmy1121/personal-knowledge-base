"""V0.4 标签验证：标签写入、来源标记、展示字段同步、故障不丢数据、重试、删除无残留。

运行（在 work 目录下）：
    venv/Scripts/python.exe scripts/verify_v06.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import db, embedding, pipeline  # noqa: E402

passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"[PASS] {name}")
    else:
        failed += 1
        print(f"[FAIL] {name} {detail}")


class FailTagLLM(pipeline.MockLLM):
    """摘要正常，标签阶段抛错。"""

    def tag(self, text):
        raise RuntimeError("标签服务故障")


path = os.path.join(tempfile.mkdtemp(prefix="kb_v06_"), "kb.db")
emb = embedding.MockEmbedding()
TEXT = "向量数据库选型对比。向量数据库适合语义检索，ChromaDB 与 Qdrant 都是常见的向量数据库。"

with db.session(path) as conn:
    d1 = db.add_document(conn, TEXT)
    conn.commit()
    st = pipeline.process_document(conn, d1, pipeline.MockLLM(), emb)
    check("处理成功转 stored", st == "stored")
    rows = conn.execute(
        "SELECT t.name, dt.source FROM document_tags dt JOIN tags t ON t.id=dt.tag_id "
        "WHERE dt.doc_id=?", (d1,)).fetchall()
    names = [r["name"] for r in rows]
    check("写入 1~8 个标签", 1 <= len(names) <= 8, str(names))
    check("标签来源标记为 llm", all(r["source"] == "llm" for r in rows))
    check("高频词『向量数据库』或其切词成为标签",
          any(n in ("向量数据库", "数据库", "向量") for n in names), str(names))
    check("标签不含无信息量词", not any(n in ("知识", "内容") for n in names))
    shown = conn.execute("SELECT tags FROM documents WHERE id=?", (d1,)).fetchone()[0]
    check("documents.tags 展示字段已同步", bool(shown) and all(n in shown for n in names), str(shown))
    dc = conn.execute("SELECT doc_count FROM tags WHERE name=?", (names[0],)).fetchone()[0]
    check("标签 doc_count 为 1", dc == 1, str(dc))

    # 重处理不产生重复标签关联
    pipeline.process_document(conn, d1, pipeline.MockLLM(), emb)
    n2 = conn.execute("SELECT COUNT(*) FROM document_tags WHERE doc_id=?", (d1,)).fetchone()[0]
    check("重处理不产生重复标签", n2 == len(names), f"{n2} vs {len(names)}")

    # 第二篇文档共享标签，doc_count 递增
    d2 = db.add_document(conn, "另一篇也讲向量数据库的笔记，向量数据库很重要。")
    conn.commit()
    pipeline.process_document(conn, d2, pipeline.MockLLM(), emb)
    shared = conn.execute(
        "SELECT t.doc_count FROM tags t JOIN document_tags dt ON dt.tag_id=t.id "
        "WHERE dt.doc_id=? AND t.id IN (SELECT tag_id FROM document_tags WHERE doc_id=?) LIMIT 1",
        (d2, d1)).fetchone()
    check("共享标签 doc_count 递增为 2", shared is not None and shared[0] == 2, str(shared and shared[0]))

    # 标签阶段故障：转 failed，摘要保留，正文与关键词检索仍可用
    d3 = db.add_document(conn, "标签故障测试文档，关键词唯一词汇零壹贰叁。")
    conn.commit()
    st3 = pipeline.process_document(conn, d3, FailTagLLM(), emb)
    check("标签故障转 failed 不抛异常", st3 == "failed")
    r3 = conn.execute("SELECT summary, error_message FROM documents WHERE id=?", (d3,)).fetchone()
    check("摘要步骤已保留", bool(r3["summary"]))
    check("失败原因被记录", "标签服务故障" in (r3["error_message"] or ""))
    check("失败时无标签残留",
          conn.execute("SELECT COUNT(*) FROM document_tags WHERE doc_id=?", (d3,)).fetchone()[0] == 0)
    check("失败后关键词检索仍可用", any(h["id"] == d3 for h in db.search(conn, "唯一词汇")))

    # 重试成功
    st3b = pipeline.process_document(conn, d3, pipeline.MockLLM(), emb)
    check("重试后转 stored", st3b == "stored")
    check("重试后标签写入",
          conn.execute("SELECT COUNT(*) FROM document_tags WHERE doc_id=?", (d3,)).fetchone()[0] > 0)

    # 删除文档：关联与向量无残留
    db.delete_document(conn, d1)
    conn.commit()
    check("删除后 document_tags 无残留",
          conn.execute("SELECT COUNT(*) FROM document_tags WHERE doc_id=?", (d1,)).fetchone()[0] == 0)

print(f"\n通过 {passed} / 失败 {failed}")
sys.exit(1 if failed else 0)
