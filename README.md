# ITRITON-SKILLS

面向智能 Agent 的实用技能集合。

## 技能列表

### tmeet-assistant

腾讯会议助手技能，名称为 `itriton-skills-tmeet-assistant`，主要能力包括：

- OAuth 登录、登出和授权状态检查
- 创建、更新、取消和查询会议
- 管理会议受邀成员
- 查询录制、智能纪要和转写内容
- 查询参会人及等候室报告
- 统计单场或周期会议的迟到、早退、缺席和有效参会时长
- 导出 CSV 或 Excel 考勤结果
- 搜索企业通讯录成员
- 呼叫成员入会或移出会议
- 导出本地日志并反馈工具问题

完整能力、参数和安全规则请参阅 [`tmeet-assistant/SKILL.md`](tmeet-assistant/SKILL.md)。

## 环境要求

- Node.js 与 npm
- Python 3
- 可访问腾讯会议服务的网络环境
- 腾讯会议 CLI `tmeet`

安装腾讯会议 CLI：

```bash
npm install -g @tencentcloud/tmeet@latest
```

## 安装技能

克隆仓库：

```bash
git clone https://github.com/icjs-cc/itriton-skills.git
cd itriton-skills
```

将 `tmeet-assistant` 目录放入所用 Agent 的技能目录。以 Codex 的默认个人技能目录为例：

```bash
cp -R tmeet-assistant ~/.codex/skills/
```

重新启动或刷新 Agent 会话，使其重新发现技能。不同 Agent 的技能目录可能不同，请以对应产品文档为准。

## 快速使用

安装技能和 `tmeet` 后，可以直接向 Agent 描述需求，例如：

```text
帮我查看明天下午的腾讯会议。
创建一个周五 14:00 到 15:00 的项目周会。
下载会议录制的转写内容。
统计本月周期会议的迟到、早退和缺席情况，并导出 Excel。
```

首次使用前需要完成腾讯会议 OAuth 授权。技能会根据当前环境引导登录，并要求对取消会议、修改会议、移除成员等高风险操作进行二次确认。

## 目录结构

```text
itriton-skills/
└── tmeet-assistant/
    ├── SKILL.md                    # 技能入口、工作流程和安全规则
    ├── references/                 # 各类 tmeet 命令与考勤数据说明
    ├── scripts/
    │   └── calculate_attendance.py # 确定性考勤计算与导出
    └── tests/                       # 考勤脚本测试及测试数据
```

## 测试

考勤脚本仅依赖 Python 标准库。运行完整测试：

```bash
python3 -m unittest discover -s tmeet-assistant/tests -v
```

## 同步到 GitHub 与 Gitee

可以为 `origin` 配置多个推送地址，使一次推送同时更新 GitHub 和 Gitee。以下配置保留 GitHub 作为 `origin` 的拉取地址，并重建其推送地址列表：

```bash
git config --unset-all remote.origin.pushurl 2>/dev/null || true
git config --add remote.origin.pushurl https://github.com/icjs-cc/itriton-skills.git
git config --add remote.origin.pushurl https://gitee.com/itriton/itriton-skills.git
```

之后使用一条命令同步两个仓库：

```bash
git push origin main
```

多个远程地址的推送不是原子操作。如果其中一个远程失败，另一个可能已经更新；修复失败原因后重新推送，并分别核对两个仓库的目标分支。

## 安全提示

- 不要在终端、日志或对话中输出 Access Token 和 Refresh Token。
- 取消或修改会议、移除成员、踢出成员等操作必须先获得明确确认。
- 考勤结论来自本地规则计算，不是腾讯会议返回的原始结论；数据不完整时不得生成确定性判定。

## 开源许可

本项目采用 [MIT License](LICENSE)，版权归 iTriton Contributors 所有。
