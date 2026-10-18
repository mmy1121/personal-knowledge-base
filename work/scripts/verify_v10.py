"""V1.0 管理页验证：GET / 返回 HTML 管理页，且不影响 API。

运行（在 work 目录）：
    venv/Scripts/python.exe scripts/verify_v10.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="kb_verify_"), "kb.db")
os.environ.pop("KB_API_TOKEN", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)
passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"[PASS] {name}")
    else:
        failed += 1
        print(f"[FAIL] {name} {detail}")


r = client.get("/")
check("GET / 返回 200", r.status_code == 200, str(r.status_code))
check("返回 HTML", "text/html" in r.headers.get("content-type", ""), r.headers.get("content-type", ""))
check("页面为 UTF-8 且含中文标题", "知识库" in r.text)
check("页面调用检索接口", "/api/v1/search" in r.text)
check("页面调用文档接口", "/api/v1/documents" in r.text)
check("API 不受影响", client.get("/api/v1/health").json()["code"] == 200)

print(f"\n通过 {passed} / 失败 {failed}")
sys.exit(1 if failed else 0)
