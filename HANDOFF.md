# HANDOFF — 给新对话的交接说明

> 目的：以后要加/减订阅目标时，新对话读完这个文件就能直接改线上仓库，不用重新翻聊天记录。

## 怎么用

把下面这句发给新对话：

```
读 eventernote-ics/HANDOFF.md，帮我加订阅目标：<艺人名或 eventernote 链接>。
用 tools/gh.py 直接改线上仓库，改完告诉我。
```

## 一句话现状

`eventernote-ics/` 是一个 Python 脚本 + GitHub Actions 项目：每天抓 Eventernote 艺人页，生成 `feed.ics`，用 ICSx⁵ 订阅进 Android 系统日历。**活动不写死**，每次运行都重新抓。

订阅名单在 `targets.json`，可以本地改，也可以由 AI 通过 `tools/gh.py` 直接提交到 GitHub。

## 自动增改（AI 用）

凭证放在仓库**外面**，不会提交：

- `.secrets/github_token.txt`：fine-grained PAT
- `.secrets/github_repo.txt`：`owner/repo`

`tools/gh.py` 的常用命令（在 `eventernote-ics/` 目录下运行）：

```bash
python tools/gh.py status                 # 仓库、分支、targets 数量、最近一次运行
python tools/gh.py list                   # 当前订阅名单
python tools/gh.py search 示例艺人        # 查 ID（只返回真正的搜索结果）
python tools/gh.py add 示例艺人 12345     # 追加 + 提交 + 触发 workflow
python tools/gh.py add-url https://www.eventernote.com/actors/示例艺人/12345
python tools/gh.py remove 12345           # 删除 + 提交 + 触发
python tools/gh.py dispatch               # 只触发生成
python tools/gh.py deploy .               # 首次部署整个目录
python tools/gh.py set-permissions        # 尝试把 Actions 权限设为 write
```

### 用户说“加 XXX”时的标准流程

1. `python tools/gh.py search XXX`
2. 如果只有一条结果 → 直接 `add`；如果多条 → 把候选列给用户，让他选（不要猜）
3. `add` 自带 commit + dispatch，约 1–2 分钟后 `feed.ics` 更新
4. 回复用户：加了谁、ID、多少条候选、订阅链接不变

### 用户说“删 XXX”时

1. `python tools/gh.py list` 找到对应 ID
2. `python tools/gh.py remove <id>`

### 凭证缺失时

如果 `.secrets` 不存在，让用户按 README 的“让 AI 自动增改”一节创建 token，**不要**让用户把 token 贴在对话里。

## 数据流

```
targets.json（订阅名单）
  → https://www.eventernote.com/actors/<id>/events（按日期倒序，20 条/页）
  → 解析：日期 / 标题 / 会场 / 開場・開演・終演 / 出演者
  → 按 event id 去重（跨艺人合并）
  → 会场页取地址 → 时区
  → 活动页取「関連リンク」→ 官方链接（有缓存）
  → 生成 feed.ics（覆盖）
  → GitHub Actions 每天 20:00 UTC（北京时间 04:00）提交
  → 用户订阅 jsDelivr / Pages 的 feed.ics
```

## 文件职责

| 文件 | 改不改 | 说明 |
|---|---|---|
| `targets.json` | **加/减订阅时改这里** | `[{"name": "...", "id": "..."}]` |
| `eventernote_ics.py` | 一般不动 | 主程序；`ACTORS` 只是 targets.json 缺失时的兜底 |
| `groups.json` | 加团体时改 | 团体→成员/角色 |
| `timezones.json` | 海外会场识别不出时改 | 会场/城市/州/国家→IANA 时区 |
| `tools/gh.py` | 一般不动 | 本地管理脚本（GitHub API） |
| `requirements.txt` | 一般不动 | `lxml` |
| `.github/workflows/update.yml` | 一般不动 | 定时任务 |
| `feed.ics` | **不要手改** | 生成物 |
| `links_cache.json` / `places_cache.json` | 一般不动 | 缓存；删条目可强制刷新 |
| `make_sample.py` | 可选 | 生成 `sample.ics` 预览格式 |

## 加团体成员（`groups.json`）

格式：`"団体名": [["声优名", "角色名"], ["只有声优"]]`

```json
"示例团体": [
  ["声优A", "角色A"],
  ["声优B", "角色B"]
]
```

