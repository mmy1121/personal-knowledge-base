"""知识库备份与恢复工具（基于 SQLite Backup API，可在后端运行时安全备份）。

用法（在 work 目录下，用 venv 解释器）：
    venv\Scripts\python.exe scripts\kb_backup.py backup  <源库> <备份文件>
    venv\Scripts\python.exe scripts\kb_backup.py restore <备份文件> <目标库>
    venv\Scripts\python.exe scripts\kb_backup.py check   <库文件>

设计理由：直接复制活动中的 .db 文件可能得到不一致的快照（尤其是 WAL 模式），
Backup API 会在事务一致的状态下拷贝；备份后与恢复前都执行 integrity_check，
通过后才算成功；恢复时若目标库已存在，先保留为 .bak，避免覆盖用户数据。
"""
import os
import shutil
import sqlite3
import sys
import time


def integrity_ok(path: str) -> bool:
    """返回 integrity_check 是否为 ok。"""
    conn = sqlite3.connect(path)
    try:
        return conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()


def counts(path: str) -> dict:
    """返回主要表的行数，用于备份前后比对。"""
    conn = sqlite3.connect(path)
    try:
        out = {}
        for t in ("documents", "document_bodies", "chunks", "categories", "tags", "corrections"):
            try:
                out[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except sqlite3.Error:
                out[t] = None
        return out
    finally:
        conn.close()


def backup(src: str, dst: str) -> dict:
    if not os.path.exists(src):
        raise FileNotFoundError(f"源库不存在：{src}")
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    if os.path.exists(dst):
        raise FileExistsError(f"备份文件已存在，拒绝覆盖：{dst}")
    s = sqlite3.connect(src)
    d = sqlite3.connect(dst)
    try:
        s.backup(d)  # 一致性快照
    finally:
        d.close()
        s.close()
    if not integrity_ok(dst):
        os.remove(dst)
        raise RuntimeError("备份文件 integrity_check 未通过，已删除")
    return counts(dst)


def restore(bak: str, target: str) -> dict:
    if not os.path.exists(bak):
        raise FileNotFoundError(f"备份文件不存在：{bak}")
    if not integrity_ok(bak):
        raise RuntimeError("备份文件 integrity_check 未通过，拒绝恢复")
    if os.path.exists(target):
        keep = f"{target}.{time.strftime('%Y%m%d%H%M%S')}.bak"
        shutil.copy2(target, keep)  # 保留原库，避免误覆盖
        print(f"原库已另存为：{keep}")
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    for ext in ("-wal", "-shm"):  # 清理旧库的 WAL 残留，避免与新库错配
        if os.path.exists(target + ext):
            os.remove(target + ext)
    s = sqlite3.connect(bak)
    d = sqlite3.connect(target)
    try:
        s.backup(d)
    finally:
        d.close()
        s.close()
    if not integrity_ok(target):
        raise RuntimeError("恢复后的库 integrity_check 未通过")
    return counts(target)


def main(argv):
    if len(argv) < 3 or argv[1] not in ("backup", "restore", "check"):
        print(__doc__)
        return 2
    cmd = argv[1]
    try:
        if cmd == "backup":
            print("备份完成：", backup(argv[2], argv[3]))
        elif cmd == "restore":
            print("恢复完成：", restore(argv[2], argv[3]))
        else:
            ok = integrity_ok(argv[2])
            print("integrity_check:", "ok" if ok else "FAILED", counts(argv[2]))
            return 0 if ok else 1
    except Exception as e:
        print(f"失败：{e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
