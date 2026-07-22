# MIT 许可与双仓库推送 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为仓库增加 MIT 许可证，并使一次 `git push origin main` 同步 GitHub 与 Gitee。

**Architecture:** 根目录 `LICENSE` 保存标准 MIT License，README 说明许可和可复用的双推送配置。GitHub 继续作为 `origin` 的抓取源，`origin` 通过两个 push URL 依次同步 GitHub 与 Gitee。

**Tech Stack:** Markdown、MIT License、Git configuration、Python `unittest`

---

### Task 1: 添加 MIT License

**Files:**
- Create: `LICENSE`

- [ ] **Step 1: 验证许可证尚不存在**

Run: `test ! -e LICENSE`

Expected: 无输出，退出码为 0。

- [ ] **Step 2: 创建标准 MIT License**

使用标准 MIT License 英文全文，版权行必须为：

```text
Copyright (c) 2026 iTriton Contributors
```

- [ ] **Step 3: 验证关键许可文本**

Run: `rg -n "MIT License|Copyright \(c\) 2026 iTriton Contributors|THE SOFTWARE IS PROVIDED \"AS IS\"" LICENSE`

Expected: 三条表达式均匹配。

### Task 2: 更新中文 README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 添加双仓库同步说明**

增加“同步到 GitHub 与 Gitee”章节，给出以下配置：

```bash
git config --unset-all remote.origin.pushurl 2>/dev/null || true
git config --add remote.origin.pushurl https://github.com/icjs-cc/itriton-skills.git
git config --add remote.origin.pushurl https://gitee.com/itriton/itriton-skills.git
git push origin main
```

说明抓取仍使用 GitHub，并提示多地址推送不是原子操作。

- [ ] **Step 2: 添加开源许可说明**

README 末尾增加“开源许可”章节，写明项目使用 MIT License，并链接 `[LICENSE](LICENSE)`。

- [ ] **Step 3: 校验链接和格式**

Run: `test -f LICENSE && rg -n "\[LICENSE\]\(LICENSE\)|git push origin main" README.md && git diff --check`

Expected: LICENSE 链接和推送命令均匹配，`git diff --check` 无输出。

### Task 3: 配置并验证双仓库推送

**Files:**
- Modify local Git config: `.git/config`

- [ ] **Step 1: 配置 origin 的两个 push URL**

Run:

```bash
git config --unset-all remote.origin.pushurl 2>/dev/null || true
git config --add remote.origin.pushurl https://github.com/icjs-cc/itriton-skills.git
git config --add remote.origin.pushurl https://gitee.com/itriton/itriton-skills.git
```

- [ ] **Step 2: 验证配置**

Run: `git remote get-url origin && git remote get-url --all --push origin`

Expected: 第一条输出 GitHub；push URL 依次输出 GitHub、Gitee，且各出现一次。

- [ ] **Step 3: 运行现有测试**

Run: `python3 -m unittest discover -s tmeet-assistant/tests -v`

Expected: `Ran 13 tests` 和 `OK`。

- [ ] **Step 4: 提交文件改动**

```bash
git add LICENSE README.md
git add -f docs/superpowers/plans/2026-07-22-license-and-mirror-push.md
git commit -m "docs: add MIT license and mirror push guide"
```

- [ ] **Step 5: 一次推送两个仓库**

Run: `git push origin main`

Expected: 输出分别包含 GitHub 和 Gitee 的推送结果。

- [ ] **Step 6: 核对两个远端**

Run: `git ls-remote --heads origin main`，然后运行 `git ls-remote --heads gitee main`。

Expected: 两个 `refs/heads/main` 均等于本地 `git rev-parse HEAD`。
