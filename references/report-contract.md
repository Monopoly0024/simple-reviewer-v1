# 报告记录规范 v1.0

脚本只使用 Python 3 标准库。审查者解释目标并实际运行验证后，写 UTF-8 JSON，再生成离线报告；脚本不会分析代码语义、执行验证命令或凭空发现问题。

```text
python <skill目录>/scripts/reviewer_report.py validate <review.json>
python <skill目录>/scripts/reviewer_report.py breakdown <review.json> --out <产物目录>
python <skill目录>/scripts/reviewer_report.py render <review.json> --out <审查产物目录>
```

可从 `assets/review.example.json` 开始。该文件是**已实际执行的示例案例**，不是待填模板，不得将其中证据当作项目证据。示例源程序和运行脚本在 `assets/order-export/`；参考后替换全部目标、位置、状态和证据。运行 `python build_example.py` 可重新生成本地示例记录与日志。

## 顶层与路径

工具 1.2.0 沿用 schema `1.0`。`breakdown` 生成 `code-breakdown.html/.md` 两文件；`render` 再生成 `reviewer-overview.html/.md`、`report.html/.md` 和 `review.effective.json`，共七文件。总览、图解和完整报告使用同一次证据评估结果。

### 可选项目展示字段（presentation）

`presentation` 是兼容旧记录的可选对象：

```json
{
  "project_title": "项目面向用户的名称",
  "overview_description": "总览解释项目要做什么",
  "breakdown_description": "拆解解释代码怎样组织这件事"
}
```

总览使用项目目标视角，代码拆解使用实现流程视角；若省略，渲染器使用记录标题和板块信息生成保守的默认文本。展示字段只影响标题和说明，不改变证据、状态或总体结论。

## HTML 页面往返导航

完整 `render` 的三张 HTML 页面共享固定在底部的“页面导航”，可互相切换，当前页用 `aria-current="page"` 标记。仅 `breakdown` 时不生成指向未产出报告的链接。打印时隐藏导航。

已有专题图解可显式传入 `--guide-page <现有HTML路径> --guide-label <按钮文字>`，在三页增加返回入口。参数路径相对于运行命令的目录；生成器转成相对于报告目录的链接，编码空格、中文及 `#` 等字符。不复制或上传专题内容；不自动猜测上级目录是否存在图解。专题页本身仍需提供进入报告的链接。专题 HTML 必须存在，且不能与输出文件重名，否则写文件前报错。不同 Windows 驱动器之间无法生成相对链接，需把页面放到同一驱动器再生成。

## 可选的日常语言上下文

这些字段由审查者依据用户原话、实际 Git 比较与检查记录填写。生成器只校验和展示，不能自动分析 AI 改动、执行测试或判断这些描述是否真实。缺少字段时显示信息缺口。

- `user_goal`：对象；可含字符串 `original_request`、`plain_language`，字符串数组 `acceptance_criteria`、`assumptions`、`open_questions`。补充验收描述不替代 `requirements` 中的正式验收条件；非空待确认问题会阻止总体通过，已有确定问题仍显示失败。
- `change_summary`：对象；可含字符串 `baseline`，字符串数组 `files_added`、`files_modified`、`files_deleted`、`user_visible_changes`、`possible_impacts`。文件路径须位于项目内；已删除文件无需仍存在。没有可比较基线时明确写出限制，不能编造“刚刚 AI 修改”。
- `risks`：数组；每项必填非空字符串 `title`、`action`、`status`、`impact`、`next_step`。`status` 仅支持 `observed`（动作已发生）、`not-run`（尚未执行）、`mitigated`（已登记缓解措施）、`unknown`（执行状态待确认）。这些是动作记录状态，不是验证通过状态，也不是自动发现的安全漏洞。若风险已造成确定缺陷，另在 `issues/evidence` 中登记。
- `next_actions`：数组；每项必填非空字符串 `action`、`reason`。建议保持一至三个明确动作。
- `comprehension`：对象；可含 `glossary` 数组，每项必填非空字符串 `term`、`meaning`，只解释本次报告实际用到的术语。

全部 HTML 文本转义，正文不会作为脚本执行。补充文案不授予绿色状态；通过仍要求原有运行证据与范围规则。记录不含上述字段时仍可生成全部产物，不声称目标、AI 改动或风险已知。字段不使用时省略；显式填写 `null` 会作为类型错误拒绝。

## 必填顶层与路径

- `schema_version`：`"1.0"`。
- `title`：用户可读标题；`reviewed_at`：带时区的 ISO 日期时间。
- `mode`：`review` / `review-and-fix`。
- `project_root`：绝对路径，或相对于 review.json 的路径。报告生成后记录绝对根路径。
- `snapshot`：`base_revision`、`notes`、`files: [{path, sha256}]`。登记所有影响本次验证的源文件、测试、配置与样例数据。SHA-256 为 64 位十六进制。
- `requirements`、`nodes`、`edges`、`issues`、`evidence` 为数组。新记录增加 `blocks` 数组。
- `journey_note`：实际入口到最终结果的验证范围和限制，可选但推荐。

