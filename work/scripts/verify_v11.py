"""V0.11 验证：录入/上传后自动触发后台处理（摘要->标签->向量化->分类）。"""
import io, os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
tmp = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(tmp, "kb.db")
os.environ.pop("AUTO_PROCESS", None)
from fastapi.testclient import TestClient
from app import main
c = TestClient(main.app)
ok_n = bad_n = 0
def check(name, cond):
    global ok_n, bad_n
    print(("[PASS] " if cond else "[FAIL] ") + name)
    ok_n += bool(cond); bad_n += (not cond)

def detail(i): return c.get(f"/api/v1/documents/{i}").json()["data"]

r = c.post("/api/v1/documents/text", json={"text": "向量数据库选型：对比 ChromaDB 与 Qdrant 的性能和部署成本", "source_type": "float_window"}).json()
d = detail(r["data"]["doc_id"])
check("文本录入后自动转 stored", d["status"] == "stored")
check("自动生成摘要", bool(d["summary"]))
check("自动生成标签", bool(d["tags"]))
check("自动归入分类", bool(d["category_path"]))

up = c.post("/api/v1/documents/upload", files={"file": ("a.txt", "FastAPI 后端接口设计：统一响应格式与错误处理".encode("utf-8"))}).json()
d2 = detail(up["data"]["doc_id"])
check("文件上传后自动转 stored", d2["status"] == "stored")
check("上传文档有分类与摘要", bool(d2["category_path"]) and bool(d2["summary"]))

os.environ["AUTO_PROCESS"] = "0"
r3 = c.post("/api/v1/documents/text", json={"text": "周末计划：去爬山看日出"}).json()
check("AUTO_PROCESS=0 时保持 pending", detail(r3["data"]["doc_id"])["status"] == "pending")
os.environ.pop("AUTO_PROCESS")
print(f"\n通过 {ok_n} / 失败 {bad_n}")
sys.exit(1 if bad_n else 0)
