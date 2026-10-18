# -*- coding: utf-8 -*-
"""探测脚本：验证 sqlite-vec 加载、向量 KNN、FTS5 中文分词方案（trigram / jieba 预分词）。"""
import sqlite3
import struct
import sys

import jieba
import sqlite_vec


def ser(v):
    """float32 列表序列化为 BLOB。"""
    return struct.pack(f"{len(v)}f", *v)


def test_vec():
    db = sqlite3.connect(":memory:")
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)
    ver = db.execute("select vec_version()").fetchone()[0]
    print("sqlite-vec version:", ver)
    db.execute("create virtual table v using vec0(embedding float[4])")
    rows = {1: [1, 0, 0, 0], 2: [0, 1, 0, 0], 3: [0.9, 0.1, 0, 0]}
    for k, vec in rows.items():
        db.execute("insert into v(rowid, embedding) values (?, ?)", (k, ser(vec)))
    res = db.execute(
        "select rowid, distance from v where embedding match ? and k = 2 order by distance",
        (ser([1, 0, 0, 0]),),
    ).fetchall()
    print("KNN result:", res)
    assert [r[0] for r in res] == [1, 3], "KNN 排序异常"
    print("[OK] sqlite-vec 加载与 KNN 正常")


def test_fts():
    docs = ["向量数据库选型对比", "FastAPI 后端开发笔记", "分类与标签的自动整理"]
    # 方案 A：trigram
    db = sqlite3.connect(":memory:")
    db.execute("create virtual table t using fts5(body, tokenize='trigram')")
    for d in docs:
        db.execute("insert into t(body) values (?)", (d,))
    for q in ["向量数据库", "向量", "FastAPI"]:
        n = len(db.execute("select rowid from t where t match ?", (f'"{q}"',)).fetchall())
        print(f"trigram  查询 {q!r}: {n} 条")
    # 方案 B：jieba 预分词 + unicode61
    db2 = sqlite3.connect(":memory:")
    db2.execute("create virtual table t using fts5(body, tokenize='unicode61')")
    for d in docs:
        db2.execute("insert into t(body) values (?)", (" ".join(jieba.cut_for_search(d)),))
    for q in ["向量数据库", "向量", "FastAPI", "分类"]:
        toks = [w for w in jieba.cut_for_search(q) if w.strip()]
        expr = " OR ".join(f'"{w}"' for w in toks)
        n = len(db2.execute("select rowid from t where t match ?", (expr,)).fetchall())
        print(f"jieba    查询 {q!r} -> {toks}: {n} 条")


if __name__ == "__main__":
    print("python", sys.version.split()[0], "sqlite", sqlite3.sqlite_version)
    test_vec()
    test_fts()
