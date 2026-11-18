# 推し活日历（Eventernote → ICS）

把 Eventernote 上关注的声优/团体的**全部未来场次**，生成一条可订阅的 iCalendar（.ics）订阅源。配合 Android 的 ICSx⁵ 使用，事件会进入系统日历数据库，系统日历、桌面小部件、提醒都能直接用。

**它不是一份手写日程表。** `feed.ics` 是脚本每天重新抓取网页后覆盖生成的结果文件；场次数会随网页变化，不需要手动维护。

```
Eventernote 艺人页 ──抓取──▶ 合并/去重 ──▶ feed.ics ──订阅──▶ ICSx⁵ ──▶ 系统日历
```

## 当前配置

- 来源：渡瀬結月（`55045`）、川村玲奈（`77840`）、学園アイドルマスター（`77694`）
- 最近一次生成：2026-11-18，**38 场**（13 + 17 + 10，跨来源去重 2 场）
- 更新频率：每天 08:00（北京时间），GitHub Actions
- 团体对照表：18 个团体
- 时区：这批全部是日本场次（`Asia/Tokyo`）

## 文件说明

| 文件 | 作用 |
|---|---|
| `targets.json` | **订阅名单**：`[{"name": "...", "id": "..."}]`，加/减艺人改这里 |
| `eventernote_ics.py` | 主程序：抓取 → 去重 → 生成 `feed.ics` |
| `groups.json` | 团体 → 成员/角色对照表，决定 `团体（成员…）` 怎么显示 |
| `timezones.json` | 会场 → 时区对照表 |
| `tools/gh.py` | 本地管理脚本：通过 GitHub API 改名单、触发 workflow、首次部署 |
| `requirements.txt` | 依赖（只有 lxml） |
| `.github/workflows/update.yml` | 每天定时运行并提交结果 |
| `feed.ics` | 生成物，订阅用 |
| `links_cache.json` / `places_cache.json` | 官方链接、会场地址缓存（自动生成，提交后可减少请求） |
| `make_sample.py` | 生成一份小样例 `sample.ics`，用来预览格式 |
| `HANDOFF.md` | 给新对话用的交接说明（加订阅目标时看它） |

## 部署（GitHub Actions）

1. 新建一个 **public** 仓库（不要勾选自动生成 README）。
2. 把本目录下的文件按原路径上传，注意 `.github/workflows/update.yml` 的路径不能变。
   - 网页拖拽整个文件夹通常可行；如果 `.github` 传不上去，用 “Add file → Create new file”，文件名填 `.github/workflows/update.yml`，再把内容粘进去。
3. 仓库 **Settings → Actions → General → Workflow permissions** 选 **Read and write permissions**，保存。
4. 打开 **Actions → update-feed → Run workflow**，手动跑一次。
5. 等 1–2 分钟，仓库根目录会出现 `feed.ics`。
6. 订阅（二选一）：
   - **jsDelivr**（推荐先试）：`https://cdn.jsdelivr.net/gh/你的用户名/仓库名@main/feed.ics`
   - **GitHub Pages**：Settings → Pages → Deploy from a branch → `main` / `/ (root)`，然后 `https://你的用户名.github.io/仓库名/feed.ics`
7. 在 ICSx⁵ 里添加这个网址，同步间隔设 1–4 小时。
8. 把原来 Eventernote 的订阅删掉，避免重复。

> jsDelivr 对 `@main` 有大约 12 小时缓存，所以更新会有延迟；GitHub Pages 更新更快，但国内访问不一定稳。可以先用 jsDelivr，打不开再换 Pages。

## 让 AI 自动增改（可选）

配置一次 fine-grained token，之后在对话里说“加 XXX”，AI 就能直接改线上 `targets.json` 并触发 workflow，不用你碰网页。

1. 先建一个空的 **public** 仓库（不要初始化 README）。
2. GitHub → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**：
   - Repository access：Only select repositories → 选这个仓库
   - Permissions：**Contents** 读写、**Actions** 读写、**Metadata** 只读（自动带上）
   - 想让它自动把 Actions 权限设成 write，再加 **Administration** 读写；不想给就部署后手动在 Settings 里开
   - 有效期建议 90 天
3. 把 token 和仓库名存到**仓库外面**（不要提交，也不要贴进对话）：
   - `...\default-workspace\.secrets\github_token.txt` → `github_pat_...`
   - `...\default-workspace\.secrets\github_repo.txt` → `用户名/仓库名`
