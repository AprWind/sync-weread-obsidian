# WeRead to Obsidian

把腾讯官方微信读书的只读数据，整理成一个本地、私有的 Obsidian 阅读看板。它由 Python 同步器、轻量渲染插件和不含真实账号数据的离线样例组成；微信读书始终是账号数据的来源，Obsidian 只保存经过裁剪的派生视图。

![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB)
![Obsidian](https://img.shields.io/badge/Obsidian-1.5%2B-7C3AED)
![License](https://img.shields.io/badge/License-MIT-111827)

![WeRead to Obsidian reading board](docs/reading-board-preview.jpeg)

## 看板体验

- **封面先行**：首屏是一条高密度、逻辑无缝的封面循环带，而不是一个通用数据仪表盘。画廊最多展示本地状态中合并并去重后的 12 册书；所选书籍会展开为进度、阅读时长、最近阅读、笔记计数和可用链接。
- **可控而不打扰**：支持播放/暂停、鼠标或触控拖拽、滚轮横移、左右方向键与可见焦点；悬停、聚焦、拖拽和离屏时会暂停。系统启用“减少动态效果”时不会自动滚动。
- **有纵深的回顾**：按本月、本周、今天与年度查看阅读，并提供日历、年度视图中的最近 12 个月历史、按 `06:00 → 05:00` 排列的阅读时钟、分类和读书/听书占比。
- **克制的笔记入口**：展示最近有活动的书及其划线/想法/书签计数，不默认读取或展示任何笔记正文。
- **系统般的安静感**：遵循 Obsidian 语义色和系统字体，支持浅深色、键盘与 44 px 触控目标；显示本地数据的同步时间，并明确呈现样例、空数据和读取错误。

## 安全与数据边界

- 账号数据仅通过 [Tencent/WeChatReading](https://github.com/Tencent/WeChatReading) 官方 skill 的只读网关读取。
- API key 仅由用户在交互式 `configure-key` 中输入，存放在 macOS Keychain（或由用户自行设置的环境变量）中；不会读取剪贴板，也不会写入 Vault、日志、命令行、Markdown、测试或 Git 仓库。替换已有 Key 时会原位更新，底层写入失败不会先删除旧凭据。
- 私密书架条目的元数据不会进入看板；仅保留一个聚合数量。不会保存原始响应、账号标识、封面缓存或真实样例数据。
- 默认看板不请求笔记正文。只有明确指定一本书时，`export-notes` 才会读取并导出该书笔记。
- 网络、解析、分页或校验失败时，保留上一份可用看板，绝不把失败写成“已同步”。若收到 `401`，请从官方渠道取得新的 key 并重新运行 `configure-key`。

## 安装与使用

先安装官方数据源 skill，再安装本项目：

```bash
npx skills add Tencent/WeChatReading -g
npx skills add AprWind/sync-weread-obsidian -g
```

对自己的 Vault 运行检查并安装。将 `/path/to/your-vault` 换成包含 `.obsidian` 目录的实际路径：

```bash
python3 ~/.agents/skills/sync-weread-obsidian/scripts/weread_sync.py doctor \
  --vault "/path/to/your-vault"

python3 ~/.agents/skills/sync-weread-obsidian/scripts/weread_sync.py install \
  --vault "/path/to/your-vault"
```

由用户本人通过 macOS 本地安全输入框录入 key；输入只会传给 Keychain，不读取剪贴板内容，也不应粘贴到聊天、文件或命令参数中：

```bash
python3 ~/.agents/skills/sync-weread-obsidian/scripts/weread_sync.py configure-key --gui
```

无图形界面时可省略 `--gui`，改用不会回显的终端输入。

再执行一次手动实时同步：

```bash
python3 ~/.agents/skills/sync-weread-obsidian/scripts/weread_sync.py sync \
  --vault "/path/to/your-vault"
```

重载 Obsidian 后，打开 `00-首页/阅读看板.md`。看板内的刷新按钮只重新读取本地 `.weread/reading-board.json`，网络同步仍须由上述显式命令触发。

如官方网关返回 `401`，不要反复重试或暴露旧 key：从官方渠道获取新 key，重新运行 `configure-key`，再执行 `doctor` 和 `sync`。

## Vault 写入范围

| 路径 | 用途 |
| --- | --- |
| `00-首页/阅读看板.md` | 人可读的看板入口 |
| `.weread/reading-board.json` | schema v2 的裁剪、标准化本地状态 |
| `.weread/snapshots/YYYY-MM.json` | 实时同步成功后的月度统计快照 |
| `.obsidian/plugins/weread-reading-board/` | 看板渲染插件 |
| `20-认知记录/阅读笔记/` | 仅在显式导出单本书笔记时创建 |

安装器会在写入前检查看板、社区插件清单和同名渲染插件的所有权；已安装的本项目版本会取得稳定标记，未知或第三方目录会原样拒绝。所有目标均限制在 Vault 内，多文件安装失败时会恢复调用前的文件状态。

## 离线验收

仅在一次性测试 Vault 中使用合成样例：

```bash
python3 sync-weread-obsidian/scripts/weread_sync.py install --vault "/tmp/test-vault"
python3 sync-weread-obsidian/scripts/weread_sync.py sync --sample --vault "/tmp/test-vault"
```

不要在已有真实阅读数据的 Vault 中运行 `--sample`。它会替换该 Vault 的看板数据，但不会访问账号。

导出笔记必须显式指定一本书：

```bash
python3 ~/.agents/skills/sync-weread-obsidian/scripts/weread_sync.py export-notes \
  --vault "/path/to/your-vault" --book-id "stable-book-id"
```

运行项目测试：

```bash
python3 -m unittest discover -s sync-weread-obsidian/scripts/tests -v
node sync-weread-obsidian/assets/tests/reading-board-harness.js
```

## 来源与独立实现

本项目独立实现了月度回顾、派生阅读数据与横向封面浏览的体验。它参考了 [treeboat-weread-style](https://github.com/lulululillian/treeboat-weread-style) 所呈现的产品行为和信息组织，并在此基础上重新设计为可访问、可暂停、支持减少动态效果的逻辑无缝循环。未复制该项目的代码、样式、文字或素材。

本项目不隶属于 Tencent、微信读书或 Obsidian，也不代表这些项目的认可或支持。
