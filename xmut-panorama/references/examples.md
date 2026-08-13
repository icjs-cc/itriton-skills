# 厦理全景地图 · 对话示例

深链均指向 2022 版：`https://3d.xmut.edu.cn/2022/?startscene=...`

---

## 1. 单点：图书馆

**用户：** 厦理工图书馆在哪里？

**Agent 动作：** `python3 scripts/open_scene.py 图书馆`（默认内嵌查看器）

**Skill：**

📚 厦门理工学院图书馆

这里是学校主要的学习资源场所，适合看书与自习。

📍 区域  
学习资源区（公开全景场景）

🗺️ 3D校园地图  
✅ 已在本地内嵌查看器打开  
查看器：http://localhost:8765/?scene=pano1083
官方备用：https://3d.xmut.edu.cn/2022/?startscene=pano1083

附近：
- 明理教学楼
- 食堂

---

## 2. 自然语言：打球

**用户：** 我想找可以打篮球的地方。

**Skill：**

公开 2022 全景里**没有**独立的「篮球场」场景。运动相关可先看：

🏃 **游泳馆外**（最接近的体育设施全景）  
[进入游泳馆外3D全景](https://3d.xmut.edu.cn/2022/?startscene=pano921)

🔎 **空中全景**（在图上找体育区域相对位置）  
[打开空中全景](https://3d.xmut.edu.cn/2022/?startscene=pano926)

进入后可点界面里的「地图」进一步定位。若你告诉我更靠近宿舍还是教学楼，我可以只保留更相关的入口。

---

## 3. 列举：食堂

**用户：** 厦理工有哪些食堂？

**Skill：**

🍜 校园餐饮（3D 已收录场景）

1. [食堂（场景A）](https://3d.xmut.edu.cn/2022/?startscene=pano924)
2. [食堂（场景B）](https://3d.xmut.edu.cn/2022/?startscene=pano925)

说明：官方全景标题均显示为「食堂」，未在公开数据里区分正式食堂名。

若要按「预算 / 口味 / 离哪近」筛选，那是决策问题；在这里你可以告诉我离图书馆还是宿舍更近，我帮你选对应 3D 入口。

---

## 4. 带我逛校园

**用户：** 带我逛一下厦理工。

**Skill：**

🎓 厦理工3D校园漫游

你可以选择：

① 🏫 教学区 → [明理教学楼](https://3d.xmut.edu.cn/2022/?startscene=pano923)  
② 📚 图书馆 → [图书馆](https://3d.xmut.edu.cn/2022/?startscene=pano1083)  
③ 🍜 食堂 → [食堂](https://3d.xmut.edu.cn/2022/?startscene=pano924)  
④ 🏠 宿舍区 → [思明苑公寓](https://3d.xmut.edu.cn/2022/?startscene=pano922)  
⑤ 🏃 体育设施 → [游泳馆外](https://3d.xmut.edu.cn/2022/?startscene=pano921)  
⑥ 🌳 校园景观 → [三鉴湖](https://3d.xmut.edu.cn/2022/?startscene=pano916)  
⑦ 🔎 随便逛逛 → [空中全景](https://3d.xmut.edu.cn/2022/?startscene=pano926)

回我编号即可。

---

## 5. Demo：新生半日（推荐现场展示）

**用户：** 我是刚到厦理工的新生，只有一个下午，帮我快速熟悉一下校园。

**Agent 动作：** `python3 scripts/open_scene.py --tour freshman`  
打开本地内嵌查看器；用户可在侧栏切换，或点「开始 / 下一站」。不要一次打开多个外部官网标签页。
