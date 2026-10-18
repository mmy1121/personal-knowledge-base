"""管理页浏览器端到端验证（用本机 Edge，经 Playwright 驱动，无需下载浏览器）。

前置：venv\Scripts\python.exe -m pip install playwright
流程：临时数据库启动后端 -> 经 API 造 2 篇文档 -> Edge 无头打开 http://127.0.0.1:<port>/
     -> 搜索 -> 点开详情 -> 改标题/分类/标签并保存 -> 校验 API 已变更 -> 删除（自动确认对话框）-> 校验已删除。
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
passed = failed = 0


def check(name, cond):
    global passed, failed
    passed += bool(cond)
    failed += (not cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def call(base, method, path, body=None):
    req = urllib.request.Request(
        base + path, method=method,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    from playwright.sync_api import sync_playwright
    tmp = tempfile.mkdtemp(prefix="kb_ui_")
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    env = dict(os.environ, DB_PATH=os.path.join(tmp, "kb.db"), PYTHONIOENCODING="utf-8")
    env.pop("KB_API_TOKEN", None)
    backend = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                                "--port", str(port)], cwd=ROOT, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        end = time.time() + 30
        while time.time() < end:
            try:
                if urllib.request.urlopen(base + "/api/v1/health", timeout=1).status == 200:
                    break
            except Exception:
                time.sleep(0.4)
        d1 = call(base, "POST", "/api/v1/documents/text",
                  {"text": "向量数据库选型对比：ChromaDB 与 Qdrant 的取舍", "title": "向量库选型"})["data"]["doc_id"]
        d2 = call(base, "POST", "/api/v1/documents/text",
                  {"text": "FastAPI 路由与依赖注入笔记", "title": "FastAPI笔记"})["data"]["doc_id"]

        with sync_playwright() as p:
            br = p.chromium.launch(channel="msedge", headless=True)
            page = br.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("dialog", lambda d: d.accept())  # 删除确认框
            page.goto(base + "/")
            page.wait_for_selector(".item")
            check("首页列出 2 篇文档", page.locator(".item").count() == 2)

            page.fill("#q", "向量数据库")
            page.press("#q", "Enter")
            page.wait_for_function("document.getElementById('msg').textContent.includes('命中')")
            check("搜索命中目标文档", page.locator(".item", has_text="向量库选型").count() >= 1)

            page.locator(".item", has_text="向量库选型").first.click()
            page.wait_for_selector("#e_title")
            check("详情显示正文", "ChromaDB" in page.inner_text("#detail pre"))

            page.fill("#e_title", "向量库选型（已改）")
            page.fill("#e_cat", "技术/数据库")
            page.fill("#e_tags", "向量检索,选型")
            page.click("text=保存修改")
            page.wait_for_function("document.getElementById('msg').textContent.includes('已保存')")
            doc = call(base, "GET", f"/api/v1/documents/{d1}")["data"]
            check("保存后标题已变更", doc["title"] == "向量库选型（已改）")
            check("保存后分类已变更", doc.get("category_path") == "技术/数据库")
            check("保存后标签已变更", "向量检索" in (doc.get("tags") or ""))

            page.click("#detail >> text=删除")
            page.wait_for_function("document.getElementById('msg').textContent.includes('已删除')")
            gone = False
            try:
                call(base, "GET", f"/api/v1/documents/{d1}")
            except urllib.error.HTTPError as e:
                gone = e.code == 404
            check("删除后接口返回 404", gone)
            check("删除后另一篇仍在", call(base, "GET", f"/api/v1/documents/{d2}")["code"] == 200)
            check("页面无 JS 报错", not errors)
            br.close()
    finally:
        backend.kill()
        time.sleep(0.5)
        for f in os.listdir(tmp):
            try:
                os.remove(os.path.join(tmp, f))
            except OSError:
                pass
        try:
            os.rmdir(tmp)
        except OSError:
            pass
    print(f"\n通过 {passed} / 失败 {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
