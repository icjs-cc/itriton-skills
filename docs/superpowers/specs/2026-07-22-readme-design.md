# README 与技能命名调整设计

## 目标

为 `itriton-skills` 仓库增加一份面向中文读者的 GitHub 首页 README，并将腾讯会议技能名称从 `ixhlink-skills-tmeet-assistant` 更正为 `itriton-skills-tmeet-assistant`。

## README 结构

README 采用简洁的快速上手结构：

1. 项目简介：说明仓库用途及当前提供的腾讯会议助手技能。
2. 核心能力：概括认证、会议管理、录制与转写、报告与考勤、通讯录、会中控制和问题排查。
3. 环境要求：列出 `tmeet`、`python3` 及网络要求。
4. 安装：提供克隆仓库及将技能目录安装到 Agent 技能目录的通用示例。
5. 快速使用：给出自然语言使用示例，并链接到技能完整说明。
6. 目录结构：说明 `SKILL.md`、`references/`、`scripts/` 和 `tests/` 的职责。
7. 测试：提供标准库 `unittest` 命令。
8. 安全提示：简要强调授权信息保护和高风险操作确认。

README 不复制 `SKILL.md` 的完整命令手册，避免内容重复和后续同步成本。

## 元数据调整

仅修改 `tmeet-assistant/SKILL.md` frontmatter 中的 `name`：

```yaml
name: itriton-skills-tmeet-assistant
```

版本号和其他技能行为保持不变。

## 验证与交付

- 检查 README 中的相对链接和 Markdown 格式。
- 搜索仓库，确认不再出现 `ixhlink-skills`。
- 运行 `python3 -m unittest discover -s tmeet-assistant/tests -v`。
- 将变更提交并推送到 `origin/main`。
