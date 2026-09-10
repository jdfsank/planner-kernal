# planner-kernal

[English](README-en.md) | 简体中文

一个显式启用的 JSON 项目规划内核：把项目目标、阶段、任务、依赖、执行会话、自检结果、审查证据和验收状态持久化到项目本地，并支持跨对话恢复。

> 项目名称中的 `kernal` 是既有兼容名称，当前版本不改名。

## 在 Codex 中使用

这是一个 Codex skill。需要在当前对话显式输入 `$planner-kernal`，或明确要求“使用 planner-kernal”，才会启用规划内核。仅仅打开项目、提到 skill 名称或存在历史 `tmp_plan/` 都不会自动初始化目标项目。

启用后，skill 根目录是本仓库，目标项目根目录由用户明确指定；两者不要混用。命令行用户也可以直接使用下文的 Shell 入口，不依赖 Codex。

## 特性

- **显式启用**：只有用户明确执行 `init --explicit` 后，才会在目标项目创建运行时状态。
- **JSON 是唯一权威状态**：`tmp_plan/state.json` 保存当前计划；归档和证据以不可变 JSON 记录保存。
- **严格契约**：运行时校验 JSON Schema、字段、实体关系、依赖图、任务门禁和跨实体引用。
- **可恢复执行**：通过 `resume` 返回当前计划摘要、活动任务、下一步候选和新鲜度警告，不要求加载全部历史。
- **版本化任务包**：每个 Task revision 都绑定实现边界、输入、测试源码、任务自检脚本和文件哈希。
- **真实自检与证据**：支持内置 `unittest`、JUnit XML 和结构化 JSON 报告；原始报告、日志和摘要相互校验。
- **分层验收**：Task 自检不能直接替代 Task 审查、Stage 集成检查或 Goal 验收。
- **并发与幂等保护**：POSIX 文件锁、全局 revision、唯一 `operation_id`、请求哈希和 SHA-256 记录防止盲目覆盖。
- **项目隔离**：内核代码与目标项目分离；目标项目只在显式启用后写入 `tmp_plan/`。

## 适用范围

planner-kernal 适合需要长期推进、跨对话恢复或多人/多代理协作的项目，例如：

- 软件功能开发与验收；
- 研究记录和来源契约的结构化管理；
- 需要可追溯自检报告的自动化任务；
- 需要明确“计划、执行、审查、验收”边界的复杂工作。

它不是：

- 自动理解需求并替代规划者的项目管理 SaaS；
- 业务代码沙箱或安全认证系统；
- 自动安装目标项目依赖的包管理器；
- 自动启动子代理、发布软件或执行外部操作的编排平台。

## 运行要求

