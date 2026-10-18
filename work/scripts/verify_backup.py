"""备份/恢复验证：Backup API 一致性、integrity_check、拒绝覆盖、损坏备份拒绝恢复、恢复后可检索。

运行（work 目录）：venv\Scripts\python.exe scripts\verify_backup.py
全程使用临时目录，不触碰 data/kb.db，不调用任何 LLM。
"""
import os
import shutil
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from app import db  # noqa: E402
import kb_backup  # noqa: E402

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    passed += bool(cond)
    failed += (not cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {detail if not cond else ''}")


tmp = tempfile.mkdtemp(prefix="kb_backup_")
try:
    src = os.path.join(tmp, "kb.db")
    bak = os.path.join(tmp, "out", "kb.bak.db")
    tgt = os.path.join(tmp, "restored", "kb.db")

    # 造数据；保持一个连接打开，模拟"后端运行中"备份
    live = db.connect(src)
    ids = [db.add_document(live, t, None, "paste") for t in
           ["向量数据库选型对比 ChromaDB", "周末爬山看日出", "FastAPI 路由笔记"]]
    live.commit()

    c = kb_backup.backup(src, bak)
    check("备份成功且文档数为 3", c["documents"] == 3, str(c))
    check("备份文件 integrity_check 通过", kb_backup.integrity_ok(bak))

    # 备份后源库继续写入，不影响备份内容
    db.add_document(live, "备份之后新增的文档", None, "paste")
    live.commit()
    check("备份是时间点快照（不含之后新增）", kb_backup.counts(bak)["documents"] == 3)
    live.close()

    try:
        kb_backup.backup(src, bak)
        check("已存在的备份文件拒绝覆盖", False)
    except FileExistsError:
        check("已存在的备份文件拒绝覆盖", True)

    try:
        kb_backup.backup(os.path.join(tmp, "nope.db"), os.path.join(tmp, "x.db"))
        check("源库不存在时报错", False)
    except FileNotFoundError:
        check("源库不存在时报错", True)

    # 恢复到全新位置
    r = kb_backup.restore(bak, tgt)
    check("恢复后文档数一致", r["documents"] == 3, str(r))
    conn = db.connect(tgt)
    try:
        n = conn.execute("SELECT COUNT(*) FROM documents WHERE id IN (?,?,?)", ids).fetchone()[0]
        check("恢复后原文档 id 均存在", n == 3)
        row = conn.execute("SELECT clean_text FROM document_bodies WHERE doc_id=?", (ids[0],)).fetchone()
        check("恢复后正文可读", row is not None and "ChromaDB" in row[0])
    finally:
        conn.close()

    # 恢复到已存在的库：原库另存 .bak，不丢
    before = len([f for f in os.listdir(os.path.dirname(tgt)) if f.endswith(".bak")])
    kb_backup.restore(bak, tgt)
    after = len([f for f in os.listdir(os.path.dirname(tgt)) if f.endswith(".bak")])
    check("覆盖恢复前保留原库副本", after == before + 1)

    # 损坏备份：拒绝恢复且不改动目标库
    bad = os.path.join(tmp, "bad.db")
    with open(bad, "wb") as f:
        f.write(b"this is not a sqlite database" * 100)
    size_before = os.path.getsize(tgt)
    try:
        kb_backup.restore(bad, tgt)
        check("损坏备份拒绝恢复", False)
    except Exception:
        check("损坏备份拒绝恢复", True)
    check("拒绝恢复后目标库未被改动", os.path.getsize(tgt) == size_before
          and kb_backup.integrity_ok(tgt))

    # 命令行入口
    check("CLI check 退出码 0", kb_backup.main(["x", "check", tgt]) == 0)
    check("CLI 参数不足返回 2", kb_backup.main(["x"]) == 2)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n通过 {passed} / 失败 {failed}")
sys.exit(1 if failed else 0)
