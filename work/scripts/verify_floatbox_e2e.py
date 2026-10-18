"""悬浮框真实端到端验证（需要交互式 Windows 桌面，运行期间请勿操作键鼠）。

流程：
1. 用临时数据库在空闲端口启动后端；
2. 启动悬浮框（真实 RegisterHotKey）；
3. 打开记事本作为"第三方前台应用"；
4. 用 SendInput 模拟真实 Ctrl+Alt+K，检查悬浮框成为前台窗口（热键 + 焦点）；
5. 模拟键入文本并按 Ctrl+Enter，检查临时数据库新增 source_type=float_window 的文档；
6. 清理所有子进程与临时文件。
"""
import ctypes
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from ctypes import wintypes

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
user32 = ctypes.windll.user32
KEYUP, UNICODE = 0x0002, 0x0004
VK = {"ctrl": 0x11, "alt": 0x12, "enter": 0x0D, "k": 0x4B}
passed = failed = 0


def check(name, cond):
    global passed, failed
    passed += cond
    failed += (not cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


class KI(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class MI(ctypes.Structure):  # 仅用于让 INPUT 联合体大小正确
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("d", wintypes.DWORD),
                ("f", wintypes.DWORD), ("t", wintypes.DWORD), ("e", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KI), ("mi", MI)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def send(vk=0, flags=0, scan=0):
    i = INPUT(type=1, ki=KI(vk, scan, flags, 0, 0))
    user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT))


def combo(*names):
    keys = [VK[n] for n in names]
    for k in keys:
        send(k)
    time.sleep(0.05)
    for k in reversed(keys):
        send(k, KEYUP)


def type_text(s):
    for ch in s:
        send(0, UNICODE, ord(ch))
        send(0, UNICODE | KEYUP, ord(ch))
        time.sleep(0.01)


def fg_pid():
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
    return pid.value


def fg_exe() -> str:
    """前台窗口所属进程的可执行文件名（小写）。
    venv 的 python.exe 是启动器，真正的窗口属于其子进程，pid 不等于 Popen.pid，故按文件名判断。"""
    pid = fg_pid()
    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = wintypes.DWORD(1024)
        if ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return os.path.basename(buf.value).lower()
        return ""
    finally:
        ctypes.windll.kernel32.CloseHandle(h)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def wait(cond, timeout=15, step=0.3):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(step)
    return False


def main():
    tmp = tempfile.mkdtemp(prefix="kb_e2e_")
    db_path = os.path.join(tmp, "kb.db")
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    env = dict(os.environ, DB_PATH=db_path, KB_API_BASE=base, PYTHONIOENCODING="utf-8")
    env.pop("KB_API_TOKEN", None)
    procs = []
    try:
        backend = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                                    "--port", str(port)], cwd=ROOT, env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append(backend)

        def up():
            try:
                return urllib.request.urlopen(base + "/api/v1/health", timeout=1).status == 200
            except Exception:
                return False
        check("后端启动", wait(up, 30))

        box = subprocess.Popen([sys.executable, "-m", "floatbox.app"], cwd=ROOT, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append(box)
        time.sleep(3)  # 等待托盘与热键注册
        check("悬浮框进程存活（热键注册未崩溃）", box.poll() is None)

        notepad = subprocess.Popen(["notepad.exe"])
        procs.append(notepad)
        time.sleep(1.5)
        user32.SetForegroundWindow(user32.FindWindowW("Notepad", None))
        time.sleep(0.5)

        combo("ctrl", "alt", "k")
        shown = wait(lambda: fg_exe().startswith("python"), 5)
        check("真实热键呼出悬浮框并成为前台窗口（焦点）", shown)

        text = f"热键端到端测试 e2e {int(time.time())}"
        type_text(text)
        time.sleep(0.3)
        combo("ctrl", "enter")

        def stored():
            try:
                c = sqlite3.connect(db_path)
                r = c.execute("SELECT COUNT(*) FROM documents WHERE source_type='float_window'").fetchone()[0]
                c.close()
                return r >= 1
            except Exception:
                return False
        check("Ctrl+Enter 后数据库新增 float_window 文档", wait(stored, 10))
        c = sqlite3.connect(db_path)
        row = c.execute("SELECT b.clean_text FROM documents d JOIN document_bodies b ON b.doc_id=d.id "
                        "WHERE d.source_type='float_window'").fetchone()
        c.close()
        check("入库正文与键入内容一致", bool(row) and "热键端到端测试" in row[0])
        time.sleep(1.2)
        check("成功后悬浮框已收起（前台不再是悬浮框）", fg_pid() != box.pid)
    finally:
        for p in procs:
            try:
                p.kill()
            except Exception:
                pass
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
