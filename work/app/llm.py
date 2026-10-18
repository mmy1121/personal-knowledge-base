"""真实 LLM Provider：DeepSeek / OpenAI 兼容 / Ollama。

关键决策：
- 只用标准库 urllib 发 HTTP，不引入 SDK 与 LangChain，链路窄、依赖轻。
- DeepSeek 与 OpenAI 兼容接口同属 /chat/completions 协议，共用一个实现，仅 base_url 与默认模型不同。
- Ollama 使用原生 /api/chat，stream=false。
- Prompt 模板独立成文件（app/prompts/*.txt），便于调优。
- JSON 解析容忍：markdown 代码块、JSON 前后夹带解释文字。
- 任何网络/解析错误都抛异常，由 pipeline 统一转 failed 并保留文档（数据先行）。
"""
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

from .pipeline import LLMProvider

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
MAX_INPUT_CHARS = 6000  # 送入 LLM 的正文上限，避免 token 超限


def load_prompt(name: str) -> str:
    return (PROMPT_DIR / f"{name}.txt").read_text(encoding="utf-8")


def parse_json(text: str):
    """稳健解析：先直接解析，再去代码块，再截取首个 {...} 或 [...]。"""
    s = (text or "").strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*(.*?)```", s, re.S)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        i, j = s.find(open_c), s.rfind(close_c)
        if 0 <= i < j:
            try:
                return json.loads(s[i:j + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError(f"LLM 输出无法解析为 JSON：{s[:80]}")


class ChatLLM(LLMProvider):
    """基于"一次对话返回文本"的通用实现；子类只需实现 _chat。"""

    def _chat(self, system: str, user: str) -> str:
        raise NotImplementedError

    def _ask_json(self, prompt_name: str, **fields):
        tpl = load_prompt(prompt_name)
        user = tpl
        for k, v in fields.items():
            user = user.replace("{" + k + "}", str(v))
        return parse_json(self._chat("你是严谨的知识库整理助手，只输出 JSON。", user))

    def summarize(self, text: str) -> dict:
        out = self._ask_json("summarize", text=text[:MAX_INPUT_CHARS])
        summary = str(out.get("summary", "")).strip()
        if not summary:
            raise ValueError("LLM 未返回摘要")
        kp = out.get("key_points") or []
        return {"summary": summary, "key_points": [str(x) for x in kp][:5]}

    def tag(self, text: str) -> list[str]:
        out = self._ask_json("tags", text=text[:MAX_INPUT_CHARS])
        arr = out.get("tags") if isinstance(out, dict) else out
        tags = [str(t).strip() for t in (arr or []) if str(t).strip()]
        if not tags:
            raise ValueError("LLM 未返回标签")
        return tags[:8]

    def classify(self, text: str, summary: str, candidates: list[dict]) -> dict:
        cand = "\n".join(f"- {c['path']}：{c.get('description') or ''}" for c in candidates) or "（暂无已有分类）"
        out = self._ask_json("classify", text=text[:2000], summary=summary, candidates=cand)
        if not isinstance(out, dict):
            raise ValueError("分类输出格式错误")
        return out


def _post_json(url: str, payload: dict, headers: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"LLM HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:200]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"LLM 网络错误: {e.reason}")


class OpenAICompatLLM(ChatLLM):
    """DeepSeek / OpenAI / 任意 OpenAI 兼容服务。"""

    def __init__(self, api_key: str, base_url: str, model: str, timeout: float = 60):
        if not api_key:
            raise RuntimeError("未配置 LLM_API_KEY")
        self.api_key, self.base_url, self.model, self.timeout = api_key, base_url.rstrip("/"), model, timeout

    def _chat(self, system: str, user: str) -> str:
        data = _post_json(
            f"{self.base_url}/chat/completions",
            {"model": self.model, "temperature": 0.2,
             "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            {"Authorization": f"Bearer {self.api_key}"}, self.timeout)
        return data["choices"][0]["message"]["content"]


class OllamaLLM(ChatLLM):
    def __init__(self, model: str, base_url: str = "http://127.0.0.1:11434", timeout: float = 120):
        self.model, self.base_url, self.timeout = model, base_url.rstrip("/"), timeout

    def _chat(self, system: str, user: str) -> str:
        data = _post_json(
            f"{self.base_url}/api/chat",
            {"model": self.model, "stream": False, "options": {"temperature": 0.2},
             "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            {}, self.timeout)
        return data["message"]["content"]


def build_llm(name: str) -> LLMProvider:
    """按 LLM_PROVIDER 构造（deepseek/openai/ollama）。mock 由 pipeline 自行处理。"""
    env = os.environ.get
    if name == "deepseek":
        return OpenAICompatLLM(env("LLM_API_KEY", ""), env("LLM_BASE_URL", "https://api.deepseek.com"),
                               env("LLM_MODEL", "deepseek-chat"))
    if name == "openai":
        return OpenAICompatLLM(env("LLM_API_KEY", ""), env("LLM_BASE_URL", "https://api.openai.com/v1"),
                               env("LLM_MODEL", "gpt-4o-mini"))
    if name == "ollama":
        return OllamaLLM(env("LLM_MODEL", "qwen2.5:7b"), env("LLM_BASE_URL", "http://127.0.0.1:11434"))
    raise RuntimeError(f"未知 LLM_PROVIDER={name}，可选 mock/deepseek/openai/ollama")
