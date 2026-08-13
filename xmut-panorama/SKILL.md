---
name: itriton-skills-xmut-panorama
version: 1.2.0
description: "厦理全景地图：厦门理工学院校园空间信息助手。用自然语言查找厦理工建筑/设施/区域，在本地 HTML 内嵌查看器中打开 3D 全景（同源代理，避免只跳外部站）。当用户提到厦理工、XMUT、3d.xmut.edu.cn、图书馆在哪、食堂、宿舍、教学楼、带我逛校园、新生熟悉校园、全景地图、3D校园、打开地图时使用。本技能只负责找地点与 3D 入口，不做选课/消费等决策。"
---

# 厦理全景地图

面向厦门理工学院师生及访客的**校园空间信息助手**。

**只做四件事：** 理解想找什么 → 映射到具体地点 → 介绍位置与周边 → **在本地 HTML 内嵌查看器中打开 3D 全景**。

**不做：** 选课、社团取舍、消费决策、时间管理（交给「校园决策助手」等其他 Skill）。

## 成功标准

- 用户不用记准确建筑名，描述意图也能落到地点
- 默认打开 **本地内嵌查看器**（左侧地点列表 + 右侧全景），而不是直接跳到外部官网标签页
- 无精确场景时，打开最近相关场景或空中全景，并诚实说明覆盖范围
- 「带我逛校园 / 新生半日熟悉校园」可在查看器内切换站点

## 数据与深链（必须使用）

地点目录见 [references/places.json](references/places.json)。回答前先读取该文件，按 `name` / `aliases` / `intent_map` 匹配。

| 项 | 值 |
|----|-----|
| 门户 | https://3d.xmut.edu.cn/（**勿**把 `startscene` 加在门户根路径，参数进不了 iframe） |
| 推荐版本 | **2022**：https://3d.xmut.edu.cn/2022/ |
| 备用版本 | 2016：https://3d.xmut.edu.cn/2016/ |
| 深链格式 | `https://3d.xmut.edu.cn/2022/?startscene={scene_id}` |
| 等价参数 | `s={scene_id}`（引擎会写入 startscene） |
| 可选视角 | `h` / `v` / `f`（水平/垂直/视野） |
| 默认场景 | `pano926`（空中全景） |

技术背景：官方站点为 **krpano / Panotour Pro**，`passQueryParameters=true`，场景标题来自 `index_messages_zh.xml`。

**优先 2022 深链。** 仅当用户明确要旧版或 2022 不可用时，再给 2016 总入口（2016 未纳入本 Skill 的 scene 目录）。

## 打开页面（必须执行）

官方站 `3d.xmut.edu.cn` 带有 `X-Frame-Options: SAMEORIGIN`，**不能**在任意网页里直接 iframe。  
本技能用本地查看器 + 同源反向代理去掉该限制，把全景嵌在 `viewer/index.html` 里。

目标明确时：**先打开本地内嵌查看器**，再在回复里说明，并附官方深链作备用。

### 推荐方式（默认内嵌）

在技能目录下执行（需非沙箱，以便起本地服务并唤起浏览器）：

```bash
python3 scripts/open_scene.py 图书馆
# 或
python3 scripts/open_scene.py pano1083
# 新生半日（查看器内路线）
python3 scripts/open_scene.py --tour freshman
```

效果：

- 自动启动（或复用）`http://localhost:8765/`（监听 `127.0.0.1:8765`）
- 打开内嵌页：`http://localhost:8765/?scene=pano1083`
- 右侧 iframe 经 `/proxy/2022/` 加载官方全景

stdout JSON 含 `mode`（`embed`/`external`）、`viewer_url`、`upstream`、`opened`。

必要时可前台保活演示：

```bash
python3 scripts/serve_viewer.py --foreground --no-open
```

### 仅当用户明确要求时

```bash
python3 scripts/open_scene.py 图书馆 --external
```

才会直接打开官方站（非内嵌）。

### 打开策略

| 场景 | 行为 |
|------|------|
| 单点查询且已唯一匹配 | 调用 `open_scene.py`：经 `/api/goto` 同步场景；已有查看器标签页会自动跳转，避免 macOS 只聚焦旧页导致场景不一致 |
| 新生半日 | `open_scene.py --tour freshman`（查看器内「开始/下一站」） |
| 用户说「下一站」 | 再次执行打开对应地点；依赖 `/api/goto` 同步，不必新开一堆标签页 |
| 类别列举 | 先列选项，选定后再打开 |
| 无法起本地服务 | 降级为官方深链 Markdown，并说明原因 |

打开成功后写：`已在本地全景查看器中打开「{地点}」（scene_id=…）。`  
若 JSON 含 `synced_via_api: true` 且 `opened: false`，说明是同步到**已打开**的查看器，不是没打开。  
失败则给 `upstream` 官方链接，不要假装已打开。