- macOS 或 Linux；Windows 请使用 WSL；
- Bash、POSIX 文件锁和进程组支持；
- [uv](https://docs.astral.sh/uv/)；
- Python 3.12.12（项目由 `.python-version` 和 `uv.lock` 固定）；
- Git 是可选依赖，仅用于 `init` 时把 `tmp_plan/` 写入本地 `info/exclude`。

项目本身不安装到目标项目，也没有运行时第三方依赖。开发校验依赖为 `PyYAML==6.0.3`。

## 安装

```bash
cd /absolute/path/to/planner-kernal
bash scripts/setup.shell
```

`setup.shell` 会使用锁定配置创建项目自己的 `.venv`，不会修改目标项目的 Python 环境。日常命令应通过项目脚本运行，以确保使用锁定的 Python 和依赖：

```bash
bash scripts/planner.shell --help
bash scripts/python.shell -c 'import sys; print(sys.version)'
```

如果机器没有 `uv`，脚本会输出 `BLOCKED` 并以退出码 `2` 结束。网络或本地缓存不可用时，先检查 `uv.lock` 是否与 `pyproject.toml` 一致，再重新运行 `setup.shell`。

## 快速开始

下面的流程使用仓库自带的软件样例。目标项目必须是一个已经存在的目录。

### 1. 准备内核和目标项目

```bash
export PLANNER_KERNEL_HOME="/absolute/path/to/planner-kernal"
export PROJECT_ROOT="/absolute/path/to/your-project"

bash "$PLANNER_KERNEL_HOME/scripts/setup.shell"
```

如果只想体验示例，可以创建一个临时项目并复制软件样例：

```bash
export PROJECT_ROOT="$(mktemp -d)"
cp "$PLANNER_KERNEL_HOME/examples/software/definition.json" "$PROJECT_ROOT/"
cp "$PLANNER_KERNEL_HOME/examples/software/subject.py" "$PROJECT_ROOT/"
cp "$PLANNER_KERNEL_HOME/examples/software/probe.py" "$PROJECT_ROOT/"
```

### 2. 显式初始化

```bash
bash "$PLANNER_KERNEL_HOME/scripts/planner.shell" \
  init --project "$PROJECT_ROOT" --explicit
```

`--explicit` 是一次当前调用的授权声明，不会因为目标目录里存在 `tmp_plan/`、历史文件或本 README 而自动取得授权。

默认情况下，如果目标目录位于 Git 工作树中，初始化会把对应的 `tmp_plan/` 规则写入该仓库的 `.git/info/exclude`，不会修改共享 `.gitignore`。不希望写入 Git exclude 时使用：

```bash
bash "$PLANNER_KERNEL_HOME/scripts/planner.shell" \
  init --project "$PROJECT_ROOT" --explicit --no-git-exclude
```

### 3. 导入计划定义

样例 `definition.json` 是一个 `define_entity` 操作，包含 Goal、Stage 和 Task。执行：

```bash
bash "$PLANNER_KERNEL_HOME/scripts/planner.shell" \
  apply --project "$PROJECT_ROOT" \
  --input "$PROJECT_ROOT/definition.json"
```

然后查看恢复摘要和结构状态：

```bash
bash "$PLANNER_KERNEL_HOME/scripts/planner.shell" \
  resume --project "$PROJECT_ROOT"

bash "$PLANNER_KERNEL_HOME/scripts/planner.shell" \
  validate --project "$PROJECT_ROOT"
```

### 4. 推进一个任务

所有写操作都使用统一的操作信封。下面是把 `TASK-001` 置为可执行的最小操作：

```json
{
  "schema_version": 1,
  "operation_id": "OP-READY-001",
  "expected_revision": 1,
  "session_id": "",
  "kind": "set_ready",
  "data": {
    "task_id": "TASK-001"
  }
}
```

保存为 `set-ready.json` 后执行：

```bash
bash "$PLANNER_KERNEL_HOME/scripts/planner.shell" \
  apply --project "$PROJECT_ROOT" --input set-ready.json
```

典型执行顺序是：

```text
define_entity
    ↓
set_ready
    ↓
claim_session
    ↓
start_task
    ↓
export-task / run-check
    ↓
submit_evidence
    ↓
request_review
    ↓
record_acceptance（Task）
    ↓
stage_review / record_acceptance（Stage）
    ↓
record_acceptance（Goal）
    ↓
complete
```

每个操作的 `expected_revision` 都必须等于上一次操作返回的 revision。执行会话建立后，除认领/接管操作外的写操作必须携带正确的 `session_id`。

### 5. 导出任务包并运行自检

任务进入 `active` 后，可以导出当前任务的执行包：

```bash
bash "$PLANNER_KERNEL_HOME/scripts/planner.shell" \
  export-task --project "$PROJECT_ROOT" \
  --task TASK-001 \
  --output tmp_plan/packets/TASK-001.json
```

任务包会包含 Goal、Stage、Task、输入产物、就绪问题、自检命令和运行器环境提示。

任务的自检结果必须写入 `tmp_plan/` 下一个全新的结果路径：

```bash
bash "$PLANNER_KERNEL_HOME/scripts/planner.shell" \
  run-check --project "$PROJECT_ROOT" \
  --task TASK-001 \
  --task-revision 1 \
  --session SESSION-001 \
  --result tmp_plan/results/TASK-001-run-001.json
```

自检返回码和状态含义如下：

| 状态 | 退出码 | 含义 |
| --- | ---: | --- |
| `PASS` | `0` | 所有必需检查和模块通过 |
| `FAIL` | `1` | 真实断言失败 |
| `BLOCKED` | `2` | 缺少依赖、零用例或必需检查被跳过 |
| `ERROR` | `3` | 超时、报告损坏或执行过程出现无法解释的错误 |

自检通过后仍需用 `submit_evidence` 登记结果，再执行 `request_review`。`PASS` 不能直接把 Task 标记为 `passed`。

## 核心概念

### Goal、Stage、Task 和 Output

| 实体 | 作用 | 典型门禁 |
| --- | --- | --- |
| Goal | 定义最终目的、范围、成功标准和重规划条件 | 目标验收通过后才能完成计划 |
| Stage | 组织一组相关任务，定义模块检查和集成检查 | 所有成员 Task 通过后才能进入阶段审查 |
| Task | 最小独立执行与验收边界，拥有实现步骤、文件边界和自检 | 依赖、输入、自检、Task 审查均通过 |
| Output | Task 产生的版本化公共契约 | 语义指纹、提供者和路径必须一致 |

除此之外，计划还维护 decisions、blockers、acceptances、execution session、archive index 和 evidence index。

### 状态与门禁

计划状态包括：

```text
draft → awaiting_execution → executing → completed
                         ↘ paused / blocked / cancelled
```

Task 状态包括 `planned`、`ready`、`active`、`ready_for_review`、`passed`、`failed`、`blocked`、`deferred` 和 `superseded`。

关键规则：

1. 未解决的规划问题、未通过的硬依赖或失效输入不能让 Task 进入 `ready`。
2. `start_task` 需要有效执行会话；一个项目同一时间只有一个执行会话。
3. 修改已绑定的测试源码、运行器、输入或被测文件后，旧证据会变为过期，不能回退使用旧 PASS。
4. 已完成或已取消的计划不可原地重启；后续工作使用 `new_plan`，旧 ID 和证据不会复用。

### 操作信封

所有写操作都符合以下结构：

```json
{
  "schema_version": 1,
  "operation_id": "OP-UNIQUE-001",
  "expected_revision": 0,
  "session_id": "",
  "kind": "save_checkpoint",
  "data": {
    "summary": "目标已明确，等待执行",
    "next_steps": ["复核 TASK-001"]
  }
}
```

- `operation_id` 在计划内唯一；相同 ID 重试必须使用完全相同的请求内容。
- `expected_revision` 防止基于旧状态覆盖新状态。
- `session_id` 绑定当前执行会话；没有活动会话时必须为空。
- `kind` 决定 `data` 的严格字段集合。
- 未知字段、重复 JSON key、非有限数字、越界路径和错误类型都会被拒绝。

常用操作类型：

| `kind` | 作用 |
| --- | --- |
| `define_entity` | 在一个事务中创建 Goal、Stage、Task 或其他实体 |
| `revise_entity` | 创建实体新 revision，并传播依赖失效 |
| `archive_pending_plan` | 将尚未执行的计划归档为 `awaiting_execution` |
| `claim_session` / `take_over_session` | 认领或在明确确认旧会话停止后接管执行会话 |
| `save_checkpoint` | 保存当前摘要和下一步 |
| `set_ready` / `start_task` | 通过就绪门禁并开始执行 Task |
| `rebind_inputs` | 为未验收 Task 重新绑定当前输入并创建必要 revision |
| `submit_evidence` | 校验并登记 `tmp_plan/` 内的自检或审查证据 |
| `request_review` | 在当前自检 PASS 后把 Task 置为待审查 |
| `stage_review` | 登记 Stage 的模块/集成证据覆盖 |
| `record_acceptance` | 记录 Task、Stage 或 Goal 的验收结果 |
| `revise_contract` | 修订版本化 Output 契约 |
| `pause` / `block` / `cancel` | 保存快照并释放执行会话 |
| `complete` | 在目标、阶段和任务均满足门禁后完成计划 |
| `new_plan` | 仅从已完成或已取消计划创建后续计划 |

完整字段约束见 [schemas/contract.schema.json](schemas/contract.schema.json) 和 [references/contracts.md](references/contracts.md)。

## CLI 参考

所有命令都要求 `--project PROJECT`，并以 JSON 输出结果。

| 命令 | 用途 | 是否写入状态 |
| --- | --- | --- |
| `init` | 显式初始化目标项目的 `tmp_plan/` | 是 |
| `resume` | 返回当前计划的恢复摘要 | 否 |
| `query` | 查询实体、证据或归档索引 | 否 |
| `validate` | 校验结构、记录哈希并报告新鲜度警告 | 否 |
| `apply` | 校验并提交任意领域操作 | 是 |
| `archive` | `archive_pending_plan` 的便捷入口 | 是 |
| `render` | 返回非权威的 JSON 阅读视图 | 否 |
| `export-task` | 导出 Task 执行包 | 可选；指定 `--output` 时写入 `tmp_plan/packets/` |
| `run-check` | 在当前执行会话中运行指定 Task revision 的自检 | 是；写入结果和原始附件 |

### 查询示例

```bash
# 查询全部 Task
bash "$PLANNER_KERNEL_HOME/scripts/planner.shell" \
  query --project "$PROJECT_ROOT" --type tasks

# 查询指定 Task
bash "$PLANNER_KERNEL_HOME/scripts/planner.shell" \
  query --project "$PROJECT_ROOT" --type tasks --id TASK-001

# 查询某个 Task revision 的 PASS 证据
bash "$PLANNER_KERNEL_HOME/scripts/planner.shell" \
  query --project "$PROJECT_ROOT" \
  --type evidence --subject TASK-001 --revision 1 --status PASS
```

### 写操作示例

```bash
# 应用一个操作文件
bash "$PLANNER_KERNEL_HOME/scripts/planner.shell" \
  apply --project "$PROJECT_ROOT" --input operation.json

# 可选地再次核对命令行 revision 与 JSON body 一致
bash "$PLANNER_KERNEL_HOME/scripts/planner.shell" \
  apply --project "$PROJECT_ROOT" \
  --input operation.json --expected-revision 4

# 专门归档待执行计划
bash "$PLANNER_KERNEL_HOME/scripts/planner.shell" \
  archive --project "$PROJECT_ROOT" --input archive.json
```

## 自检与证据协议

每个可独立执行的 Task revision 都有一个版本绑定的 Bash 入口：

```text
tmp_plan/checks/TASK-001/R001/单元自检.shell
```

自检定义包含：

- module 与 check 的双向映射；
- 正常路径检查；
- 适用时的边界或错误路径检查；
- 多模块任务的交互检查；
- 测试源码、运行器、配置、输入和被测文件哈希；
- 超时、子进程组清理和原始报告附件。

内置适配器：

- `unittest`：使用 `scripts/planner_kernel/unittest_report.py` 记录真实测试用例；
- `junit`：解析并核对 JUnit XML 的 testcase 汇总；
- `json`：解析由真实断言生成的 `{"tests": [{"id": ..., "status": ...}]}`。

自检结果只是证据，不会自动完成以下动作：

- 把 Task 标记为 `passed`；
- 替代人工或独立 Task review；
- 替代 Stage 集成检查；
- 证明研究事实、主观质量或视觉效果。

完整协议见 [references/self-check.md](references/self-check.md)。

## 目标项目中的运行时目录

显式初始化后，目标项目会产生如下结构：

```text
<project>/
└── tmp_plan/
    ├── .lock
    ├── state.json              # 当前权威状态
    ├── archive/                # 不可变计划快照
    ├── evidence/               # 已登记的证据记录
    ├── packets/                # 导出的执行包
    ├── checks/                 # 版本绑定的任务自检脚本
    ├── results/                # 自检结果入口
    └── work/                   # 自检运行器的临时工作目录
```

`state.json` 是当前状态入口；归档、证据、原始报告和日志由索引及哈希绑定。不要直接编辑 `state.json` 或手动覆盖历史记录，应通过 CLI 操作更新状态。

## 项目目录

```text
planner-kernal/
├── SKILL.md                         # Codex skill 定义与使用边界
├── agents/openai.yaml               # UI 元数据与显式启用策略
├── scripts/
│   ├── planner.shell                # CLI 启动包装器
│   ├── python.shell                 # 锁定 Python/uv 运行器
│   ├── setup.shell                  # 创建本地开发环境
│   ├── planner.py                   # Python CLI 入口
│   ├── dev_check.py                 # 开发阶段任务检查入口
│   └── planner_kernel/              # 核心实现
├── schemas/contract.schema.json     # JSON Schema 权威导出
├── references/                      # 工作流、契约、自检协议
├── examples/                        # software/research 可运行样例
├── checks/                          # skill 自身的任务自检入口
├── tests/                           # 单元、集成和回归测试
├── pyproject.toml
├── uv.lock
├── .python-version
└── .gitignore
```

## 开发与测试

安装开发环境：

```bash
bash scripts/setup.shell
```

运行完整测试套件：

```bash
bash scripts/python.shell -m unittest discover -s tests -t .
```

运行某个测试模块：

```bash
bash scripts/python.shell -m unittest tests.test_kernel
```

运行项目自身的任务开发检查：

```bash
bash checks/TASK-KERNEL-001/R002/单元自检.shell \
  --result /tmp/planner-kernal-kernel-check.json
```

默认的开发检查结果会写入被 `.gitignore` 忽略的 `validation/`。如需保持项目目录干净，请显式把 `--result` 指向系统临时目录。目标项目的正式任务证据仍应写入该目标项目的 `tmp_plan/results/`，并通过 `submit_evidence` 登记。

## 错误与排查

### `EXPLICIT_REQUIRED`

初始化缺少明确授权。确认本次调用确实由用户显式要求启用后，加上 `--explicit`。

### `NOT_INITIALIZED`

目标项目还没有运行时状态。先执行：

```bash
bash "$PLANNER_KERNEL_HOME/scripts/planner.shell" \
  init --project "$PROJECT_ROOT" --explicit
```

### `UNKNOWN_LAYOUT`

目标目录已经存在非空 `tmp_plan/`，但缺少有效 `state.json`。内核不会删除、重置或猜测其中内容。先人工备份并检查目录，再决定恢复或迁移方案。

### `CONFLICT` 或 `STALE`

通常表示 revision 过期、操作 ID 被复用、测试源码发生变化或证据已失效。重新执行 `resume`/`query` 获取最新状态；相同请求的重试保留原 `operation_id`，不同内容必须使用新 ID。

### `SESSION`

当前操作缺少有效执行会话或被其他会话持有。先 `claim_session`，或在明确确认旧会话已停止后使用 `take_over_session`。

### `BLOCKED` / `uv is required`

确认已安装 `uv`，并执行：

```bash
bash scripts/setup.shell
```

锁定运行器使用离线模式；如果本地缓存不完整，按 `uv` 的环境提示补齐缓存后再重试。

### `Missing/changed attachment` 或证据过期

不要修改或覆盖历史结果。重新运行当前 Task revision 的自检；如果接口、测试或输入确实改变，先按规划流程创建新 revision。

## 设计边界与安全提示

- 角色字段是协作协议，不是文件系统认证；共享目录中的其他进程仍可能修改文件，内核依靠哈希复核发现漂移。
- 检查脚本不是业务沙箱。不要把不可信的安装、发布、联网或修改业务文件的脚本当作普通自检运行。
- `project_path` 和 `runtime_path` 会拒绝绝对路径、`..` 穿越和符号链接路径；所有内核写入都限制在目标项目的 `tmp_plan/` 内。
- 自检报告和证据采用追加式/不可变写入，历史记录发现损坏时应调查或从已知副本恢复，而不是覆盖历史来消除警告。
- 研究样例只演示“声明带有来源引用”的结构契约，不自动验证来源是否真的支持论断。
- planner-kernal 不修改项目 `AGENTS.md`，不自动全局安装，不自动迁移旧计划，也不自动启动子代理。

## 相关文档

- [SKILL.md](SKILL.md)：在 Codex 中的显式入口、使用边界和完整工作流；
- [references/workflow.md](references/workflow.md)：规划者、执行者和验收者的职责；
- [references/contracts.md](references/contracts.md)：JSON 契约、CLI 和操作类型；
- [references/self-check.md](references/self-check.md)：任务自检、报告适配器和证据协议；
- [schemas/contract.schema.json](schemas/contract.schema.json)：正式 JSON Schema；
- [examples/software/definition.json](examples/software/definition.json)：软件任务样例；
- [examples/research/definition.json](examples/research/definition.json)：研究记录样例。

## 版本

当前项目版本：`0.1.0`。

许可证和发布信息尚未在项目中声明；在对外发布前请补充相应的许可证、贡献指南和变更日志。
