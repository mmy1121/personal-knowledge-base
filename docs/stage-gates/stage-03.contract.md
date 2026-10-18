# 阶段契约 S03（精简版）：可靠性——备份与恢复

```yaml
stage_id: "S03"
stage_name: "可靠性（精简版）：备份与恢复"
objective: "提供可在后端运行时安全备份、带完整性校验、恢复前保留原库的备份/恢复工具，并纳入一键回归"
scope_in:
  - "work/scripts/kb_backup.py（backup / restore / check）"
  - "work/scripts/verify_backup.py"
  - "work/README.md 备份一节"
scope_out:
  - "定时自动备份、增量备份、加密备份"
  - "sqlite-vec 迁移"
acceptance:
  - id: "AC-01"
    level: "MUST"
    requirement: "备份为时间点快照，备份文件 integrity_check 通过，已存在的备份文件拒绝覆盖"
    method: "RUN_COMMAND"
    command: "cd work && venv\\Scripts\\python.exe scripts\\verify_backup.py"
    expected: "13 项通过，0 失败"
  - id: "AC-02"
    level: "MUST"
    requirement: "恢复后文档数与内容一致；覆盖恢复前保留原库副本；损坏备份被拒绝且目标库不变"
    method: "RUN_COMMAND"
    command: "同上"
    expected: "同上"
  - id: "AC-03"
    level: "MUST"
    requirement: "一键回归包含新脚本且 0 失败"
    method: "RUN_COMMAND"
    command: "cd work && venv\\Scripts\\python.exe scripts\\verify_all.py（不带 key）"
    expected: "退出码 0；脚本 21；失败 0"
  - id: "AC-04"
    level: "SHOULD"
    requirement: "仓库无密钥残留"
    method: "RUN_COMMAND"
    command: "grep -rIl -E \"sk-[A-Za-z0-9]{20,}\" 排除 venv/ext_dl/ext_data"
    expected: "无输出"
```