4. 告诉 AI“好了”，它会用 `python tools/gh.py deploy .` 把项目传上去并触发第一次运行。

之后就可以：

```bash
python tools/gh.py status          # 看仓库/分支/名单数量/最近一次运行
python tools/gh.py search 渡瀬結月  # 查 ID
python tools/gh.py add 渡瀬結月 55045
python tools/gh.py remove 55045
```

token 是明文存在本机的，不在仓库里；不想用了随时去 GitHub 撤销。`tools/gh.py` 默认读仓库上一级的 `.secrets/`，换位置时用环境变量 `OSHI_SECRETS_DIR` 指定。

## 日常维护

加订阅目标的完整步骤写在 [HANDOFF.md](HANDOFF.md)，这里只放最常用的三条。

### 加/减艺人

编辑 `targets.json`：

```json
[
  {"name": "渡瀬結月", "id": "55045"},
  {"name": "川村玲奈", "id": "77840"},
  {"name": "学園アイドルマスター", "id": "77694"}
]
```

ID 就是 Eventernote 艺人页 URL 最后那段：`https://www.eventernote.com/actors/川村玲奈/77840` → `77840`。

也可以不走网页，用 `tools/gh.py` 直接改线上仓库（见下一节）。

### 加团体（括号成员）

编辑 `groups.json`，格式是 `[声优名, 角色名]`，没有角色就只写 `["名字"]`：

```json
"Ave Mujica": [
  ["佐々木李子", "三角初華"],
  ["渡瀬結月", "若葉睦"]
]
```

- 只有场次里出现的成员才会写进括号；
- 角色名和声优名都会参与匹配；两个同时出现时显示 `角色/声优`；
- 一个人属于多个团时，每个团都会完整列出（允许重复）。

### 加时区

编辑 `timezones.json`，优先级：`venues`（会场 ID）→ `cities` → `us_states` → `countries`。

日本会场自动按 `Asia/Tokyo` 处理，不需要填。海外会场第一次遇到时会抓会场页取地址，识别不出会按 JST 写入，并在描述里标“时区未识别”，同时日志会提示。

## 显示规则

- 日本场次：`开演 J20:00（B19:00）`，日历时间按 JST 写入，手机在北京自动显示北京时间。
- 海外场次：`开演 当地20:00`，不写北京时间，日历时间按会场时区写入。
- 时间顺序固定为 **开场 → 开演 → 终演**；事件块从开演开始。
- 没有开演时间：做成全天事件，备注“时间未定”。
- 没有场地：`LOCATION` 留空。
- 出场者：分团换行，团内用 `、`，纯个人放最后一行；不截断。
- 链接：与正文空两行，链接之间空一行，官方链接在上、Eventernote 链接在下。
- 不写提醒（`VALARM`），需要的话在 ICSx⁵ 里设默认提醒。

## 排查

| 症状 | 先查 |
|---|---|
| Actions 跑失败 | Actions 日志；多半是网络或 `contents: write` 权限没开 |
| 订阅 404 | 仓库是不是 public、第一次 workflow 有没有跑完 |
| 同一场出现两次 | 旧的 Eventernote 订阅没删 |
| 更新的内容没出现 | jsDelivr 缓存（最多约 12 小时），或 ICSx⁵ 同步间隔 |
| 时间差 1 小时 | 手机时区不是北京；日本/中国都没有夏令时 |
| 海外场次时间不对 | 描述里有没有“时区未识别”，有就补 `timezones.json` |

## 本地运行

```bash
pip install -r requirements.txt
python eventernote_ics.py               # 完整抓取
python eventernote_ics.py --no-details  # 跳过官方链接（更快）
python make_sample.py                   # 生成 sample.ics
```

## 已知限制

- 数据来自 Eventernote，网友众包，可能漏、错、重复；重要场次以官方/票务页为准。
- 订阅是只读的，事件不能在日历里改。
- 海外场次的 `TZID` 使用 IANA 名称、没有附带 `VTIMEZONE` 定义；Android/ICSx⁵ 能解析，个别老客户端可能不认。
- 官方链接有缓存，活动页后来补了链接不会自动更新；想强制刷新就删掉 `links_cache.json` 里对应条目。
- 定时任务可能延迟几分钟到几十分钟；仓库连续 60 天没有提交会被 GitHub 暂停定时任务（本仓库每天提交，一般不会触发）。
- 请控制使用频率，个人订阅量级即可，不要拿去做批量抓取。
