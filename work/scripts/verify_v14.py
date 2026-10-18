"""V0.14 验证：用户手动修正分类反哺自动分类（corrections -> 候选置顶）。"""
import os, sys, tempfile
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["EMBEDDING_MODE"] = "mock"
os.environ["AUTO_PROCESS"] = "0"
from app import db, pipeline, manage, classify
from app.embedding import EmbeddingProvider

ok_n = fail_n = 0
def check(name, cond, detail=""):
    global ok_n, fail_n
    print(("[PASS] " if cond else "[FAIL] ") + name + (f" {detail}" if not cond else ""))
    if cond: ok_n += 1
    else: fail_n += 1


class FixedEmbedder(EmbeddingProvider):
    name = "fixed-4"
    dim = 4
    def embed(self, texts):
        out = []
        for t in texts:
            if "汽车" in t or "轿车" in t:
                out.append([1, 0, 0, 0])
            else:
                out.append([0, 0, 1, 0])
        m = np.array(out, dtype=np.float32)
        return m / np.linalg.norm(m, axis=1, keepdims=True)


class FirstCandLLM(pipeline.MockLLM):
    """总是选第一个候选；无候选则新建『通用/杂项』。用来证明候选排序受用户修正影响。"""
    def classify(self, text, summary, candidates):
        if candidates:
            return {"action": "assign", "category_path": candidates[0]["path"]}
        return {"action": "create", "new_category": "通用/杂项"}


emb, llm = FixedEmbedder(), FirstCandLLM()
conn = db.connect(os.path.join(tempfile.mkdtemp(), "v14.db"))

def add(text, title):
    d = db.add_document(conn, text, title, "paste")
    conn.commit()
    pipeline.process_document(conn, d, llm, embedder=emb)
    conn.commit()
    return d

def path_of(d):
    return conn.execute("SELECT category_path FROM documents WHERE id=?", (d,)).fetchone()[0]

a = add("轿车保养手册：定期更换机油", "轿车保养")
check("无修正时冷启动新建『通用/杂项』", path_of(a) == "通用/杂项", path_of(a))

manage.update_document(conn, a, category_path="交通/汽车")
conn.commit()
check("修正已记入 corrections",
      conn.execute("SELECT COUNT(*) FROM corrections WHERE doc_id=? AND kind='category'", (a,)).fetchone()[0] == 1)

vec = emb.embed(["汽车选购"])[0]
cc = classify.correction_candidates(conn, vec, emb.name)
check("相似文档的修正目标成为候选", [c["path"] for c in cc] == ["交通/汽车"] and cc[0]["user_corrected"], str(cc))

b = add("汽车选购指南：SUV 与轿车对比", "汽车选购")
check("相似新文档被归入用户修正过的分类", path_of(b) == "交通/汽车", path_of(b))

c = add("今天天气晴朗，适合散步", "天气")
vec_c = emb.embed(["今天天气晴朗，适合散步"])[0]
check("不相似文档不受修正影响（不产生修正候选）",
      classify.correction_candidates(conn, vec_c, emb.name) == [], str(classify.correction_candidates(conn, vec_c, emb.name)))

manage.update_document(conn, a, category_path="其他/杂")
conn.commit()
cc2 = classify.correction_candidates(conn, vec, emb.name)
check("旧修正被后续修正取代（只取最新生效）", [c["path"] for c in cc2] == ["其他/杂"], str(cc2))
d = add("汽车保险怎么买", "汽车保险")
check("新文档跟随最新修正", path_of(d) == "其他/杂", path_of(d))

os.environ["CORR_MIN_SIM"] = "1.1"
check("阈值过高时不引入修正候选", classify.correction_candidates(conn, vec, emb.name) == [])
del os.environ["CORR_MIN_SIM"]

print(f"\n通过 {ok_n} / 失败 {fail_n}")
sys.exit(1 if fail_n else 0)
