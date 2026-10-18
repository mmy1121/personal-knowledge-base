"""V0.4/V0.5 混合检索验证：用确定性的固定向量测 RRF 融合、语义路、退化与过滤。

说明：Mock 哈希词袋无法做语义近义，因此这里用手工构造的固定向量验证"融合逻辑"，
真实语义效果需用 fastembed + bge-small-zh 单独做实验（见评估任务）。

运行（在 work 目录）：
    venv/Scripts/python.exe scripts/verify_v05.py
"""
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
_tmp = tempfile.mkdtemp(prefix="kb_verify5_")
os.environ["DB_PATH"] = os.path.join(_tmp, "api.db")

import numpy as np  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db, hybrid, pipeline  # noqa: E402
from app.embedding import EmbeddingProvider  # noqa: E402
from app.main import app  # noqa: E402

passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"[PASS] {name}")
    else:
        failed += 1
        print(f"[FAIL] {name} {detail}")


class FixedEmbedder(EmbeddingProvider):
    """按关键词映射到固定方向：汽车类/数据库类/其他。'汽车'与'轿车'语义同向但用词不同。"""
    name = "fixed-4"
    dim = 4

    def embed(self, texts):
        out = []
        for t in texts:
            if "汽车" in t or "轿车" in t:
                out.append([1, 0, 0, 0])
            elif "数据库" in t:
                out.append([0, 1, 0, 0])
            else:
                out.append([0, 0, 1, 0])
        m = np.array(out, dtype=np.float32)
        return m / np.linalg.norm(m, axis=1, keepdims=True)


emb = FixedEmbedder()
llm = pipeline.MockLLM()

# ---- 带向量的库 ----
conn = db.connect(os.path.join(_tmp, "vec.db"))
a = db.add_document(conn, "轿车保养手册：定期更换机油与滤芯", "轿车保养", "paste")
b = db.add_document(conn, "数据库选型对比：ChromaDB 与 Qdrant", "数据库选型", "float_window")
c = db.add_document(conn, "今天天气晴朗，适合散步", "天气", "paste")
conn.commit()
for d in (a, b, c):
    pipeline.process_document(conn, d, llm, embedder=emb)

res = hybrid.hybrid_search(conn, "汽车", embedder=emb)
ids = [r["id"] for r in res]
check("语义近义但用词不同：『汽车』命中『轿车』文档", a in ids, str(res))
check("该命中来自语义路", a in ids and "sem" in res[ids.index(a)]["via"])

res = hybrid.hybrid_search(conn, "ChromaDB", embedder=emb)
check("精确专有名词命中且排第一", res and res[0]["id"] == b, str(res))
check("专有名词命中含关键词路", res and "kw" in res[0]["via"])

res = hybrid.hybrid_search(conn, "数据库 ChromaDB", embedder=emb)
check("两路同时命中的文档得分更高并排第一", res and res[0]["id"] == b and set(res[0]["via"]) == {"kw", "sem"}, str(res))

res = hybrid.hybrid_search(conn, "汽车", source_type="float_window", embedder=emb)
check("来源类型过滤生效", all(r["source_type"] == "float_window" for r in res) and a not in [r["id"] for r in res])

res = hybrid.hybrid_search(conn, "汽车", time_from=time.time() + 3600, embedder=emb)
check("时间范围过滤生效（未来起点无结果）", res == [])

res = hybrid.hybrid_search(conn, "zzqqxx完全无关", embedder=emb)
check("无结果不报错", isinstance(res, list))
check("空查询返回空列表", hybrid.hybrid_search(conn, "   ", embedder=emb) == [])


class BrokenEmbedder(EmbeddingProvider):
    name = "fixed-4"
    dim = 4

    def embed(self, texts):
        raise RuntimeError("模型未下载")


res = hybrid.hybrid_search(conn, "ChromaDB", embedder=BrokenEmbedder())
check("向量路异常时退化为关键词检索不报错", res and res[0]["id"] == b and res[0]["via"] == ["kw"], str(res))

# ---- 未配向量的库 ----
conn2 = db.connect(os.path.join(_tmp, "novec.db"))
x = db.add_document(conn2, "纯关键词文档：向量数据库选型", None, "paste")
conn2.commit()
res = hybrid.hybrid_search(conn2, "向量数据库", embedder=emb)
check("未配向量自动退化为纯关键词", res and res[0]["id"] == x and res[0]["via"] == ["kw"], str(res))

# ---- API 层 ----
client = TestClient(app)
client.post("/api/v1/documents/text", json={"text": "数据库选型：ChromaDB 对比 Qdrant", "source_type": "float_window"})
client.post("/api/v1/documents/text", json={"text": "周末去爬山看日出", "source_type": "paste"})
r = client.post("/api/v1/search", json={"query": "ChromaDB"}).json()
check("API 检索返回统一格式与结果", r["code"] == 200 and len(r["data"]["results"]) >= 1, str(r))
r = client.post("/api/v1/search", json={"query": "ChromaDB", "filters": {"source_type": "paste"}}).json()
check("API 来源过滤生效", r["code"] == 200 and r["data"]["results"] == [], str(r))
r = client.post("/api/v1/search", json={"query": "ChromaDB", "source_type": "float_window"}).json()
check("API 来源过滤命中", len(r["data"]["results"]) == 1, str(r))
resp = client.post("/api/v1/search", json={"query": ""})
check("API 空查询 400", resp.status_code == 400)
r = client.post("/api/v1/search", json={"query": "完全不存在的词zzqq"}).json()
check("API 无结果不报错", r["code"] == 200 and r["data"]["results"] == [], str(r))

print(f"\n通过 {passed} / 失败 {failed}")
sys.exit(1 if failed else 0)
