# 每任务单元自检.shell

每个实际任务修订都有独立 Bash 入口，业务检查复用公共运行器。准备阶段允许测试因业务功能尚未实现而失败，但不允许缺测试而产生 PASS。脚本的内容由内核生成，实际测试源码与配置由任务规划者提供。

```bash
export PLANNER_KERNEL_HOME="/absolute/path/to/planner-kernal"
bash "$PROJECT_ROOT/tmp_plan/checks/TASK-001/R001/单元自检.shell" \
  --project "$PROJECT_ROOT" --session SESSION-001 \
  --result tmp_plan/results/TASK-001-run-001.json
```

结果路径必须是项目 tmp_plan 内的新路径，不能覆盖先前结果。自检须在有效执行会话下运行；它生成证据，不修改任务状态。然后通过 submit_evidence 和 request_review 接入审查。

## 模块与检查定义

每个 module 包含 id、purpose、boundary_required、boundary_reason、check_ids。
每个 check 包含 id、module_ids、case、argv、cwd、test_sources、expected、timeout_seconds、required、adapter。check_ids 和 module_ids 必须双向一致。

- 每个模块至少一个 required normal 检查。
- boundary_required 为真时还需要 required boundary；否则写明不适用原因。
- 多模块任务至少一个覆盖多个模块的 required integration 检查。
- 一个检查可以验证多个模块的交互，但不能把无关的测试报告复制给各模块充当覆盖。

argv 是参数数组，不经 shell 拼接。支持以下占位符：`{python}`、`{project}`、`{report}`、`{work}`、`{unittest_report}`。cwd、test_sources、tested_paths 和 context_refs 都是项目相对路径。

```json
{
  "id": "CHECK-NORMAL",
  "module_ids": ["MODULE-PARSER"],
  "case": "normal",
  "argv": ["{python}", "{unittest_report}", "--report", "{report}", "tests.test_parser.ParserTests.test_normal"],
  "cwd": ".",
  "test_sources": ["tests/test_parser.py", "tests/helpers.py"],
  "expected": "有效输入解析为预期结构",
  "timeout_seconds": 60,
  "required": true,
  "adapter": "unittest"
}
```

## 报告适配器

`unittest` 使用内置 unittest_report.py，记录每个真实用例及失败子测试；预期失败、跳过不算必需检查通过。项目导入路径通过项目既有环境或 cwd 提供。

`junit` 要求项目框架写入 `{report}`，解析 testcase，校验存在的 tests/failures/errors/skipped 汇总与真实用例一致；不支持 DTD。框架只打印文本而没有报告不能通过。

`json` 使用明确的断言报告：

```json
{"tests": [{"id": "normal-case", "status": "PASS", "message": "actual value equals expected value"}]}
```

status 允许 PASS、FAIL、SKIP、BLOCKED，ID 必须非空且唯一。message 可选。该 JSON 必须由真正运行的断言产生，不能是固定成功模板。

## 聚合和证据

所有必需模块通过才返回 0。断言失败为 1；缺依赖、零用例或必需跳过为 2；超时、报告损坏及无法解释的执行矛盾为 3。优先级为 ERROR > FAIL > BLOCKED > PASS，普通失败后继续收集其他模块结果。

报告绑定 plan_id、任务修订、实际脚本与测试源码、配置、运行器、必要输入和被测文件哈希；登记时再次验证，且核对摘要与原始报告一致。修改测试或被测文件后旧证据不能继续证明通过。

任务进入 ready 时，内核冻结 `check_source_hashes`；更改断言需要新修订。同一任务修订按 registered_revision 选择最近登记的自检结果，最新失败不能回退到旧 PASS；旧报告不能重复登记来抹去失败。

只在隔离工作目录创建测试临时文件。运行器会清理自己创建的 work 目录和子进程，保留报告与日志附件。它不提供业务程序沙箱；不得把安装、发布、联网或修改业务文件的脚本伪装成最低单元测试。

自检至少通过一次故意破坏业务行为的反例验证，证明断言确实会失败。结构性检查、固定 exit 0、echo PASS、仅导入模块，都不能取代功能验证。
