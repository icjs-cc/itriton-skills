# 考勤标准化数据契约

`scripts/calculate_attendance.py` 不直接调用 `tmeet`，只处理经过标准化的 JSON。这样可以保留原始 CLI 响应，并让考勤判定可复现、可测试。

## 输入结构

```json
{
  "generated_at": "2026-07-21T16:00:00+08:00",
  "policy": {
    "late_grace_minutes": 5,
    "early_leave_grace_minutes": 5,
    "minimum_attendance_ratio": 0.8,
    "merge_gap_minutes": 2,
    "waiting_room_counts": false,
    "exclude_types": ["bot", "room_device"]
  },
  "roster": {
    "mode": "augment",
    "add": [{"person_id": "u4", "name": "李四"}],
    "exclude": ["u3"]
  },
  "meetings": [
    {
      "meeting_code": "123456789",
      "sub_meeting_id": "optional-sub-meeting-id",
      "subject": "项目周会",
      "start_time": "2026-07-21T14:00:00+08:00",
      "end_time": "2026-07-21T15:00:00+08:00",
      "pagination_complete": true,
      "invitees": [
        {
          "person_id": "u1",
          "name": "张三",
          "email": "zhangsan@example.com",
          "phone": "13800000000"
        }
      ],
      "participants": [
        {
          "person_id": "u1",
          "name": "张三",
          "email": "zhangsan@example.com",
          "participant_type": "user",
          "sessions": [
            {
              "join_time": "2026-07-21T14:03:00+08:00",
              "leave_time": "2026-07-21T15:00:00+08:00"
            }
          ]
        }
      ]
    }
  ]
}
```

## 字段规则

### 顶层字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `generated_at` | 建议 | 数据生成时间；判断会议是否仍在进行。省略时使用本机当前时间 |
| `policy` | 否 | 覆盖默认考勤规则，只填写需要修改的字段 |
| `roster` | 否 | 用户名单合并规则 |
| `meetings` | 是 | 至少一场会议；周期会议的每个子会议作为独立元素 |

### 名单合并

- `mode=augment`：以每场会议的 `invitees` 为基础，追加 `add`。
- `mode=replace`：使用 `people` 完全替代会议受邀者，再追加 `add`。
- `exclude` 优先级最高，可填写人员 ID、邮箱、手机号或姓名。
- 每个人至少提供 `person_id` / `open_id` / `email` / `phone` / `name` 之一。

优先级固定为：`exclude` > `replace` > `add` > `invitees`。

### 参会数据

- `sessions` 必须包含真实的 `join_time` 与 `leave_time`，均为带时区 ISO 8601。
- 同一人员的不同设备、不同进出记录分别放入 `sessions`；脚本负责去重和合并。
- `participant_type` 建议标准化为 `user`、`guest`、`host`、`bot` 或 `room_device`。
- 不得将等候室进入时间写成 `join_time`；默认规则不计算等候室时间。
- `pagination_complete` 只有在所有受邀者和参会报告页面均成功拉取后才能设为 `true`。

## tmeet 响应映射规则

先保留 `tmeet` 原始 JSON，再根据实际响应字段映射到本契约。不同 CLI 版本返回字段可能变化，映射前必须检查真实字段，禁止仅凭本文档猜测：

- 用户稳定标识 -> `person_id`
- 用户展示姓名 -> `name`
- 实际入会时间 -> `sessions[].join_time`
- 实际离会时间 -> `sessions[].leave_time`
- Sip/Pstn、会议室或机器人类型 -> `participant_type`

如果真实响应缺少入会或离会时间，保留可确认的人员事实，但不要构造时间；脚本会输出 `participant_timestamps_missing` 并拒绝生成最终判定。

## 用户名单文件

脚本通过 `--roster` 接受 `.json`、`.csv` 或 `.xlsx`：

- JSON：人员数组，或 `{ "people": [...] }`。
- CSV/XLSX：第一行必须是表头，支持 `person_id`、`open_id`、`name`、`email`、`phone`。
- XLSX 读取第一个工作表。
- 空行忽略；缺少任何身份字段的非空行会报告具体行号。

## 输出结构

JSON 输出包含：

- `policy`：本次实际使用的规则；
- `sessions[].summary`：单场应到、实到、正常、迟到、早退、缺席、时长不足数量；
- `sessions[].details`：人员事实、合并后区间、有效时长、出勤率和可并存状态；
- `sessions[].needs_review`：同名或多身份候选；
- `sessions[].external_attendees`：实际参会但不在应到名单中的人员；
- `sessions[].excluded`：机器人、会议室设备等排除记录及原因；
- `sessions[].warnings`：分页或时间字段问题；
- `aggregate`：多场/周期会议的人员汇总。

`statuses` 可取 `normal`、`late`、`early_leave`、`insufficient_duration`、`absent`、`data_insufficient`。除 `normal` 和 `data_insufficient` 外，其余状态可以并存；`data_insufficient` 表示输入缺少最终判定所需事实，此时不生成单场摘要和周期汇总。