## 工作流程

1. **识别意图**：单点查询 / 类别列举 / 漫游导览 / 模糊设施
2. **读取** `references/places.json`，做名称或意图匹配
3. **一对多时**：列出候选项，请用户选一个；或按意图给出 1 个首选 + 邻近备选
4. **打开页面**：按上方策略执行 `scripts/open_scene.py`（或 `open`/`xdg-open`）
5. **输出**：名称、简介、周边、**已打开提示 + Markdown 备用深链**
6. **覆盖不足时**：打开最近场景或空中全景，说明公开漫游覆盖限制

## 输出格式

### 单点查询

```markdown
📚 {地点名称}

{一句话简介}

📍 区域
{area}

🗺️ 3D校园地图
✅ 已在本地内嵌查看器打开
查看器：[http://localhost:8765/?scene={scene_id}](http://localhost:8765/?scene={scene_id})
官方备用：[进入{地点}3D全景]({3d_url})

附近：
- …
```

### 类别列举（如食堂）

只列空间事实与入口；若用户继续问「吃什么/哪家更划算」，一句话引导去决策类 Skill，本 Skill 可继续帮「离某地点近的食堂场景」。

### 带我逛校园（菜单）

```markdown
🎓 厦理工3D校园漫游

你可以选择：

① 🏫 教学区
② 📚 图书馆
③ 🍜 食堂
④ 🏠 宿舍区
⑤ 🏃 体育设施
⑥ 🌳 校园景观
⑦ 🔎 随便逛逛（空中全景）

选择一个区域后：**先打开对应场景**，再简短确认。
```
区域默认落地：

| 选项 | 首选 scene |
|------|------------|
| 教学区 | 明理教学楼 `pano923` |
| 图书馆 | `pano1083` |
| 食堂 | `pano924`（可附 `pano925`） |
| 宿舍区 | 思明苑公寓 `pano922` |
| 体育设施 | 游泳馆外 `pano921` |
| 校园景观 | 三鉴湖 `pano916` |
| 随便逛逛 | 空中全景 `pano926` |

### 新生半日熟悉校园（比赛 Demo 首选）

当用户类似说：「刚到厦理工的新生，只有一个下午，帮我快速熟悉校园」时，**不要**输出普通「图书馆在哪里」式单点问答，使用：

先执行：`python3 scripts/open_scene.py --tour freshman`，再回复：

```markdown
🎓 新生半日校园探索计划

✅ 已打开本地全景查看器（内嵌官方 2022 漫游）
侧栏可切换地点，或点「开始 / 下一站」按半日路线走。

查看器：http://localhost:8765/?scene=pano923&tour=freshman

路线：
1. 教学区（明理教学楼）— 了解上课位置
2. 图书馆 — 了解学习资源
3. 食堂 — 解决吃饭
4. 思明苑公寓 — 熟悉生活区
5. 三鉴湖 — 认识校园特色

官方总览备用：https://3d.xmut.edu.cn/2022/?startscene=pano926
```

## 意图映射（摘要）

完整别名以 `places.json` 为准。常见映射：

- 看书 / 自习 → 图书馆  
- 上课 / 教室 → 明理教学楼（可提土建学院、综合楼）  
- 吃饭 → 两个食堂场景  
- 宿舍 → 思明苑公寓  
- 运动 / 篮球 → **游泳馆外**（最接近的体育相关公开场景）+ 说明无独立篮球场全景  
- 拍照 / 湖 → 三鉴湖  
- 校门 → 西南大门  

## 边界

- 不编造未在 `places.json` 中的 `scene_id` 或深链
- 不把经验路线说成官方强制参观顺序；半日计划是**探索建议**
- 开放时间、门禁、是否对访客开放：无可靠来源时标明「以学校当日规定为准」
- 2022 公开场景约 13 个，远非校园全部建筑；缺场景时诚实降级，不假装有精确全景

## 回复前自检

- [ ] 是否已读 `places.json`？
- [ ] 默认是否走**内嵌查看器**（`open_scene.py` 无 `--external`）？
- [ ] 是否避免把 `startscene` 加在门户根路径？
- [ ] 本地 8765 起不来时，是否降级并说明？
- [ ] 是否避免做成决策/攻略长文，保持「空间 + 3D」？

## 更多示例与索引

- 对话示例：[references/examples.md](references/examples.md)
- 地点目录：[references/places.json](references/places.json)
- 官方场景表：[references/scene_index.md](references/scene_index.md)
- 内嵌页：[viewer/index.html](viewer/index.html)
- 打开 / 代理：`scripts/open_scene.py`、`scripts/serve_viewer.py`
