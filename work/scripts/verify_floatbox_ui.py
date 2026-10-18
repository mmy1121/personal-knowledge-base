"""验证悬浮框窗口层（PySide6 离屏模式，不需要真实屏幕）。

覆盖：
1. 字数统计随输入更新
2. 提交成功：文本清空、绿色提示、窗口收起
3. 提交失败：文本保留、红色提示、窗口不收起（数据不丢）
4. Ctrl+Enter 触发存入（真实键盘事件）
5. Esc 收起
6. 热键解析；RegisterHotKey 真实注册/注销（冷门组合，验证 Win32 路径可用）
7. WM_HOTKEY 消息经 native event filter 触发回调
"""
import ctypes
import os
import sys
from ctypes import wintypes

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from floatbox import app as fb  # noqa: E402
from floatbox.submit import SubmitResult  # noqa: E402

passed = failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"[PASS] {name}")
    else:
        failed += 1
        print(f"[FAIL] {name}")


qapp = QApplication.instance() or QApplication([])
calls = []
mode = {"ok": True}


def fake_submit(text, *a, **k):
    calls.append(text)
    return SubmitResult(True, "已存入，后台分类中...", 1) if mode["ok"] else SubmitResult(False, "无法连接后端（文本已保留）")


fb.submit_text = fake_submit  # 替换窗口层引用的提交函数
box = fb.FloatBox()

box.show()
box.edit.setPlainText("复制来的文字")
check("字数统计更新", box.count.text() == "6 字")

# 成功
mode["ok"] = True
box.save()
check("成功后文本清空", box.edit.toPlainText() == "")
check("成功提示为绿色", "green" in box.status.styleSheet())
check("成功提示文案含已存入", "已存入" in box.status.text())
QTest.qWait(900)
check("成功后窗口自动收起", not box.isVisible())

# 失败
box.show()
box.edit.setPlainText("不能丢的内容")
mode["ok"] = False
box.save()
check("失败后文本保留", box.edit.toPlainText() == "不能丢的内容")
check("失败提示为红色", "red" in box.status.styleSheet())
QTest.qWait(900)
check("失败后窗口不收起", box.isVisible())

# Ctrl+Enter
mode["ok"] = True
n = len(calls)
box.edit.setFocus()
QTest.keyClick(box.edit, Qt.Key_Return, Qt.ControlModifier)
check("Ctrl+Enter 触发存入", len(calls) == n + 1 and calls[-1] == "不能丢的内容")

# Esc
box.show()
QTest.keyClick(box.edit, Qt.Key_Escape)
check("Esc 收起窗口", not box.isVisible())

# 热键解析
mods, vk = fb.parse_hotkey("ctrl+alt+k")
check("热键解析：修饰键含 ctrl+alt+NOREPEAT", mods == (0x0002 | 0x0001 | 0x4000))
check("热键解析：虚拟键码为 K", vk == ord("K"))

# 真实注册/注销（用冷门组合避免与已运行实例冲突）
user32 = ctypes.windll.user32
m2, v2 = fb.parse_hotkey("ctrl+alt+shift+f")
reg = bool(user32.RegisterHotKey(None, 0x7777, m2, v2))
check("RegisterHotKey 注册成功", reg)
if reg:
    check("UnregisterHotKey 注销成功", bool(user32.UnregisterHotKey(None, 0x7777)))

# WM_HOTKEY 经 native filter 触发回调
hit = []
flt = fb.HotkeyFilter(lambda: hit.append(1))
msg = wintypes.MSG()
msg.message = fb.WM_HOTKEY
msg.wParam = fb.HOTKEY_ID
handled, _ = flt.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(msg))
check("WM_HOTKEY 触发回调", handled and hit == [1])
msg.wParam = 1
handled, _ = flt.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(msg))
check("其他热键 ID 不触发", (not handled) and hit == [1])

print(f"\n通过 {passed} / 失败 {failed}")
sys.exit(1 if failed else 0)
