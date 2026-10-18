"""V0.4 混合检索：关键词(AND 档 + OR 档) + 语义(向量余弦) 三路 -> RRF 融合。

关键决策：
- 只用排名不用分数：BM25 与余弦不在同一量纲，加权求和需要随数据漂移的系数。
- 未配向量 / 向量路异常时自动退化为纯关键词检索，不报错。
- 过滤（来源类型、时间范围）在融合后统一应用，保证两路口径一致。
"""
import os
from typing import Optional

from . import db, embedding, vectorstore


def _semantic_hits(conn, query: str, embedder, top_k: int = 50) -> list[dict]:
    """语义路；任何异常（模型未下载、维度不符等）都视为无语义结果。"""
    try:
        emb = embedder or embedding.get_embedder()
        if not vectorstore.has_vectors(conn, emb.name):
            return []
        qvec = emb.embed([query])[0]
        hits = vectorstore.search(conn, qvec, emb.name, top_k)
        # 相似度下限：没有下限时，语义路总会返回 Top-K，把完全不相关的文档混进结果。
        # 阈值与模型相关（Mock 哈希词袋无相关词时余弦为 0；真实 BGE 模型需用 eval_semantic.py 标定），
        # 因此可用 SEM_MIN_SIM 配置。
        # Mock 只有 256 个哈希桶，无关文本撞桶即可产生 0.1~0.2 的余弦，故默认阈值更高
        # 真实模型（bge-small-zh）经 scripts/calibrate_sem_threshold.py 标定：
        # 阈值 0.4 时相关保留 100%、无关误入 4%，故默认 0.4
        default_floor = "0.3" if emb.name.startswith("mock") else "0.4"
        floor = float(os.environ.get("SEM_MIN_SIM", default_floor))
        return [h for h in hits if h["score"] >= floor]
    except Exception:
        return []


def hybrid_search(conn, query: str, limit: int = 10, k: int = 60,
                  source_type: Optional[str] = None,
                  time_from: Optional[float] = None, time_to: Optional[float] = None,
                  embedder=None, category_path: Optional[str] = None,
                  tag: Optional[str] = None) -> list[dict]:
    terms = list(dict.fromkeys(db.tokenize(query)))
    if not terms:
        return []
    kw_lists = [db._rank_ids(conn, db._fts_query(terms, "AND"), 50)]
    if len(terms) > 1:
        kw_lists.append(db._rank_ids(conn, db._fts_query(terms, "OR"), 50))
    sem = _semantic_hits(conn, query, embedder)
    sem_ids = [h["doc_id"] for h in sem]
    sem_text = {h["doc_id"]: h["text"] for h in sem}

    scores: dict[int, float] = {}
    via: dict[int, set] = {}
    for name, ids in [("kw", kw_lists[0])] + ([("kw", kw_lists[1])] if len(kw_lists) > 1 else []) \
            + [("sem", sem_ids)]:
        for rank, d in enumerate(ids, start=1):
            scores[d] = scores.get(d, 0.0) + 1.0 / (k + rank)
            via.setdefault(d, set()).add(name)

    out = []
    for d in sorted(scores, key=scores.get, reverse=True):
        r = conn.execute(
            "SELECT d.id, d.title, d.summary, d.source_type, d.status, d.category_path, d.created_at,"
            " b.clean_text FROM documents d JOIN document_bodies b ON b.doc_id=d.id WHERE d.id=?",
            (d,)).fetchone()
        if not r:
            continue
        if source_type and r["source_type"] != source_type:
            continue
        if time_from is not None and (r["created_at"] or 0) < time_from:
            continue
        if time_to is not None and (r["created_at"] or 0) > time_to:
            continue
        # 分类过滤：路径前缀匹配，含子分类（'技术' 匹配 '技术' 与 '技术/数据库'）
        if category_path:
            cp = category_path.strip("/")
            rp = r["category_path"] or ""
            if not (rp == cp or rp.startswith(cp + "/")):
                continue
        doc_tags = [t[0] for t in conn.execute(
            "SELECT t.name FROM document_tags dt JOIN tags t ON t.id=dt.tag_id "
            "WHERE dt.doc_id=? ORDER BY t.name", (d,))]
        if tag and tag not in doc_tags:
            continue
        snippet = db.make_snippet(r["clean_text"], terms) if "kw" in via[d] \
            else (sem_text.get(d) or r["clean_text"])[:120]
        out.append({"id": r["id"], "title": r["title"], "summary": r["summary"],
                    "source_type": r["source_type"], "status": r["status"],
                    "category_path": r["category_path"], "tags": doc_tags,
                    "score": round(scores[d], 6),
                    "via": sorted(via[d]), "snippet": snippet})
        if len(out) >= limit:
            break
    return out
