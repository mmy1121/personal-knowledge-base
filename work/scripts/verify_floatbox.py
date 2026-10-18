"""验证悬浮框提交逻辑（不依赖 Qt、不依赖真实后端）。

覆盖：
1. 成功：返回 ok=True 与 doc_id，请求体字段为 text / source_type=float_window
2. 后端返回业务错误（code != 200）：ok=False，带错误信息
3. 后端返回 HTTP 500：ok=False
4. 后端未启动（端口无监听）：ok=False，提示中含"保留"，不抛异常
5. 空文本：ok=False，不发请求
"""
import json
import os
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from floatbox.submit import submit_text  # noqa: E402

received = []
last_headers = []  # 记录每次请求的头，用于验证 X-KB-Token
received_headers = []


def make_handler(mode: str):
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            received_headers.append(dict(self.headers))
            received.append((self.path, json.loads(self.rfile.read(n).decode("utf-8"))))
            last_headers.append({k.lower(): v for k, v in self.headers.items()})
            if mode == "ok":
                code, body = 200, {"code": 200, "msg": "success", "data": {"doc_id": 42}}
            elif mode == "biz":
                code, body = 200, {"code": 400, "msg": "正文为空，拒绝入库", "data": {}}
            else:
                code, body = 500, {"code": 500, "msg": "boom", "data": {}}
            raw = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *a):
            pass
    return H


def serve(mode):
    srv = HTTPServer(("127.0.0.1", 0), make_handler(mode))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}"


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


passed = failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"[OK]   {name}")
    else:
        failed += 1
        print(f"[FAIL] {name}")


srv, base = serve("ok")
r = submit_text("复制来的一段文字", base=base)
check("成功提交返回 ok 与 doc_id", r.ok and r.doc_id == 42)
check("请求路径正确", received[-1][0] == "/api/v1/documents/text")
check("字段为 text + source_type=float_window",
      received[-1][1].get("text") == "复制来的一段文字"
      and received[-1][1].get("source_type") == "float_window"
      and "clean_text" not in received[-1][1])
srv.shutdown()

srv, base = serve("biz")
r = submit_text("abc", base=base)
check("业务错误 ok=False 且带信息", (not r.ok) and "拒绝" in r.message)
srv.shutdown()

srv, base = serve("http500")
r = submit_text("abc", base=base)
check("HTTP 500 ok=False", not r.ok)
srv.shutdown()

try:
    r = submit_text("不能丢的文本", base=f"http://127.0.0.1:{free_port()}")
    check("后端未启动不抛异常，ok=False，提示保留文本", (not r.ok) and "保留" in r.message)
except Exception as e:  # noqa: BLE001
    check(f"后端未启动不应抛异常（抛了 {type(e).__name__}）", False)

n_before = len(received)
r = submit_text("   \n  ")
check("空文本不发请求", (not r.ok) and len(received) == n_before)

# 设置 KB_API_TOKEN 后，请求必须携带 X-KB-Token；未设置时不带该头
os.environ.pop("KB_API_TOKEN", None)
srv, base = serve("ok")
submit_text("无 token 场景", base=base)
check("未设置 token 时不携带 X-KB-Token", "x-kb-token" not in last_headers[-1])
os.environ["KB_API_TOKEN"] = "secret-123"
submit_text("有 token 场景", base=base)
check("设置 KB_API_TOKEN 后携带 X-KB-Token", last_headers[-1].get("x-kb-token") == "secret-123")
os.environ.pop("KB_API_TOKEN", None)
srv.shutdown()

print(f"\n通过 {passed} 项，失败 {failed} 项")
sys.exit(1 if failed else 0)
