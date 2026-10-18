import os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
from fastapi.testclient import TestClient
from app import main
with TestClient(main.app) as c:
    r = c.post("/api/v1/documents/text", json={"text": "向量数据库选型：对比 ChromaDB 与 Qdrant", "source_type": "float_window"}).json()
    did = r["data"]["doc_id"]
    import time; time.sleep(1.5)
    d = c.get(f"/api/v1/documents/{did}").json()["data"]
    print("status_after_post:", d["status"], "| summary:", d["summary"], "| category:", d["category_path"], "| tags:", d["tags"])
    lst = c.get("/api/v1/documents?category_path=x&tag=y").json()["data"]
    print("list_total_with_unknown_filters:", lst["total"], "| item_keys:", list(lst["items"][0].keys()))
    s = c.post("/api/v1/search", json={"query": "向量数据库", "filters": {"category_path": "不存在", "tags": ["不存在"]}}).json()["data"]["results"]
    print("search_with_bad_category_filter_hits:", len(s), "| result_keys:", list(s[0].keys()) if s else None)
print("LLM_PROVIDER=deepseek ->", end=" ")
os.environ["LLM_PROVIDER"] = "deepseek"
from app import pipeline
try: pipeline.set_llm(None); pipeline.get_llm()
except Exception as e: print(e)
