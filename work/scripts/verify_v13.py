"""V0.13 验证：真实 LLM Provider（用本地 HTTP 假服务模拟 OpenAI 兼容与 Ollama 接口）、JSON 容错解析、.env 加载、Provider 选择。"""
import os, sys, json, threading, tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from app import llm, config, pipeline

ok_n = fail_n = 0
def check(name, cond):
    global ok_n, fail_n
    print(("[PASS] " if cond else "[FAIL] ") + name)
    if cond: ok_n += 1
    else: fail_n += 1

REPLIES = {}
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        user = body["messages"][-1]["content"]
        if "选择分类" in user: txt = '结果如下 {"action":"create","new_category":"技术/数据库"} 完毕'
        elif "摘要" in user: txt = '好的：\n```json\n{"summary":"这是摘要","key_points":["要点1","要点2"]}\n```'
        elif "标签" in user: txt = '{"tags":["向量检索","FastAPI"]}'
        else: txt = '结果如下 {"action":"create","new_category":"技术/数据库"} 完毕'
        self.auth = self.headers.get("Authorization")
        REPLIES["auth"] = self.headers.get("Authorization")
        out = {"choices": [{"message": {"content": txt}}]} if self.path.endswith("/chat/completions") \
            else {"message": {"content": txt}}
        if "/error" in self.path:
            self.send_response(500); self.end_headers(); return
        data = json.dumps(out).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(data))); self.end_headers()
        self.wfile.write(data)
srv = HTTPServer(("127.0.0.1", 0), H); port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{port}"

# JSON 容错
check("纯 JSON", llm.parse_json('{"a":1}') == {"a": 1})
check("代码块 JSON", llm.parse_json('x```json\n{"a":2}\n```y') == {"a": 2})
check("夹带说明文字", llm.parse_json('结果 {"a":3} 完毕') == {"a": 3})
try: llm.parse_json("无json"); check("无法解析抛错", False)
except ValueError: check("无法解析抛错", True)

# OpenAI 兼容
p = llm.OpenAICompatLLM("sk-test", base, "m")
s = p.summarize("正文" * 10)
check("摘要解析（代码块包裹）", s["summary"] == "这是摘要" and len(s["key_points"]) == 2)
check("携带 Bearer key", REPLIES["auth"] == "Bearer sk-test")
check("标签解析", p.tag("正文") == ["向量检索", "FastAPI"])
c = p.classify("正文", "摘要", [])
check("分类解析（夹带文字）", c["action"] == "create" and c["new_category"] == "技术/数据库")
# Ollama
o = llm.OllamaLLM("qwen", base)
check("Ollama 摘要", o.summarize("正文")["summary"] == "这是摘要")
# 错误
try: llm.OpenAICompatLLM("", base, "m"); check("缺 key 报错", False)
except RuntimeError: check("缺 key 报错", True)
bad = llm.OpenAICompatLLM("k", base + "/error", "m")
try: bad.summarize("x"); check("HTTP 错误抛异常", False)
except Exception: check("HTTP 错误抛异常", True)
dead = llm.OllamaLLM("q", "http://127.0.0.1:1")
try: dead.summarize("x"); check("服务未启动抛异常", False)
except Exception: check("服务未启动抛异常", True)

# .env
d = tempfile.mkdtemp(); f = os.path.join(d, ".env")
open(f, "w", encoding="utf-8").write('# c\nZZ_TEST_A="hello"\nZZ_TEST_B=1\n')
from pathlib import Path
r = config.load_env(Path(f))
check(".env 加载并去引号", r.get("ZZ_TEST_A") == "hello" and os.environ["ZZ_TEST_B"] == "1")
os.environ["ZZ_TEST_B"] = "keep"; open(f, "a").write("ZZ_TEST_B=2\n"); config.load_env(Path(f))
check("真实环境变量优先", os.environ["ZZ_TEST_B"] == "keep")

# get_llm 选择
pipeline.set_llm(None)
os.environ["LLM_PROVIDER"] = "ollama"; os.environ["LLM_BASE_URL"] = base
check("get_llm 选择 ollama", isinstance(pipeline.get_llm(), llm.OllamaLLM))
pipeline.set_llm(None); os.environ["LLM_PROVIDER"] = "deepseek"; os.environ["LLM_API_KEY"] = "k"
check("get_llm 选择 deepseek", isinstance(pipeline.get_llm(), llm.OpenAICompatLLM))
pipeline.set_llm(None); os.environ["LLM_PROVIDER"] = "mock"
check("get_llm 默认 mock", isinstance(pipeline.get_llm(), pipeline.MockLLM))
print(f"\n通过 {ok_n} / 失败 {fail_n}")
