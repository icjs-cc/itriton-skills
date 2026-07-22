# MIT 许可与双仓库推送设计

## 目标

为 `itriton-skills` 增加标准 MIT 开源许可证，并配置一次 Git 推送同时同步 GitHub 与 Gitee。

## 开源许可

仓库根目录新增 `LICENSE`，使用标准 MIT License 全文。版权声明固定为：

```text
Copyright (c) 2026 iTriton Contributors
```

README 增加“开源许可”章节，链接到 `LICENSE`，不自行改写许可证条款。

## 双仓库推送

保留 `origin` 的抓取地址为 GitHub：

```text
https://github.com/icjs-cc/itriton-skills.git
```

为 `origin` 配置两个 push URL：

```text
https://github.com/icjs-cc/itriton-skills.git
https://gitee.com/itriton/itriton-skills.git
```

配置完成后，执行 `git push origin main` 会依次推送两个地址。现有 `gitee` 远程继续保留，便于单独同步和排查。

README 增加可复制的配置命令，并说明多地址推送不是原子操作：若某一远程失败，另一远程可能已经成功，应修复失败原因后重试并核对两个远端提交。

## 验证与交付

- 检查 `LICENSE` 包含标准 MIT 文本、正确年份和版权主体。
- 检查 README 中的 `LICENSE` 相对链接有效。
- 检查 `remote.origin.pushurl` 正好包含 GitHub 和 Gitee 两个地址。
- 运行现有 13 项单元测试，确认文档改动未影响技能脚本。
- 提交文件改动后执行一次 `git push origin main`。
- 分别查询 GitHub 和 Gitee 的 `main`，确认均指向本地 `HEAD`。