规则（代码已实现，不要重写）：

- 只有**场次出演者里出现**的成员才会写进括号；没出现的不补。
- 角色名和声优名都参与匹配（忽略空格差异）。
- 角色和声优同时出现 → 显示 `角色/声优`。
- 同一人属于多个团 → **每个团都完整列出**，允许重复，不做全局去重。
- 团体名出现在出演者里才展开括号；没出现就按普通名字处理。
- 表里没有的团体 → 不括号，和纯个人一起放最后一行。

## 加时区（`timezones.json`）

优先级：`venues`（会场 ID）→ `cities` → `us_states` → `countries`。

```json
{
  "venues": { "2652": "America/Los_Angeles" },
  "cities": { "Seoul": "Asia/Seoul" },
  "us_states": { "CA": "America/Los_Angeles" },
  "countries": { "Republic of Korea": "Asia/Seoul" }
}
```

- 日本会场自动 `Asia/Tokyo`，不用填。
- 海外会场第一次遇到会抓 `/places/<id>` 取地址；识别不出 → 按 JST 写，描述里标“时区未识别”，日志提示补表。
- 改完提交即可，`places_cache.json` 里已有的会场会跳过抓取。

## 不能改的格式约定

- 日本场次：`开场 J10:00（B09:00）`、`开演 J12:00（B11:00）`、`终演 …`，顺序固定 **开场 → 开演 → 终演**。
- 海外场次：`开演 当地20:00`，**不写 B**。
- 事件块 `DTSTART` 用**开演**时间；没有开演时间 → 全天事件 + “时间未定”。
- 日历名 `推し活`；不写 `VALARM`（提醒交给 ICSx⁵ 默认设置）。
- 出演者：`出演：` 后分团换行 `・団体（a、b）`，纯个人最后一行。
- 链接：正文与第一条链接之间**空两行**，链接之间**空一行**，官方链接在 Eventernote 链接**上面**。
- `UID` 固定 `eventernote-<event id>@eventernote-ics`——**不要改**，改了会在日历里出现重复。
- 不写“来源”行。

## 缓存

- `links_cache.json`：`event id → 官方链接列表`。活动页后来补链接不会更新；删掉对应条目即可重抓。
- `places_cache.json`：`会场 id → {address, overseas}`。删掉可重新取地址。
- 两个文件都由 workflow 自动提交，不用手动维护。

## 验证清单

- [ ] `python tools/gh.py status` 显示 targets 数量正确
- [ ] `python eventernote_ics.py` 无异常
- [ ] 输出 `Merged: N unique events`，N 与预期接近
- [ ] `non-JST events` 数量符合预期（没有海外场就是 0）
- [ ] `feed.ics` 里 `BEGIN:VEVENT` 数量 = N，无超过 75 字节的行
- [ ] 抽一场：`SUMMARY`、`DTSTART;TZID=`、`DESCRIPTION` 的换行/空行正确
- [ ] 同一活动没有出现两条（UID 唯一）
- [ ] 有官方链接的场次，官方链接在 Eventernote 链接上面

## 常见故障

| 症状 | 原因 |
|---|---|
| Actions 失败 | `contents: write` 没开；或网络问题 |
| 订阅 404 | 仓库不是 public；首次 workflow 没跑完 |
| 重复事件 | 旧的 Eventernote 订阅没删；或有人改了 `UID` |
| 更新不出现 | jsDelivr 缓存（~12h）；ICSx⁵ 同步间隔 |
| 时间差 1 小时 | 手机时区不是北京（日本/中国无夏令时） |
| 海外时间错 | 时区表没命中，描述里会有“时区未识别” |
| `gh.py` 401/403 | token 过期、权限不足、repo 名写错 |
| 抓取报错 | Eventernote 页面结构变了，检查 `parse_actor_page` 的 XPath |

## 不要做

- 不要把活动列表写死进代码或 JSON。
- 不要改 `UID` 格式。
- 不要加 `VALARM`。
- 不要把 `.secrets` 提交进仓库，也不要在对话里贴 token。
- 不要提交 `feed_preview.txt`、`sample_preview.txt` 这类调试文件。
- 不要在 CI 里设 `EVENTERNOTE_INSECURE=1`（那是本地沙箱调试用的）。
- 不要用批量并发抓取；脚本自带 0.8s 间隔，保持。
