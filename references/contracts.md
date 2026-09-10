# JSON 契约与 CLI

正式契约见 [contract.schema.json](../schemas/contract.schema.json)。`schemas.py` 是生成源，运行时校验使用同一词汇；测试要求导出 Schema 与源一致。跨实体引用、依赖和验收门禁由语义校验负责。

uv 管理的 Python 3.12.12、Bash、POSIX 文件锁和进程组是必需环境。支持 macOS/Linux，Windows 使用 WSL；不自动安装项目依赖。

## 初始化和读取

```bash
bash "$PLANNER_KERNEL_HOME/scripts/planner.shell" init --project "$PROJECT_ROOT" --explicit
bash "$PLANNER_KERNEL_HOME/scripts/planner.shell" resume --project "$PROJECT_ROOT"
bash "$PLANNER_KERNEL_HOME/scripts/planner.shell" query --project "$PROJECT_ROOT" --type tasks --id TASK-001
bash "$PLANNER_KERNEL_HOME/scripts/planner.shell" query --project "$PROJECT_ROOT" --type evidence --subject TASK-001 --revision 1 --status PASS
bash "$PLANNER_KERNEL_HOME/scripts/planner.shell" validate --project "$PROJECT_ROOT"
```

`init --explicit` 表示本次用户已明确启用，不是脚本自动取得授权。Git exclude 是初始化唯一可能写到 `tmp_plan/` 外的配置；用 `--no-git-exclude` 显式关闭。

`validate` 分别返回结构结果和新鲜度警告；结构 PASS 不表示功能验收 PASS。`resume` 不写状态，返回当前相关实体而非完整历史。`preparable_task_ids` 只是规划者可以检查并尝试 set_ready 的候选，不能直接执行。

## 写入信封

```json
{
  "schema_version": 1,
  "operation_id": "OP-SAVE-001",
  "expected_revision": 0,
  "session_id": "",
  "kind": "save_checkpoint",
  "data": {"summary": "目标已明确，等待执行", "next_steps": ["复核 TASK-001"]}
}
```

```bash
bash "$PLANNER_KERNEL_HOME/scripts/planner.shell" apply --project "$PROJECT_ROOT" --input operation.json
```

每个新操作使用新 ID。重试原操作保留原 ID、expected_revision、session_id 和内容，内核返回原回执。不同内容复用 ID 返回 CONFLICT；过期 revision 重新读取并协调，不盲目覆盖。

| kind | data 必需字段与行为 |
|---|---|
| define_entity | `entities: [{type, value}]`；可在单事务创建相互引用的实体，初始修订为 1 |
| revise_entity | 同上；已有实体 revision 加一，输出改用 revise_contract；Task 状态重置为 planned/unknown/pending |
| archive_pending_plan | `{}`；归档为 awaiting_execution；active/review 工作应先处理其状态，不伪装为未执行 |
| claim_session | `{id, owner}`；无有效会话时认领并进入 executing |
| take_over_session | `{old_id, id, owner, old_stopped: true}`；使用新会话 ID |
| save_checkpoint | `{summary, next_steps}` |
| set_ready | `{task_id}`；准备检查与依赖必须满足 |
| start_task | `{task_id}`；恢复 active 时另传 `acknowledge_resume: true`，须有有效会话 |
| rebind_inputs | `{task_id}`；未验收任务绑定当前输入，输入变化产生新任务修订 |
| submit_evidence | `{id, path}`；path 为 tmp_plan 内结果 JSON，验证后登记不可变副本 |
| request_review | `{task_id}`；有效会话、当前模块自检 PASS 后申请审查 |
| stage_review | `{stage_id, evidence_ids}`；所有任务通过，证据覆盖模块与集成检查 |
| record_acceptance | `{acceptance}`；Schema 的 acceptance 对象，绑定修订、标准、证据和 review_mode |
| revise_contract | `{output}`；修订加一，fingerprint 必须与 contract 匹配，compatible 必须保持语义 |
| pause / block / cancel | `{}`；保存快照并释放执行会话 |
| complete | `{}`；目标和阶段通过，重新核对当前任务与验收证据 |
| new_plan | `{reason}`；仅已完成/取消且无会话时可用，保存历史并创建新 plan_id |

有有效会话时，除认领/接管之外的操作都须携带它的 ID。角色属于协作协议，不是共享文件系统上的安全认证。

## 修订与证据

`revision` 是正整数，revision 1 的任务脚本位于 `tmp_plan/checks/TASK-001/R001/单元自检.shell`。Goal 定义目的与标准；Stage 拥有 goal_id；Task 拥有 stage_id；索引从这些权威关系派生。

实体 ID 在项目内保持唯一，`new_plan` 后不复用退休 ID。后续任务使用新 ID，避免旧执行包或旧 shell 与新计划中同名同修订的任务混淆。

归档不引用自己的索引。状态原子提交前先持久化所有新记录，中断留下的未引用文件会出现在诊断中；不自动删除，不把它们计算为已提交状态。记录发生哈希损坏时必须调查或恢复已知副本，不能覆盖历史来消除警告。

目标/阶段人工 review 证据使用 Schema 的 `review_evidence`：明确 method、expected、actual、criteria、reviewer、review_mode；携带当前 plan_id、subject_revisions、被测文件 bindings 和原始 attachments。
`subject_revisions` 对 Stage 包含自身与成员 Task 修订，对 Goal 包含自身、Stage 和成员 Task 修订。所有相关 tested_paths 必须绑定文件哈希。人工观察必须实际完成，不能由生成脚本代写 PASS。

证据可用 `supersedes` 引用同主题的旧证据；验收记录纠正必须显式 supersede 当前同主题同修订的验收，不能制造互相矛盾的并列结果。

## 示例

将 [software](../examples/software/definition.json) 或 [research](../examples/research/definition.json) 目录中的文件复制到专门的演示项目。显式 init 后，用 apply 提交该 definition.json，再 set_ready、claim_session 和 start_task。
示例自带可运行实现与正反例；它演示协议，不代替用户项目的研发。研究样例只验证结构化记录的最低来源契约，不证明所引用内容真实支持论断。
