"""公开数据集评估：LCSTS（新浪微博短文本摘要，valid 集 8685 条带人工参考摘要）。
对比：Mock 基线（取正文开头 100 字） vs 真实 LLM（默认 deepseek，需环境变量 LLM_API_KEY，密钥不落盘）。
指标：字级 ROUGE-1 / ROUGE-2 的召回率与 F1。
说明：参考摘要平均仅约 18 字（标题式），而本系统摘要目标为 100~200 字，
因此以"召回率"为主指标（参考摘要的信息有多少被覆盖），F1 因长度差异偏低，仅作参考。
用法：LLM_API_KEY=xxx venv\\Scripts\\python.exe scripts\\eval_summary_lcsts.py [样本数]
"""
import os, sys, json, random
os.environ.setdefault("EMBEDDING_MODE", "mock")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from collections import Counter
from app import llm as llmmod, pipeline

N = int(sys.argv[1]) if len(sys.argv) > 1 else 50
provider = os.environ.get("LLM_PROVIDER_EVAL", "deepseek")
if provider != "mock" and not os.environ.get("LLM_API_KEY") and provider != "ollama":
    print("未设置 LLM_API_KEY，跳过"); sys.exit(0)

DATA = os.path.join(os.path.dirname(__file__), "..", "ext_data", "lcsts", "valid.jsonl")
rows = []
with open(DATA, encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        if len(d["text"]) >= 60 and d["summary"].strip():
            rows.append(d)
random.seed(42)
sample = random.sample(rows, N)


def ngrams(s, n):
    s = "".join(s.split())
    return Counter(s[i:i + n] for i in range(len(s) - n + 1))


def rouge(ref, hyp, n):
    r, h = ngrams(ref, n), ngrams(hyp, n)
    ov = sum((r & h).values())
    rec = ov / max(sum(r.values()), 1)
    pre = ov / max(sum(h.values()), 1)
    f1 = 2 * rec * pre / (rec + pre) if rec + pre else 0.0
    return rec, f1


def run(name, summarize):
    acc = {"r1": 0, "f1_1": 0, "r2": 0, "f1_2": 0, "len": 0}
    ok = 0
    for d in sample:
        try:
            s = summarize(d["text"])
        except Exception as e:
            print(f"[{name}] 调用失败: {type(e).__name__}")
            continue
        r1, f1 = rouge(d["summary"], s, 1)
        r2, f2 = rouge(d["summary"], s, 2)
        acc["r1"] += r1; acc["f1_1"] += f1; acc["r2"] += r2; acc["f1_2"] += f2
        acc["len"] += len(s); ok += 1
    ok = max(ok, 1)
    return {k: v / ok for k, v in acc.items()} | {"n": ok}


mock = pipeline.MockLLM()
res = [("Mock 基线（开头100字）", run("mock", lambda t: mock.summarize(t)["summary"]))]
if provider != "mock":
    real = llmmod.build_llm(provider)
    res.append((f"真实 LLM（{provider}）", run(provider, lambda t: real.summarize(t)["summary"])))

out = ["| 方法 | 有效样本 | ROUGE-1 召回 | ROUGE-1 F1 | ROUGE-2 召回 | ROUGE-2 F1 | 平均摘要长度(字) |",
       "|---|---|---|---|---|---|---|"]
for name, a in res:
    out.append(f"| {name} | {a['n']} | {a['r1']:.3f} | {a['f1_1']:.3f} | {a['r2']:.3f} | {a['f1_2']:.3f} | {a['len']:.0f} |")
print("\n".join(out))
with open(os.path.join(os.path.dirname(__file__), "..", "eval_summary_lcsts_result.md"), "w", encoding="utf-8") as f:
    f.write(f"# 公开数据集评估：LCSTS 摘要（valid 集抽样 {N} 条）\n\n" + "\n".join(out) +
            "\n\n说明：参考摘要平均约 18 字，系统摘要目标 100~200 字，故以召回率为主、F1 仅供参考。\n")