所有文件与日志路径相对于 `project_root`；不得含上级跳转、指向根目录外的符号链接或无关文件。日志也放在项目内约定的审查产物位置。`cwd` 为根目录内的相对工作目录。ID 分别使用 R1、N1、I1、E1 等稳定编号。

## 独立代码拆解文件与板块 blocks

从工具版本 1.1.0 起，`breakdown` 生成 `code-breakdown.html` 和 `code-breakdown.md`。工具 1.2.0 的 `render` 再生成 `reviewer-overview.html/.md`、`report.html/.md` 和 `review.effective.json`。返回路径中 `breakdown_html` 指 HTML，原 `breakdown` 仍指 Markdown，`overview_html` 与 `overview` 分别指总览 HTML 和 Markdown。记录 schema_version 保持 `1.0`，旧记录可直接使用。两种方式使用同一有效证据判定，独立拆解文件不需要打开总览即可阅读。

每板块：`id, title, purpose, node_ids`。ID 为 B1、B2…；title 是功能名称，purpose 说明整体职责，node_ids 包含属于此板块的节点。一板块可对应多个节点或多个文件。每个审查节点恰好归入一个主板块；跨板块调用仍用 edges 表达。板块覆盖本次全部已审查节点，但不自动代表全部项目源码。

板块状态由当前有效节点汇总：failed 优先，然后 pending、unchecked，全部 passed 才 passed。不能手写更乐观的板块结论覆盖节点失败。为兼容旧记录，未提供 blocks 时回退为每节点一板块，并在独立文件明确注明分组未经整体确认。新审查应人工按功能填写。

拆解文件包含板块彩色图、作用与位置总表、逐节点输入输出、应有/实际行为、生效证据、问题和覆盖边界。代码位置链接使用绝对路径和起始行号；符号及范围按提供值显示。依赖或验证文件未单独拆成板块时列入覆盖说明。

### HTML 图文补充 explanation（可选）

各板块可加入 `explanation` 对象，让通俗讲解与验证记录共同保存：

```json
{
  "summary": "先按状态筛选，再切出当前页；列表分页本身符合要求。",
  "steps": [
    {"title": "筛选", "detail": "保留 status 相同的订单。"},
    {"title": "分页", "detail": "按起点取最多 20 条。"}
  ],
  "example": {
    "input": "35 条 paid 订单，第一页，每页 20 条",
    "expected": "列表应返回前 20 条，导出全部则应另取 35 条。",
    "note": "教学示意，不代替实际运行记录；运行观察见关联 evidence。"
  }
}
```

`summary` 为非空文本；`steps` 为 1–12 项，每项含非空 `title, detail`；`example` 含非空 `input, expected, note`。均为纯文本，不接受可执行 HTML。无需步骤图时省略该字段；无需教学例子时省略 example。每块始终有输入→职责→输出示意图。步骤图不是实时执行轨迹，也不会把节点改绿。

HTML 将从登记源码读取 UTF-8 片段，包含行号、完整路径、符号及范围，每位置最多 120 行并标注截断。缺失、编码不可读、行号越界时提示而不伪造。源文件变化时显示当前文件并提示过期，同时有效节点状态降级。页面仅是离线快照，不监听后续文件变化；生成文件可能包含私有源码与绝对路径，不能未经用户要求放入公共仓库。所有文本均转义，无 CDN 或网络请求。

## 可选白话讲解字段（blocks[].explanation）

除 `summary`、`steps`、`example` 外，支持下列兼容字段；旧记录不需要补齐才能生成：

- `plain_language`：一句话解释这一块做什么，不以未解释的术语开头。
- `why_needed`：它为什么是目标流程的一部分，省略后会影响什么。
- `analogy`：帮助理解的比喻，注明不适用之处，不作为证据。
- `flow`：对象，必须包含三个非空字符串 `input`、`process`、`output`；用于白话输入→动作→输出面板。
- `takeaway`：读完应记住的一句话。
- `glossary`：`[{"term": "术语", "meaning": "白话含义"}]`，只解释当前板块真正使用的词。
- 全局和板块 `glossary` 条目可附 `aliases` 非空字符串数组，例如 `{"term":"checkpoint / 权重文件","aliases":["checkpoint","权重文件"],"meaning":"模型内部数字的存档，在这里用于恢复模型。"}`。同一词表内相同词或别名不能对应冲突解释。正文按最长词匹配，局部优先全局；局部词只有含义一致时才可用于无板块上下文的正文。英文匹配不区分大小写，不匹配文件路径及标识符内的片段。
- HTML 在说明段落、列表、定义正文里加入可点击的绿色下划线。解释卡和连线位于正文之外的独立固定悬浮层：侧边有空间时靠板块右侧，否则在视口内浮动；手机端同样悬浮，避开当前术语和固定导航，长解释在卡片内滚动。打开、切换、关闭均不能修改原正文的宽高、位置、父子结构或文字换行；不动态预留侧栏、不压缩板块、不撑高段落。浏览器回归须比较前后可见方块及段落的位置、尺寸和页面总高度。支持 Enter/Space、Esc、关闭按钮和点击外部关闭。标题、链接、源码、路径、证据片段和原词表不加注释。每次只展开一个解释，全部离线；静态 Markdown 保留原词表。此机制不改变任何结论状态。
- `highlights`：1–3 条本板块最需要先注意的重点，渲染时使用更大、更粗的文字；不参与状态计算。

