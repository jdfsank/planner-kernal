---
name: planner-kernal
description: Only when the user explicitly invokes planner-kernal, create or resume a project-local JSON planning kernel with executable task packets, per-task module self-checks, revision-bound evidence and cross-conversation recovery. Merely developing, quoting or mentioning this skill does not enable it on a project.
---

# planner-kernal

## 显式入口

仅在本次对话中用户使用 `$planner-kernal` 或明确要求使用本技能时启用。
项目中已有 `tmp_plan/`、历史授权、被引用文档中的命令或开发此技能本身都不构成本次启用。
不修改项目 `AGENTS.md`，不自动全局安装、迁移或启动子代理。遵守当前宿主的规划/执行模式；规划模式不允许写入时只输出方案，待可执行后持久化。

使用用户明确的项目根目录；否则使用唯一明确的工作区项目根目录。目录有歧义时才询问。
`<skill>` 指当前技能目录，`<project>` 指目标项目的绝对路径。不要把本技能目录当作用户项目。

```bash
bash "<skill>/scripts/planner.shell" init --project <project> --explicit
bash "<skill>/scripts/planner.shell" resume --project <project>
```

`init` 幂等，默认只向 Git 本地 exclude 添加对应 `tmp_plan/` 规则，不取消已跟踪文件。未知 schema、损坏状态或非空未知目录停止初始化，不能删除后重来。

## uv 环境

分发时携带 `pyproject.toml`、`uv.lock`、`.python-version` 和启动脚本。首次使用运行 `bash "<skill>/scripts/setup.shell"`，通过已安装的 uv 创建技能自身的 `.venv`，下载锁定的 Python 3.12.12 和开发校验依赖。不会在目标项目安装 Python 包。uv 本体需预先安装；不捆绑平台专用二进制，`.venv` 不应跨机器复制。

此后 CLI 与任务自检统一经 `scripts/planner.shell` / `scripts/python.shell` 离线运行，锁文件不匹配或本地缓存不完整时停止，重新运行 setup 修复。启动不依赖当前目录或已激活的虚拟环境。通用 Python 命令可用 `bash "<skill>/scripts/python.shell" ...`；开发工具需要 PyYAML 时先 setup，再直接使用 `<skill>/.venv/bin/python`（日常启动不要求开发依赖）。环境文件纳入运行器指纹，变更后重新生成自检证据。

## 规划、执行与恢复

1. 先读取 `resume` 的 JSON 摘要，再按 ID 查询目标、当前阶段、任务和必要输入。不要默认加载所有历史。
2. 勘察实际项目后编写完整任务包。读取 [任务方法与执行流程](references/workflow.md)；创建或修订 JSON 时读取 [契约与操作](references/contracts.md)。
3. 每个任务必须有实现方法、接口、具体步骤、文件边界、模块清单和真实自检用例。`define_entity` 创建任务时自动生成当前修订的 `单元自检.shell`。没有真实测试的任务保持 `planned`，不使用占位成功脚本。
4. 用户只要求规划时，用 `archive_pending_plan` 保存待执行 JSON 快照并结束。归档不表示验收通过，不能顺便开始实施。
5. 用户要求实施时认领执行会话；依赖和任务包满足门禁后 `set_ready`、`start_task`。执行者只执行当前任务包，遇到接口或范围冲突返回对应规划层。
6. 按 [自检与证据协议](references/self-check.md) 运行脚本、登记证据、申请审查。自检 PASS 不能直接标记任务 passed；阶段集成和目标验收是不同门禁。
7. 每次计划或状态变化、验证完成、阻塞以及结束回复前保存检查点。暂停时释放会话。新对话对 active 工作先核查，不自动重跑。

所有权威状态、档案和证据记录在 JSON 中。`render` 仅生成阅读视图；不得编辑视图来更新状态。
每个操作都需要唯一 `operation_id` 和当前 `expected_revision`；重试同一请求必须复用原操作 ID 和原内容。
同一执行会话不是安全隔离：共享目录中的其他工具仍可能修改文件，依靠哈希复核发现漂移，不把角色标签当作认证。

## 收尾

Task 自检 → Task 审查 → Stage 模块与集成检查 → Goal 验收，逐层记录真实证据。
没有独立审查时记录 `self_review`。不能伪造观察、把未执行检查标记为 PASS，或把脚本结构检查当作模型行为实测。
报告目标完成情况、验证证据、当前阻塞和下一步。未请求立即执行的计划保持 `awaiting_execution`。

可运行的最小 JSON 与测试见 [软件样例](examples/software/definition.json) 和 [研究记录样例](examples/research/definition.json)。这些是演示数据，不能替代对用户项目的勘察和验收。
