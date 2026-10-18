# 阶段契约 S04（精简版）：交付与复现

```yaml
stage_id: "S04"
stage_name: "交付与复现（精简版）：README 校准、一键启动、依赖锁定"
objective: "让评审者按 README 在 Windows 上能装起来、启动后端与悬浮框，并使文档中的验证数字与实际一致"
scope_in:
  - "work/README.md 回归数字与评估说明校准（19 脚本/307 项 → 23 脚本/352 项）"
  - "work/start_backend.bat、work/start_floatbox.bat 一键启动脚本"
  - "work/requirements.lock.txt（pip freeze 锁定当前已验证环境）"
scope_out:
  - "从零重建 venv 的全新机器复现（本机已有 venv，未在干净环境验证）"
  - "Docker 镜像构建验证（Dockerfile 仅保留，未在本阶段实测）"
  - "悬浮框第三方应用人工验收（S11，需用户本人）"
acceptance:
  - id: "AC-01"
    level: "MUST"
    requirement: "README 中的回归数字与最近一次一键回归一致"
    method: "INSPECT"
    expected: "README 写明 23 个脚本、352 项通过、0 失败"
  - id: "AC-02"
    level: "MUST"
    requirement: "start_backend.bat 的启动命令可拉起后端，健康检查与管理页返回 200"
    method: "RUN_COMMAND"
    expected: "/api/v1/health 返回 code 200；/ 返回 200（使用临时库与测试端口）"
  - id: "AC-03"
    level: "SHOULD"
    requirement: "依赖锁定文件已生成且不含密钥"
    method: "RUN_COMMAND"
    expected: "requirements.lock.txt 存在；密钥扫描无命中"
```
