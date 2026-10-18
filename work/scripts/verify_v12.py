"""V0.12 验证：列表/检索支持分类(含子分类)、标签过滤，结果返回分类与标签。"""
import os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
tmp = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(tmp, "kb.db")
os.environ["LLM_PROVIDER"] = "mock"
os.environ["EMBEDDING_MODE"] = "mock"
os.environ["AUTO_PROCESS"] = "1"
from fastapi.testclient import TestClient
from app import main, db, manage

ok_n = fail_n = 0
def check(name, cond):
    global ok_n, fail_n
    print(("[PASS] " if cond else "[FAIL] ") + name)
    if cond: ok_n += 1
    else: fail_n += 1

c = TestClient(main.app)
docs = {
    "a": "向量数据库选型：对比 ChromaDB 与 Qdrant 的性能，向量数据库部署成本较低。",
    "b": "向量数据库索引结构：HNSW 与 IVF，向量数据库检索速度与召回权衡。",
    "c": "周末爬山计划：带上相机和保温杯，爬山看日出。",
}
ids = {}
for k, t in docs.items():
    r = c.post("/api/v1/documents/text", json={"text": t, "title": k}).json()
    ids[k] = r["data"]["doc_id"]
# 确保分类树有层级：把 a 手动归入 技术/数据库/选型，b 归入 技术/数据库/索引，c 归入 生活
for k, cp, tags in [("a", "技术/数据库/选型", ["向量库", "选型"]),
                    ("b", "技术/数据库/索引", ["向量库", "索引"]),
                    ("c", "生活/户外", ["爬山"])]:
    r = c.patch(f"/api/v1/documents/{ids[k]}", json={"category_path": cp, "tags": tags})
    check(f"手动修正 {k} 成功", r.status_code == 200)

# 列表过滤
def lst(**p): return c.get("/api/v1/documents", params=p).json()["data"]
d = lst(category_path="技术")
check("列表按父分类含子分类 = 2 篇", d["total"] == 2)
d = lst(category_path="技术/数据库/选型")
check("列表按叶子分类 = 1 篇", d["total"] == 1)
d = lst(tag="向量库")
check("列表按标签 = 2 篇", d["total"] == 2)
d = lst(tag="爬山")
check("列表按标签 爬山 = 1 篇", d["total"] == 1 and d["items"][0]["title"] == "c")
d = lst(category_path="技术", tag="索引")
check("分类+标签组合 = 1 篇", d["total"] == 1 and d["items"][0]["title"] == "b")
d = lst(category_path="不存在")
check("不存在的分类 = 0 篇", d["total"] == 0)
d = lst(category_path="技")
check("分类前缀不误匹配（'技' 不匹配 '技术'）", d["total"] == 0)
it = lst()["items"][0]
check("列表项含 category_path 与 tags 列表", "category_path" in it and isinstance(it["tags"], list))
check("列表项不含正文", "clean_text" not in it)

# 检索过滤
def srch(q, **f): return c.post("/api/v1/search", json={"query": q, "filters": f}).json()["data"]["results"]
r = srch("向量数据库")
check("无过滤命中 a、b", {x["title"] for x in r} >= {"a", "b"})
r = srch("向量数据库", category_path="技术/数据库/选型")
check("检索按分类过滤只剩 a", [x["title"] for x in r] == ["a"])
r = srch("向量数据库", category_path="技术")
check("检索按父分类含子分类 = a、b", {x["title"] for x in r} == {"a", "b"})
r = srch("向量数据库", tag="索引")
check("检索按标签过滤只剩 b", [x["title"] for x in r] == ["b"])
r = srch("向量数据库", category_path="生活")
check("过滤后无结果不报错", r == [])
r = srch("向量数据库", category_path="技术")
check("检索结果含 tags 与 category_path", all(isinstance(x.get("tags"), list) and x.get("category_path") for x in r))
check("检索结果 tags 内容正确", any("选型" in x["tags"] for x in r if x["title"] == "a"))

print(f"\n通过 {ok_n} / 失败 {fail_n}")
sys.exit(1 if fail_n else 0)
