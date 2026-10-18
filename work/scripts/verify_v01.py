r"""V0.1 验证脚本：建表、text/upload 入库、中文检索、删除无残留、失败不丢数据。

运行（需在 work 目录下，用 venv 解释器）：
    venv\Scripts\python.exe scripts\verify_v01.py
使用临时数据库，不污染 data/kb.db。
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
_tmp = tempfile.mkdtemp(prefix="kb_verify_")
os.environ["DB_PATH"] = os.path.join(_tmp, "kb.db")

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)
passed, failed = 0, 0


def check(name: str, cond: bool, detail: str = ""):
    global passed, failed
    if cond:
        passed += 1
        print(f"[PASS] {name}")
    else:
        failed += 1
        print(f"[FAIL] {name} {detail}")


# 1. 健康检查与统一响应格式
r = client.get("/api/v1/health").json()
check("health 统一响应格式", r.get("code") == 200 and "data" in r and r.get("msg") == "success")

# 2. 文本入库：status=pending，返回 doc_id
r = client.post("/api/v1/documents/text",
                json={"text": "向量数据库选型：对比 ChromaDB 与 Qdrant，最终使用 sqlite-vec。",
                      "source_type": "float_window"}).json()
check("text 入库返回 doc_id 且 pending", r["code"] == 200 and r["data"]["status"] == "pending")
id1 = r["data"]["doc_id"]

r = client.post("/api/v1/documents/text",
                json={"text": "文档自动分类与标签整理的实现思路，分类树深度不超过三层。", "title": "分类笔记"}).json()
id2 = r["data"]["doc_id"]

# 3. 空文本拒绝，不静默存空
resp = client.post("/api/v1/documents/text", json={"text": "   "})
check("空文本被拒绝(400)", resp.status_code == 400 and resp.json()["code"] == 400)

# 4. 标题为空时取首行截断
d = client.get(f"/api/v1/documents/{id1}").json()["data"]
check("标题默认取首行截断", d["title"].startswith("向量数据库选型") and len(d["title"]) <= 30)
check("详情含正文", "sqlite-vec" in d["clean_text"])

# 5. TXT 上传（GBK 编码）与 MD 上传
gbk = "中文检索测试文档：全文检索需要分词。".encode("gbk")
r = client.post("/api/v1/documents/upload", files={"file": ("gbk笔记.txt", gbk)}).json()
check("GBK TXT 上传成功", r["code"] == 200 and r["data"]["title"] == "gbk笔记")
gid = r["data"]["doc_id"]
d = client.get(f"/api/v1/documents/{gid}").json()["data"]
check("GBK 解码正确", "全文检索" in d["clean_text"])

md = "# 标题\n\n- 列表项：混合检索使用 RRF 融合\n".encode("utf-8")
r = client.post("/api/v1/documents/upload", files={"file": ("note.md", md)}).json()
check("MD 上传成功", r["code"] == 200)

resp = client.post("/api/v1/documents/upload", files={"file": ("a.pdf", b"%PDF")})
check("伪造/损坏 PDF 返回 400 且有明确提示（V0.2 起支持 PDF，不再按格式拒绝）",
      resp.status_code == 400 and bool(resp.json().get("msg")))

# 6. 中文检索：长词、2 字词、英文专有名词
def hit(q, doc_id):
    res = client.post("/api/v1/search", json={"query": q}).json()["data"]["results"]
    return doc_id in [x["id"] for x in res], res


ok1, res = hit("向量数据库", id1)
check("搜『向量数据库』命中", ok1)
ok2, _ = hit("分类", id2)
check("2 字词『分类』命中", ok2)
ok3, res3 = hit("ChromaDB", id1)
check("专有名词 ChromaDB 精确命中", ok3)
check("命中片段含高亮【】", any("【" in x["snippet"] for x in res3))
ok4, _ = hit("向量库选型 ChromaDB Qdrant 完全不存在的词", id1)
check("多词查询不因 AND 过严漏召回(OR 档兜底)", ok4)
res0 = client.post("/api/v1/search", json={"query": "zzzqqq xqxqxq"}).json()
check("无结果不报错", res0["code"] == 200 and res0["data"]["results"] == [],
      f"实际返回: {res0}")
resp = client.post("/api/v1/search", json={"query": ""})
check("空查询返回 400", resp.status_code == 400)

# 7. 列表分页，且不含正文
lst = client.get("/api/v1/documents?page=1&size=2").json()["data"]
check("列表分页", lst["total"] >= 4 and len(lst["items"]) == 2)
check("列表不加载正文", all("clean_text" not in it for it in lst["items"]))

# 8. 删除后无 FTS / 正文残留
check("删除成功", client.delete(f"/api/v1/documents/{id1}").json()["code"] == 200)
with db.session(os.environ["DB_PATH"]) as conn:
    n_body = conn.execute("SELECT COUNT(*) FROM document_bodies WHERE doc_id=?", (id1,)).fetchone()[0]
    n_fts = conn.execute("SELECT COUNT(*) FROM fts_docs WHERE rowid=?", (id1,)).fetchone()[0]
check("删除后正文无残留", n_body == 0)
check("删除后 FTS 无残留", n_fts == 0)
ok5, _ = hit("ChromaDB", id1)
check("删除后检索不再命中", not ok5)
check("删除不存在文档返回 404", client.delete("/api/v1/documents/99999").status_code == 404)

print(f"\n通过 {passed} / 失败 {failed}")
sys.exit(1 if failed else 0)
