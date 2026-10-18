"""评估实验 1b：simple 扩展（wangfenjin/simple v0.7.1）作为 FTS5 中文分词器的对照实验。

对比：
- jieba 预分词（本项目默认方案，OR 档查询）
- simple 扩展 + jieba_query（扩展内置 jieba 分词，需 dict 目录）
指标与语料复用 eval_fts_tokenizers.py：Recall@5、MRR。
运行：venv\\Scripts\\python.exe scripts\\eval_simple_ext.py [扩展目录]
扩展目录默认 ../ext_dl/simple_v071/libsimple-windows-x64，需含 simple.dll 与 dict 文件夹。
结果写入 ../评估结果_simple扩展对照.md
"""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_fts_tokenizers import CORPUS, QUERIES, build, search  # noqa: E402

GROUPS = ["2字词", ">=3字词", "英文专名"]


def load_simple(ext_dir: str):
    c = sqlite3.connect(":memory:")
    c.enable_load_extension(True)
    c.load_extension(os.path.join(ext_dir, "simple.dll"))
    c.enable_load_extension(False)
    dict_dir = os.path.join(ext_dir, "dict").replace("\\", "/")
    c.execute("SELECT jieba_dict(?)", (dict_dir,))
    c.execute("CREATE VIRTUAL TABLE f USING fts5(t, tokenize='simple')")
    for i, t in CORPUS.items():
        c.execute("INSERT INTO f(rowid, t) VALUES(?,?)", (i, t))
    return c


def search_simple(c, q: str):
    try:
        return [r[0] for r in c.execute(
            "SELECT rowid FROM f WHERE f MATCH jieba_query(?) ORDER BY bm25(f) LIMIT 5", (q,))]
    except sqlite3.OperationalError as e:
        print("查询失败:", q, e)
        return []


def score(run):
    out = {}
    for g in GROUPS + ["全部"]:
        qs = [x for x in QUERIES if g == "全部" or x[2] == g]
        hit, rr = 0, 0.0
        for q, rel, _ in qs:
            ids = run(q)
            if any(i in rel for i in ids):
                hit += 1
            for rank, i in enumerate(ids, 1):
                if i in rel:
                    rr += 1.0 / rank
                    break
        out[g] = (hit / len(qs), rr / len(qs), len(qs))
    return out


def main():
    ext_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(ROOT), "work", "ext_dl", "simple_v071", "libsimple-windows-x64")
    ext_dir = os.path.abspath(ext_dir)
    cj = build("jieba")
    res = {"jieba 预分词(本项目)": score(lambda q: search(cj, "jieba", q))}
    try:
        cs = load_simple(ext_dir)
        print("[PASS] simple.dll 加载成功，jieba 词典设置成功")
        res["simple 扩展 + jieba_query"] = score(lambda q: search_simple(cs, q))
    except Exception as e:  # 加载失败也要如实记录
        print("[FAIL] simple 扩展加载失败:", repr(e))
    names = list(res)
    lines = ["# 评估结果：simple 扩展对照实验", "",
             "语料 %d 篇，查询 %d 条。指标：Recall@5 / MRR。" % (len(CORPUS), len(QUERIES)), "",
             "| 分组(查询数) | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for g in GROUPS + ["全部"]:
        n = res[names[0]][g][2]
        cells = ["%.2f / %.2f" % res[m][g][:2] for m in names]
        lines.append("| %s(%d) | %s |" % (g, n, " | ".join(cells)))
    lines += ["", "说明：小语料仅做机制对比；simple 扩展为 v0.7.1 Windows x64，来源 GitHub Release，已校验 SHA256。"]
    out = "\n".join(lines)
    print(out)
    with open(os.path.join(os.path.dirname(ROOT), "评估结果_simple扩展对照.md"), "w", encoding="utf-8") as f:
        f.write(out + "\n")


if __name__ == "__main__":
    main()
