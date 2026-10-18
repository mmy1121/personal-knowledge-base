"""V0.4 验证脚本：Mock Embedding 确定性、切片向量化入库、向量检索、失败不丢数据、重试跳过、级联删除。

运行（在 work 目录下）：
    venv/Scripts/python.exe scripts/verify_v04.py
使用临时数据库，不污染 data/kb.db。
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402

from app import db, embedding, pipeline, vectorstore  # noqa: E402

passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"[PASS] {name}")
    else:
        failed += 1
        print(f"[FAIL] {name} {detail}")


class BadEmbedder(embedding.EmbeddingProvider):
    name = "bad"
    dim = 8

    def embed(self, texts):
        raise RuntimeError("模拟 Embedding 故障")


tmp = tempfile.mkdtemp(prefix="kb_v04_")
path = os.path.join(tmp, "kb.db")
mock = embedding.MockEmbedding()

# 1. Embedding 基本性质
a = mock.embed(["向量数据库选型对比"])
b = embedding.MockEmbedding().embed(["向量数据库选型对比"])
check("Mock 确定性（不同实例结果一致）", np.array_equal(a, b))
check("向量已 L2 归一化", abs(float(np.linalg.norm(a[0])) - 1.0) < 1e-5)
check("维度正确", a.shape == (1, mock.dim))
sim_same = float((mock.embed(["向量数据库选型"]) @ mock.embed(["向量数据库选型"]).T)[0, 0])
sim_rel = float((mock.embed(["向量数据库选型"]) @ mock.embed(["向量数据库对比"]).T)[0, 0])
sim_un = float((mock.embed(["向量数据库选型"]) @ mock.embed(["今天天气晴朗适合郊游"]).T)[0, 0])
check("相同文本相似度为 1", abs(sim_same - 1.0) < 1e-5)
check("词面相关 > 无关", sim_rel > sim_un, f"rel={sim_rel} un={sim_un}")

with db.session(path) as conn:
    # 2. 流水线：向量化入库
    d1 = db.add_document(conn, "向量数据库选型：对比 ChromaDB 与 Qdrant 的性能和部署成本。")
    d2 = db.add_document(conn, "周末郊游计划：带上帐篷和野餐垫，去湖边看日落。")
    llm = pipeline.MockLLM()
    check("处理成功转 stored", pipeline.process_document(conn, d1, llm, embedder=mock) == "stored")
    pipeline.process_document(conn, d2, llm, embedder=mock)
    n = conn.execute("SELECT COUNT(*) FROM chunks WHERE doc_id=?", (d1,)).fetchone()[0]
    check("切片写入 chunks", n >= 1)
    r = conn.execute("SELECT embed_model, embed_dim, length(embedding) AS l FROM chunks WHERE doc_id=?",
                     (d1,)).fetchone()
    check("记录 embed_model/维度", r["embed_model"] == mock.name and r["embed_dim"] == mock.dim)
    check("向量以 float16 存储", r["l"] == mock.dim * 2)

    # 3. 向量检索
    res = vectorstore.search(conn, mock.embed(["ChromaDB Qdrant 向量数据库"])[0], mock.name)
    check("语义路命中目标且排第一", bool(res) and res[0]["doc_id"] == d1)
    check("同一文档只保留一条", len({x["doc_id"] for x in res}) == len(res))
    check("换模型名不混用", vectorstore.search(conn, mock.embed(["向量"])[0], "other-model") == [])
    check("维度不一致返回空而非报错", vectorstore.search(conn, np.ones(7, dtype=np.float32), mock.name) == [])
    check("has_vectors 判断", vectorstore.has_vectors(conn, mock.name)
          and not vectorstore.has_vectors(conn, "other-model"))

    # 4. Embedding 故障：文档不丢，摘要保留，可检索，可重试
    d3 = db.add_document(conn, "Embedding 故障场景：正文必须保留并可被关键词检索。")
    llm3 = pipeline.MockLLM()
    check("Embedding 故障转 failed 不抛异常",
          pipeline.process_document(conn, d3, llm3, embedder=BadEmbedder()) == "failed")
    row = conn.execute("SELECT status, error_message, summary FROM documents WHERE id=?", (d3,)).fetchone()
    check("失败原因被记录", "Embedding" in (row["error_message"] or "") or "故障" in (row["error_message"] or ""))
    check("摘要步骤已保留（每步独立提交）", bool(row["summary"]))
    check("失败时无切片残留", conn.execute("SELECT COUNT(*) FROM chunks WHERE doc_id=?", (d3,)).fetchone()[0] == 0)
    check("失败文档关键词检索仍可用", any(x["id"] == d3 for x in db.search(conn, "故障场景")))
    # 加入标签/分类步骤后，重试时分类等未完成步骤会合理地再调用 LLM；
    # 这里只断言"已完成的摘要步骤"不被重复调用
    summarize_calls = []
    _orig_summarize = llm3.summarize
    llm3.summarize = lambda text: (summarize_calls.append(1), _orig_summarize(text))[1]
    check("重试成功转 stored", pipeline.process_document(conn, d3, llm3, embedder=mock) == "stored")
    check("重试不重复调用 LLM 摘要", len(summarize_calls) == 0)
    check("重试后清空错误",
          conn.execute("SELECT error_message FROM documents WHERE id=?", (d3,)).fetchone()[0] is None)
    check("重试后向量写入", conn.execute("SELECT COUNT(*) FROM chunks WHERE doc_id=?", (d3,)).fetchone()[0] >= 1)

    # 5. 已向量化的文档重处理不重复写入
    before = conn.execute("SELECT COUNT(*) FROM chunks WHERE doc_id=?", (d1,)).fetchone()[0]
    pipeline.process_document(conn, d1, llm, embedder=mock)
    after = conn.execute("SELECT COUNT(*) FROM chunks WHERE doc_id=?", (d1,)).fetchone()[0]
    check("重处理不产生重复切片", before == after)

    # 6. 长文本多切片
    long_text = "\n".join(f"第{i}段：这是用于测试切片的内容，包含关键词编号{i}。" * 4 for i in range(60))
    d4 = db.add_document(conn, long_text, title="长文")
    pipeline.process_document(conn, d4, llm, embedder=mock)
    cnt = conn.execute("SELECT COUNT(*) FROM chunks WHERE doc_id=?", (d4,)).fetchone()[0]
    check("长文本被切成多片并全部向量化", cnt > 1, f"cnt={cnt}")
    res = vectorstore.search(conn, mock.embed(["切片 关键词"])[0], mock.name)
    check("长文档在结果中只出现一次", sum(1 for x in res if x["doc_id"] == d4) == 1)

    # 7. 级联删除
    db.delete_document(conn, d1)
    check("删除文档后切片向量无残留",
          conn.execute("SELECT COUNT(*) FROM chunks WHERE doc_id=?", (d1,)).fetchone()[0] == 0)

print(f"\n通过 {passed} / 失败 {failed}")
sys.exit(1 if failed else 0)
