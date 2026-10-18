"""真实 LLM 联调：需环境变量 LLM_API_KEY；未设置则跳过。
覆盖：deepseek 路径、openai 兼容路径（base_url 指向 DeepSeek）、完整流水线(摘要/标签/分类)。
Ollama 需本机服务，设置 OLLAMA_MODEL 才会实测，否则跳过。密钥不写入任何文件。"""
import os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
key = os.environ.get("LLM_API_KEY", "")
if not key:
    print("未设置 LLM_API_KEY，跳过真实联调"); print("通过 0 / 失败 0"); sys.exit(0)
tmp = tempfile.mkdtemp()
os.environ["EMBEDDING_MODE"] = "mock"
from app import llm, db, pipeline

ok_n = fail_n = 0
def check(name, cond, detail=""):
    global ok_n, fail_n
    print(("[PASS] " if cond else "[FAIL] ") + name + (f" {detail}" if not cond else ""))
    if cond: ok_n += 1
    else: fail_n += 1

TEXT = ("向量数据库用于存储和检索高维向量。ChromaDB、Qdrant、sqlite-vec 是常见方案，"
        "个人知识库场景数据量小，sqlite-vec 与 SQLite 同文件部署最轻量。检索时常用余弦相似度，"
        "并与 BM25 关键词检索通过 RRF 融合。")
providers = {
    "deepseek": llm.build_llm("deepseek"),
    "openai兼容": llm.OpenAICompatLLM(key, "https://api.deepseek.com", "deepseek-chat"),
}
if os.environ.get("OLLAMA_MODEL"):
    providers["ollama"] = llm.OllamaLLM(os.environ["OLLAMA_MODEL"])
for name, p in providers.items():
    try:
        s = p.summarize(TEXT)
        check(f"{name} 摘要非空", len(s["summary"]) >= 20, s)
        check(f"{name} 要点 1~5 条", 1 <= len(s["key_points"]) <= 5, s)
        t = p.tag(TEXT)
        check(f"{name} 标签 1~8 个", 1 <= len(t) <= 8, t)
        c = p.classify(TEXT, s["summary"], [{"path": "生活/户外", "description": "爬山旅行"}])
        check(f"{name} 分类返回合法 action", c.get("action") in ("assign", "create"), c)
        if c.get("action") == "create":
            check(f"{name} 新建分类为父/子形式", "/" in c.get("new_category", ""), c)
    except Exception as e:
        check(f"{name} 调用", False, repr(e))

# 完整流水线（真实 LLM + Mock Embedding）
conn = db.connect(os.path.join(tmp, "kb.db"))
ids = [db.add_document(conn, t, n, "paste") for n, t in [
    ("向量库", TEXT),
    ("爬山", "周末去香山爬山，带上相机和保温杯，山顶看日出，下山后在山脚吃了农家菜。"),
    ("RRF", "RRF 倒数排名融合只使用排名而非分数，k 取 60，可融合 BM25 与余弦相似度两路结果。")]]
conn.commit()
for d in ids:
    st = pipeline.process_document(conn, d, providers["deepseek"])
    row = conn.execute("SELECT status,summary,category_path,tags,error_message FROM documents WHERE id=?", (d,)).fetchone()
    check(f"流水线 doc{d} stored", st == "stored" and row["summary"] and row["category_path"], dict(row))
    print("   ", row["category_path"], "|", row["tags"])
paths = [r[0] for r in conn.execute("SELECT category_path FROM documents ORDER BY id")]
check("两篇技术文档同类或同父，爬山不同父", paths[0].split("/")[0] == paths[2].split("/")[0] != paths[1].split("/")[0], paths)
print(f"\n通过 {ok_n} / 失败 {fail_n}")
sys.exit(1 if fail_n else 0)
