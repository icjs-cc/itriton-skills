# 腾讯会议考勤

本工作流使用 `tmeet` 查询会议事实，再调用 [`../scripts/calculate_attendance.py`](../scripts/calculate_attendance.py) 确定性计算单场或周期会议考勤。完整输入输出契约见 [`attendance-schema.md`](attendance-schema.md)。

## 默认规则

| 规则 | 默认值 |
|---|---:|
| 迟到宽限 | 5 分钟 |
| 早退宽限 | 5 分钟 |
| 最低有效出勤率 | 80% |
| 多段参会合并间隔 | 2 分钟 |
| 等候室时间 | 不计入 |
| 主持人 | 计入 |
| 机器人、会议室设备 | 排除 |

用户明确给出其他规则时，写入标准化输入的 `policy`。最终回复和导出文件必须展示实际采用的规则。

## 单场考勤工作流

1. 确定目标会议。用户只提供会议号时，先执行：

   ```bash
   tmeet meeting get --meeting-code "<会议号>" --compact
   ```

2. 使用内部 `meeting_id` 查询完整受邀者名单。首次不传 `--page-token`，持续读取 `data.next_page_token` 直到为空：

   ```bash
   tmeet meeting invitees-list --meeting-id "<meeting_id>" --page-size 30 --compact
   ```

3. 查询完整参会报告，同样持续翻页：

   ```bash
   tmeet report participants --meeting-id "<meeting_id>" --page-size 100
   ```

   考勤依赖入会、离会、人员标识和设备类型等字段。首次处理某个 CLI 版本时不要使用 `--compact`，先确认完整响应是否包含所需字段；确认 compact 响应仍保留所需字段后才可启用。

4. 将会议基础信息、全部受邀者和全部参会记录写入临时标准化 JSON。字段映射遵循 [`attendance-schema.md`](attendance-schema.md)，原始响应另行保留以供追溯。

5. 如果用户提供名单，通过 `--roster` 加载。默认补充会议受邀者；用户明确要求覆盖时使用 `--roster-mode replace`。

6. 在 `skills/tmeet-assistant` 目录中执行计算并生成所需格式：

   ```bash
   python3 scripts/calculate_attendance.py /tmp/tmeet-attendance-input.json \
     --roster /path/to/roster.xlsx \
     --roster-mode augment \
     --json-output /tmp/tmeet-attendance.json \
     --csv-output /tmp/tmeet-attendance.csv \
     --xlsx-output /tmp/tmeet-attendance.xlsx
   ```

7. 读取 JSON 中的 `warnings`、`needs_review` 和 `final` 后再回复用户。存在数据不足或身份待确认时，不得把结果描述为最终考勤。

## 周期会议工作流

1. 使用 `meeting get` 确认周期会议及子会议。
2. 对每个目标 `sub_meeting_id` 分别拉取完整参会报告：

   ```bash
   tmeet report participants \
     --meeting-id "<meeting_id>" \
     --sub-meeting-id "<sub_meeting_id>" \
     --page-size 100
   ```

3. 在标准化 JSON 的 `meetings` 中为每场子会议增加一个元素。
4. 一次运行计算脚本，生成单场明细和 `aggregate` 周期汇总。

周期汇总包括应出席、实到、正常、迟到、早退、缺席次数和平均出勤率。不得用周期平均值覆盖单场异常。

## 判定规则

- **迟到**：首次有效入会晚于计划开始时间加宽限时间。
- **早退**：最后有效离会早于计划结束时间减宽限时间。
- **有效时长**：所有参会区间的并集；重叠设备不重复累计。
- **出勤率**：有效时长除以计划会议时长，最高为 100%。
- **缺席**：应到人员没有有效参会区间。
- **时长不足**：出勤率低于最低比例。
- **临时考勤**：会议尚未结束时不判定早退，并标记 `provisional=true`。

## 名单与身份规则

- 默认应到名单来自 `meeting invitees-list`。
- 用户名单可以补充、排除或明确覆盖受邀者名单。
- 匹配顺序：稳定人员 ID、邮箱、手机号、唯一姓名。
- 同名、多账号或多候选禁止猜测，必须进入 `needs_review` 并请用户确认。
- 外部访客可展示在 `external_attendees`，默认不自动加入应到名单。
- 禁止为了考勤任意调用 `contact search`；遵守主 skill 的通讯录使用限制。

## 数据完整性硬约束

- 任一受邀者或参会报告分页未拉完，设置 `pagination_complete=false`；禁止生成最终出勤率。
- 真实响应缺少入会或离会时间时，禁止根据总时长、发言时间或其他字段推断。
- 会议未结束时只能输出临时考勤。
- 原始时间必须带时区；跨时区比较由脚本按绝对时间完成。
- 展示给用户时只使用会议号，不展示内部 `meeting_id`。

## 回复格式

按以下顺序展示：

1. 会议主题、会议号和计划时间；
2. 本次采用的考勤规则；
3. 应到、实到、正常、迟到、早退、缺席、时长不足摘要；
4. 人员明细及每项判定原因；
5. 身份待确认、外部参会者和数据完整性警告；
6. 用户要求的 CSV 或 Excel 文件。

考勤涉及人员管理信息。未获用户明确要求时，不扩大查询范围、不跨会议关联人员行为，也不在反馈日志中包含姓名、手机号、邮箱、会议号等敏感信息。
