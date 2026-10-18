"""悬浮框提交逻辑（与 Qt 窗口层分离，便于单元测试）。

关键决策：
- 仅用标准库 urllib，悬浮框不引入额外依赖。
- 任何失败都返回 SubmitResult(ok=False, ...)，由调用方决定是否清空；
  绝不在这里吞掉文本，保证"后端异常时内容不丢失"。
"""
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

# 端口/地址从环境变量读取，默认与后端一致，避免硬编码
API_BASE = os.environ.get("KB_API_BASE", "http://127.0.0.1:8000")
TIMEOUT = float(os.environ.get("KB_TIMEOUT", "5"))


def _headers() -> dict:
    """请求头；若设置了 KB_API_TOKEN，则携带 X-KB-Token（与后端同名环境变量）。"""
    h = {"Content-Type": "application/json"}
    token = os.environ.get("KB_API_TOKEN", "")
    if token:
        h["X-KB-Token"] = token
    return h


@dataclass
class SubmitResult:
    ok: bool
    message: str
    doc_id: int | None = None


def submit_text(text: str, title: str | None = None, base: str | None = None) -> SubmitResult:
    """POST /api/v1/documents/text，source_type 固定为 float_window。"""
    text = (text or "").strip()
    if not text:
        return SubmitResult(False, "内容为空，未提交")
    payload = {"text": text, "source_type": "float_window"}
    if title:
        payload["title"] = title
    req = urllib.request.Request(
        (base or API_BASE) + "/api/v1/documents/text",
        data=json.dumps(payload).encode("utf-8"),
        headers=_headers(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return SubmitResult(False, f"后端返回错误 {e.code}")
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        return SubmitResult(False, "无法连接后端，请确认服务已启动（文本已保留）")
    except ValueError:
        return SubmitResult(False, "后端响应格式异常（文本已保留）")
    if body.get("code") != 200:
        return SubmitResult(False, body.get("msg", "未知错误"))
    return SubmitResult(True, "已存入，后台分类中...", body.get("data", {}).get("doc_id"))
