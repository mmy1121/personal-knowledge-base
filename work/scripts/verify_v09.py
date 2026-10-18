"""V0.9 验证：本地 API 防护（可选 token + Host 校验）。

运行（work 目录下）：
    venv/Scripts/python.exe scripts/verify_v09.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
_tmp = tempfile.mkdtemp(prefix="kb_verify9_")
os.environ["DB_PATH"] = os.path.join(_tmp, "kb.db")
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


# 1. 未设置 token：开箱即用
r = client.post("/api/v1/documents/text", json={"text": "未设置 token 也能入库"})
check("未设置 token 时放行", r.status_code == 200, r.text)

# 2. Host 校验（防 DNS rebinding）
r = client.get("/api/v1/health", headers={"Host": "evil.example.com"})
check("非法 Host 返回 403", r.status_code == 403, r.text)
r = client.get("/api/v1/health", headers={"Host": "127.0.0.1:8000"})
check("本机 Host 放行", r.status_code == 200, r.text)
r = client.get("/api/v1/health", headers={"Host": "localhost:8000"})
check("localhost Host 放行", r.status_code == 200, r.text)

# 3. 设置 token 后
os.environ["KB_API_TOKEN"] = "secret-123"
try:
    r = client.post("/api/v1/documents/text", json={"text": "无 token"})
    check("缺少 token 返回 401", r.status_code == 401, r.text)
    check("401 使用统一响应格式", r.json().get("code") == 401)
    r = client.post("/api/v1/documents/text", json={"text": "错 token"},
                    headers={"X-KB-Token": "wrong"})
    check("错误 token 返回 401", r.status_code == 401, r.text)
    r = client.post("/api/v1/documents/text", json={"text": "对 token"},
                    headers={"X-KB-Token": "secret-123"})
    check("正确 token 放行", r.status_code == 200, r.text)
    r = client.delete("/api/v1/documents/1")
    check("删除接口同样受保护", r.status_code == 401, r.text)
    r = client.post("/api/v1/search", json={"query": "token"})
    check("检索接口同样受保护", r.status_code == 401, r.text)
    r = client.get("/api/v1/health")
    check("health 免 token", r.status_code == 200, r.text)
    r = client.options("/api/v1/documents/text",
                       headers={"Origin": "http://127.0.0.1:5173",
                                "Access-Control-Request-Method": "POST"})
    check("CORS 预检不被 token 拦截", r.status_code != 401, str(r.status_code))
    r = client.get("/api/v1/health", headers={"Host": "evil.example.com"})
    check("设置 token 后非法 Host 仍 403", r.status_code == 403, r.text)
finally:
    os.environ.pop("KB_API_TOKEN", None)

# 4. 取消 token 后恢复放行
r = client.post("/api/v1/documents/text", json={"text": "取消 token 后恢复"})
check("取消 token 后恢复放行", r.status_code == 200, r.text)

print(f"\n通过 {passed} / 失败 {failed}")
sys.exit(1 if failed else 0)
