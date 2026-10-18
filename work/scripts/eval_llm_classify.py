"""评估：真实 LLM 的分类准确率（今日头条数据集，用其官方类别作标准答案）。

用法（密钥只从环境变量读取，不落盘）：
    set LLM_API_KEY=你的key
    venv\\Scripts\\python.exe -I scripts\\eval_llm_classify.py [每类样本数，默认4]

做法：每类随机抽 N 条（标题+关键词），候选分类固定为 15 个中文类别，
调用 llm.classify，比较返回的 category_path 与标准答案。
输出：总体准确率、各类准确率、混淆最多的类别对，写入 eval_llm_classify_result.md。
"""
import os
import random
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from app import llm  # noqa: E402

DATA = os.path.join(ROOT, "ext_data", "toutiao_cat_data.txt")
CODE2NAME = {
    "news_story": "故事", "news_culture": "文化", "news_entertainment": "娱乐",
    "news_sports": "体育", "news_finance": "财经", "news_house": "房产",
    "news_car": "汽车", "news_edu": "教育", "news_tech": "科技",
    "news_military": "军事", "news_travel": "旅游", "news_world": "国际",
    "stock": "股票", "news_agriculture": "农业", "news_game": "电竞游戏",
}


def main():
    per = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    key = os.environ.get("LLM_API_KEY", "")
    if not key:
        print("请先设置环境变量 LLM_API_KEY"); sys.exit(1)
    provider = llm.build_llm(os.environ.get("LLM_PROVIDER", "deepseek"))

    random.seed(7)
    bucket = defaultdict(list)
    with open(DATA, encoding="utf-8") as f:
        for line in f:
            p = line.rstrip("\n").split("_!_")
            if len(p) >= 4 and p[2] in CODE2NAME:
                bucket[p[2]].append((p[3], p[4] if len(p) > 4 else ""))
    samples = []
    for code, rows in bucket.items():
        rows = [r for r in rows if len(r[0]) >= 8]
        for title, kw in random.sample(rows, per):
            samples.append((CODE2NAME[code], f"{title}。关键词：{kw}"))
    cands = [{"path": n, "description": ""} for n in CODE2NAME.values()]

    def run(item):
        truth, text = item
        try:
            out = provider.classify(text, text[:100], cands)
            return truth, out.get("category_path") or out.get("new_category") or "", None
        except Exception as e:  # 网络/解析失败单独统计，不算分类错误
            return truth, "", str(e)[:80]

    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(run, samples))

    valid = [r for r in res if r[2] is None]
    errors = [r for r in res if r[2] is not None]
    hit = sum(1 for t, p, _ in valid if p == t)
    per_cls, conf = defaultdict(lambda: [0, 0]), Counter()
    for t, p, _ in valid:
        per_cls[t][1] += 1
        if p == t:
            per_cls[t][0] += 1
        else:
            conf[(t, p)] += 1
    lines = [f"# 评估结果：LLM 分类准确率（{os.environ.get('LLM_PROVIDER', 'deepseek')}）", "",
             f"样本 {len(samples)} 条（每类 {per} 条），有效 {len(valid)}，调用失败 {len(errors)}。",
             f"**总体准确率：{hit}/{len(valid)} = {hit / max(1, len(valid)):.3f}**", "",
             "| 类别 | 正确/样本 |", "|---|---|"]
    for n in CODE2NAME.values():
        a, b = per_cls[n]
        lines.append(f"| {n} | {a}/{b} |")
    lines += ["", "混淆最多的类别对（标准答案 → 预测）：", ""]
    for (t, p), c in conf.most_common(8):
        lines.append(f"- {t} → {p or '（空）'}：{c} 次")
    lines += ["", "说明：头条类别本身有重叠（如 股票/财经、故事/文化），标准答案存在歧义，准确率为保守估计。"]
    out_path = os.path.join(ROOT, "eval_llm_classify_result.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"accuracy={hit}/{len(valid)} errors={len(errors)} -> {out_path}")


if __name__ == "__main__":
    main()
