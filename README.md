# WeRead to Obsidian

把腾讯官方微信读书只读数据安全地同步成 Obsidian 阅读看板。项目提供一个本地 Python 同步器、一个轻量 Obsidian 渲染插件，以及不含真实账号数据的离线样例。

![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB)
![Obsidian](https://img.shields.io/badge/Obsidian-1.5%2B-7C3AED)
![License](https://img.shields.io/badge/License-MIT-111827)

![WeRead to Obsidian reading board](docs/reading-board-preview.jpeg)

## 设计重点

- 趋势优先：首屏先看本周阅读时长、天数、完成数和笔记数。
- 滚动画廊：最多展示最近阅读的 5 本公开书籍，支持触控、滚轮和键盘操作。
- 系统审美：使用 Obsidian 语义颜色、Apple 系统字体、44 px 触控目标、浅色/深色模式和减少动态效果偏好。
- 明确状态：区分实时、过期、样例、空数据和错误，不把失败伪装成成功。

## 安全边界

- 只通过 [Tencent/WeChatReading](https://github.com/Tencent/WeChatReading) 的官方只读网关获取账号数据。
- API key 只接受环境变量或 macOS Keychain；不会写入 Vault、日志、Markdown、测试或 Git 仓库。
- 默认排除私密书架条目，不发布原始响应、账号标识或真实阅读数据。
- 网络、解析或分页失败时保留上一份可用看板。
- 单本书笔记导出必须显式执行；脚本只替换唯一、完整的托管区块，其他文字按原字节保留。

## 安装

先安装官方数据源 skill，再安装本项目：

```bash
npx skills add Tencent/WeChatReading -g
npx skills add AprWind/sync-weread-obsidian -g
```

检查 Vault 并安装看板。把示例路径替换为自己的 Obsidian Vault：

```bash
python3 ~/.agents/skills/sync-weread-obsidian/scripts/weread_sync.py doctor \
  --vault "/path/to/your-vault"

python3 ~/.agents/skills/sync-weread-obsidian/scripts/weread_sync.py install \
  --vault "/path/to/your-vault"
```

由用户本人在交互式终端输入 API key。输入不会回显：

```bash
python3 ~/.agents/skills/sync-weread-obsidian/scripts/weread_sync.py configure-key
```

然后执行一次手动实时同步：

```bash
python3 ~/.agents/skills/sync-weread-obsidian/scripts/weread_sync.py sync \
  --vault "/path/to/your-vault"
```

重载 Obsidian 后打开 `00-首页/阅读看板.md`。看板内的刷新按钮只重新读取本地 JSON；网络同步仍由上面的显式命令触发。

## Vault 写入范围

| 路径 | 用途 |
| --- | --- |
| `00-首页/阅读看板.md` | 人可读的看板入口 |
| `.weread/reading-board.json` | 经过裁剪和标准化的本地状态 |
| `.weread/snapshots/YYYY-MM.json` | 实时同步成功后的月度统计快照 |
| `.obsidian/plugins/weread-reading-board/` | 看板渲染插件 |
| `20-认知记录/阅读笔记/` | 仅在显式导出单本书笔记时创建 |

安装器会预检冲突、限制所有目标路径在 Vault 内，并在多文件安装失败时恢复已替换的旧文件。

## 离线验收

仅在一次性测试 Vault 中使用合成样例：

```bash
python3 sync-weread-obsidian/scripts/weread_sync.py install --vault "/tmp/test-vault"
python3 sync-weread-obsidian/scripts/weread_sync.py sync --sample --vault "/tmp/test-vault"
```

不要在已经包含真实阅读数据的 Vault 中运行 `--sample`。

运行项目测试：

```bash
python3 -m unittest discover -s sync-weread-obsidian/scripts/tests -v
node sync-weread-obsidian/assets/tests/reading-board-harness.js
```

## 来源与独立性

本项目借鉴了 [treeboat-weread-style](https://github.com/lulululillian/treeboat-weread-style) 的月度归档、派生数据和横向封面浏览思路，但没有复制其代码或主题。实现重新处理了路径穿越、远程内容注入、托管标记损坏、分页失控、失败回滚、私密条目和减少动态效果等问题。

这是独立项目，不隶属于 Tencent、微信读书或 Obsidian，也不代表这些项目的认可或支持。