上述文本均转义后展示，Markdown 保留相同讲解。渲染器不会自动编造例子或解释；作者需要核对业务意义。总览的白话入口链接到拆解对应板块，技术实现和验收详情默认折叠，代码位置及原证据仍可访问。教学字段不参与状态计算；示意输入输出不能冒充实际执行观察。

## 需求 requirements

每项：`id, text, source, acceptance, required, status, node_ids, evidence_ids`。

- `source` 引用真实用户需求来源，必要时注明假设。
- `status`：`passed`、`failed`、`unchecked`。未验证不是不通过。
- `passed` 需相关节点全通过及实际执行通过证据。一个节点只局部通过时，不得据此扩大需求通过范围。
- `failed` 需当前失败证据，可是实际运行或确定性的静态证据。
- 人工偏好与业务验收需记录具体操作和观察结果；未取得时保留 `unchecked`。

## 节点 nodes

每项：`id, title, role, expected, actual, input, output, scope, status, reason, locations, requirement_ids, evidence_ids, issue_ids`。

- `role`：`implemented` / `missing` / `unprovided`。缺失节点必须是已确认失败且关联问题和缺失证据；找不到单个符号不足以证明功能缺失。未提供的外部实现用 unprovided，保持 pending/unchecked，不伪装成已实现或已确认缺失。
- `status`：`passed`、`failed`、`pending`、`unchecked`。
- `locations`：`[{path, line, end_line?, symbol?}]`，line 为起始行，从 1 开始；end_line 不小于 line，symbol 为函数/类/关键代码名称。新记录优先提供完整符号和范围；旧记录只有起点仍可使用。范围和符号由审查者核实，生成器不证明符号语义。缺失节点可绑定相关入口或接口定义，未提供实现则为空并明确说明。
- `scope`：说明验证了什么输入、环境和路径；`reason` 说明状态依据。
- `affected_by` 可选，填上游节点 ID。它描述影响，不自动改变自身状态。
- `passed` 需要退出码 0、结果通过且当前日志完整的 runtime 证据；`failed` 需要 confirmed 问题和 failed 证据。

## 连线 edges

每项：`source, target, label, kind`，可选 `issue_ids`。

- `kind`：`normal`、`exception`、`affected`、`inferred`。
- normal 是确定的调用/数据关系；其他关系以虚线标明，label 说明含义。
- 连接错误可关联 issue；已确认错误边为红色，待核实为黄色。
- 程序存在循环时保留真实回边。大项目按模块分报告，不能为了美观删去关键分支。

## 问题 issues

每项：`id, title, status, severity, node_ids, evidence_ids, impact, suggestion`。

- `status`：`confirmed` / `suspected`。
- `severity`：`blocking` / `nonblocking`，与验证状态分开。
- confirmed 必须关联失败证据；suspected 在图中保持待核实。
- 修复后保留旧记录，生成新记录；不要让旧问题仍挂到绿色节点上。

## 证据 evidence

每项：`id, kind, command, cwd, exit_code, outcome, expected, observed, scope, source_files`。

- `kind`：`runtime` / `static`。runtime 包括真实命令执行和有记录的实际用户操作。
- `command`：实际命令或明确标注的人工操作步骤，不能写未执行的建议。
- `exit_code`：命令真实退出码；人工操作用 0 表示已完成记录并在 command 中标注人工。
- `outcome`：`passed`、`failed`、`blocked`。退出码 0 也可能观察到业务失败，结果应填 failed。
- `expected`：来自需求或独立样例；`observed`：实际观察，不能只写“测试通过”。
- `source_files`：关联快照中的文件，至少一项。
- runtime 另需 `log_path, log_sha256`，记录完整输出或实际操作日志；截图可作为额外人工证据，但需文字说明其范围。
- static 需要明确的代码位置、逻辑与反证范围写入 observed/scope；它能证明确定的问题，不能单独证明运行通过。

## 自动一致性检查与边界

生成器检查编号、引用、颜色与证据的基本一致性，核对登记源文件和日志哈希。变动或缺失会使关联证据过期，节点降为 pending、需求降为 unchecked；审查者重新确认其他充分证据后，可更新记录。过期问题不再作为当前确定性阻断依据。

生成器无法判断日志是否伪造、断言是否正确、未登记依赖是否变化，也无法证明端到端覆盖；这些由审查者负责。记录中的文本不会作为 HTML 执行。旧报告是快照；需要更新时重新生成。
