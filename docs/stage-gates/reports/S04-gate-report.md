# S04 阶段验收报告（精简版）：交付与复现

- 验证时间：2026-10-18
- 环境：Windows 11 / Python 3.12.10；无 Git 仓库
- independent_verification: **false**（同一工作流自行运行并读取产物）

| 编号 | 级别 | 结果 | 证据 |
|---|---|---|---|
| AC-01 README 回归数字与最近一次一键回归一致 | MUST | PASS | README 已写明“23 个脚本、352 项通过、0 失败”，与 S03 第 3 轮及 S02 改动 classify.py 后的无 key 回归一致（均为 23 脚本 / 352 项 / 0 失败） |
| AC-02 start_backend.bat 的启动命令可拉起后端，健康检查与管理页返回 200 | MUST | PASS | 使用临时库与测试端口：/api/v1/health 返回 code 200，管理页 / 返回 200。注意：验证用的是脚本中的同一条 uvicorn 命令，并非双击运行 .bat；日志末尾的端口占用报错来自重复启动的第二个实例，不影响结论 |
| AC-03 依赖锁定文件已生成且不含密钥 | SHOULD | PASS | work/requirements.lock.txt（118 行，pip freeze 自当前已验证 venv）；密钥扫描无命中 |

## 说明
- 本阶段新增：start_backend.bat、start_floatbox.bat、requirements.lock.txt，并校准 README 的回归数字与脚本清单。
- start_floatbox.bat 仅创建并写入 README，未在本阶段自动化验证；悬浮框的自动化 E2E 已在先前阶段通过，第三方应用人工验收仍属 S11。

## 范围外 / 局限
1. 未在干净机器或全新 venv 上按 README 从零复现安装；锁定文件来自本机已有 venv，可复现性只有间接依据。
2. Dockerfile 与 docker-compose.yml 仅保留，未在本阶段构建实测。
3. requirements.lock.txt 为 Windows / Python 3.12 环境的完整 freeze，含若干评估期依赖（如 matplotlib、ir_datasets），体积较大，跨平台不保证可直接安装。

## 遗留
1. DEBT-04（P2）：DeepSeek key 多次出现在聊天记录中，演示或提交后应到服务商后台作废并重新生成。
2. 悬浮框在第三方应用中的人工验收仍需用户本人完成（S11）。
3. 全新环境复现与 Docker 构建验证待补（可选）。
