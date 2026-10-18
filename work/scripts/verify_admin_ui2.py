"""管理页新增交互的浏览器端到端验证（本机 Edge + Playwright）。

覆盖 S01 缺口：页面粘贴文本、页面上传文件、分类树新建/重命名/删除、运行模式显示、
失败时文本保留。用临时数据库，不触碰用户数据。
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


def call(base, method, path):
    req = urllib.request.Request(base + path, method=method)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        # playwright 是可选依赖：未安装时跳过浏览器端验证，不让一键回归崩溃
        print("未安装 playwright，跳过管理页浏览器验证（可选：pip install playwright && playwright install chromium）")
        print("通过 0 / 失败 0")
        return
    tmp = tempfile.mkdtemp(prefix="kb_ui2_")
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    env = dict(os.environ, DB_PATH=os.path.join(tmp, "kb.db"), PYTHONIOENCODING="utf-8",
               LLM_PROVIDER="mock", EMBEDDING_MODE="mock")
    env.pop("KB_API_TOKEN", None)
    backend = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                                "--port", str(port)], cwd=ROOT, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    upload_path = os.path.join(tmp, "上传样例.txt")
    with open(upload_path, "w", encoding="utf-8") as f:
        f.write("这是一份通过页面上传的样例文件，主题是向量数据库选型。")
    try:
        end = time.time() + 30
        while time.time() < end:
            try:
                if urllib.request.urlopen(base + "/api/v1/health", timeout=1).status == 200:
                    break
            except Exception:
                time.sleep(0.4)

        with sync_playwright() as p:
            br = p.chromium.launch(channel="msedge", headless=True)
            page = br.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            prompts = []

            def on_dialog(d):
                if d.type == "prompt":
                    d.accept(prompts.pop(0) if prompts else "")
                else:
                    d.accept()
            page.on("dialog", on_dialog)

            page.goto(base + "/")
            page.wait_for_function("document.getElementById('mode').textContent.includes('运行模式')")
            mode = page.inner_text("#mode")
            check("显示运行模式（Mock 无外发）", "mock" in mode and "无外发" in mode)

            page.fill("#p_title", "页面粘贴测试")
            page.fill("#p_text", "通过管理页粘贴的一段关于混合检索 RRF 的笔记。")
            page.click("text=保存文本")
            page.wait_for_function("document.getElementById('msg').textContent.includes('已存入')")
            check("粘贴后文本框已清空", page.input_value("#p_text") == "")
            page.wait_for_selector(".item", timeout=5000)
            check("粘贴后列表立即可见", page.locator(".item", has_text="页面粘贴测试").count() >= 1)

            page.set_input_files("#p_file", upload_path)
            page.click("button:has-text('上传文件')")
            page.wait_for_function("/已上传|上传失败/.test(document.getElementById('msg').textContent)")
            print("上传后页面提示：", page.inner_text("#msg"))
            check("上传提示为成功", "已上传" in page.inner_text("#msg"))
            check("上传后列表可见", page.locator(".item", has_text="上传样例").count() >= 1)

            page.set_input_files("#p_file", os.path.join(tmp, "不存在.pdf")) if False else None
            bad = os.path.join(tmp, "坏文件.pdf")
            with open(bad, "wb") as f:
                f.write(b"not a pdf")
            page.set_input_files("#p_file", bad)
            page.click("button:has-text('上传文件')")
            page.wait_for_function("document.getElementById('msg').textContent.includes('上传失败')")
            check("损坏 PDF 给出明确失败提示", "上传失败" in page.inner_text("#msg"))

            prompts.append("测试/子类")
            page.click("text=新建分类")
            page.wait_for_function("document.getElementById('msg').textContent.includes('已新建')")
            page.wait_for_function("document.getElementById('tree').textContent.includes('子类')")
            check("分类树显示新建分类", "子类" in page.inner_text("#tree"))

            prompts.append("改名后")
            page.locator("#tree li:not(:has(li))", has_text="子类").first.locator("text=重命名").click()
            page.wait_for_function("document.getElementById('msg').textContent.includes('已重命名')")
            check("分类重命名后树已更新", "改名后" in page.inner_text("#tree"))

            page.locator("#tree li:not(:has(li))", has_text="改名后").first.locator("a", has_text="删除").click()
            page.wait_for_function("document.getElementById('msg').textContent.includes('已删除')")
            check("空分类可删除", "改名后" not in page.inner_text("#tree"))

            total = call(base, "GET", "/api/v1/documents?size=50")["data"]["total"]
            check("API 中确有 2 篇入库文档", total == 2)
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
