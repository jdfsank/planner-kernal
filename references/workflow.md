# 规划者、执行者与验收者

## 创建任务之前

读取目标项目的实际实现、约束、已有测试和用户需求。目标由 JSON `goal` 定义，外部文档是来源引用，不是额外执行授权。一个 Stage 描述可观察能力，Task 是独立实施和验收边界；内部连续编辑保留为 Steps。

一个 Task 可以有多个内部模块，但只拥有一个独立版本化的公共 Output 契约。把相关 API 方法放在一个逻辑契约对象中，不为每个方法制造任务。不同公共产物需要独立修订、消费者和验收时再拆分。

每个 Step 的四个字段都应具体：

```json
{
  "action": "在 slug 中先拒绝非字符串或仅空白输入，再执行 lower/split/join；不改变现有调用签名",
  "path": "subject.py",
  "expected": "Hello   WORLD 转为 hello-world，空输入抛出 ValueError",
  "verification": "运行 CHECK-NORMAL 与 CHECK-BOUNDARY，核对真实返回值及异常"
}
```

避免“完善模块”“确保正确”等指令。调查尚未完成时在 `unresolved` 中列出问题，并建立有明确问题、信息来源和结果格式的调查任务。调查任务也有机器可验证的最低交付契约；事实、设计和视觉判断单独验收。

`context_refs`、`test_sources` 和 `tested_paths` 都是项目相对的实际文件，不是模糊目录或 URL。把间接导入的测试辅助代码、关键 fixture 也列入 `test_sources`，把会影响结果的配置加入 `context_refs`。计划说明中的外部 URL 放入 Goal 的 `sources`。

## 创建并保存

使用一个 `define_entity` 操作提交相互引用的 Goal、Stage、Task 和初始 Output。定义任务时自动生成版本绑定的 shell，但业务测试由规划者编写或复用项目现有测试，并在任务达到 ready 前验证其真实入口。

任务以 `planned / unknown / pending` 开始，Stage 以 `planned` 开始。定义完成不等于用户批准实施。用户只要计划时，`archive_pending_plan` 保存快照并清空执行会话。开发计划和验证输出是开发记录，不是目标项目的运行时状态。

## 执行者

1. 显式启用后 `resume`；读取 `freshness_warnings`、下一步与准备候选。
2. 用户要求实施后 `claim_session`；导出当前 Task，核对修订及必要输入。
3. `set_ready` 确认门禁，`start_task` 进入 active；只编辑 owned 路径，不扩大接口和范围。
4. 按 Step 实施。若需改变检查行为或接口，返回规划者修订，不削弱断言来换取 PASS。
5. 使用任务 shell，登记结果；自检失败按诊断路径修复。成功后 `request_review`。
6. 返回改动文件、真实检查结果、证据 ID、偏差及未完成项。不得自称已通过独立审查。

同一对话暂停用 `pause` 保存快照并释放会话。崩溃后新对话不能仅凭时间抢占；用新的会话 ID、旧会话 ID 和 `old_stopped: true` 明确接管。`old_stopped` 是操作者基于事实作出的声明，内核无法跨宿主证明旧代理已经停止。

## 验收者与纠错

- Task：检查原目标、diff、模块测试、证据是否新鲜；`record_acceptance` 绑定当前任务修订。
- Stage：所有成员通过后，真实执行 module_checks 和 integration_checks；记录 review 证据，再 `stage_review`，最后记录 Stage acceptance。
- Goal：回到 success_criteria 进行验收；不能把自检报告当作体验、研究事实或视觉证据。
- 实现缺陷回 Task；公共契约不兼容回 Output 提供者；组合失败回 Stage；目的和范围变化回 Goal。

`revise_entity` 与 `revise_contract` 先归档旧数据，再创建修订并传播失效。旧验收保持不变。重新绑定未验收任务的输入会创建新 Task revision；已经验收的任务先显式修订。兼容产物修订必须保持语义指纹。

完成或取消的计划不原地复活。用户提出后续工作时显式 `new_plan`，保留旧档案和证据索引，生成新 plan_id。旧计划证据不能证明新计划。
