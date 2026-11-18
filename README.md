# Eventernote → ICS

把 [Eventernote](https://www.eventernote.com) 上关注的声优、偶像、团体的活动日程，生成一条可订阅的 iCalendar（`.ics`）订阅源。

配合 Android 的 [ICSx⁵](https://icsx5.bitfire.at/)，事件会写入系统日历数据库，系统日历、桌面小部件和提醒都能直接用，不需要额外的日历 App。

## 特性

- 从 Eventernote 艺人页抓取未来场次，按活动 ID 去重
- 支持同时订阅多个艺人/团体，同一活动只出现一次
- 出演者按团体分组显示，角色名与声优名可以对应
- 日本场次写入 `Asia/Tokyo` 时区，海外场次按会场时区写入
- 自动抓取活动页的官方链接
- GitHub Actions 每天定时更新，不需要自己的服务器
- 输出标准 ICS，任何日历客户端都能订阅

## 工作原理

```
targets.json（订阅名单）
  → Eventernote 艺人页
  → 解析：日期 / 开场·开演·终演 / 会场 / 出演者
  → 按活动 ID 去重 → 时区 → 官方链接
  → feed.ics
  → GitHub Actions 每天提交
  → 日历客户端订阅 feed.ics 的 URL
```

## 快速开始

1. 新建一个 **public** 仓库，把本项目文件按原路径上传
2. 编辑 `targets.json`，填入要订阅的艺人和 ID
3. 仓库 **Settings → Actions → General → Workflow permissions** 选 **Read and write permissions**
4. **Actions → update-feed → Run workflow**，等 1–2 分钟
5. 订阅 `https://cdn.jsdelivr.net/gh/<用户名>/<仓库>@main/feed.ics`

## 配置

### `targets.json`

订阅名单，一个对象一个目标：

```json
[
  {"name": "示例艺人", "id": "12345"},
  {"name": "示例团体", "id": "67890"}
]
```

`id` 是 Eventernote 艺人页 URL 的最后一段：

```
https://www.eventernote.com/actors/示例艺人/12345
                                      └── 12345
```

### `groups.json`

团体 → 成员/角色对照表，决定出演者怎么分组显示：

```json
{
  "示例团体": [
    ["声优A", "角色A"],
    ["声优B"]
  ]
}
```

- 只有活动出演者里出现的成员才会写进括号
- 角色名和声优名都参与匹配，忽略空格差异
- 两者同时出现时显示 `角色/声优`
- 同一人属于多个团体时，每个团体都会完整列出
- 不在表里的团体不展开括号，和纯个人一起放在最后一行

### `timezones.json`

会场 → 时区对照表，优先级：`venues`（会场 ID）→ `cities` → `us_states` → `countries`。

```json
{
  "venues": {"1234": "America/Los_Angeles"},
  "cities": {"Seoul": "Asia/Seoul"},
  "us_states": {"CA": "America/Los_Angeles"},
  "countries": {"Republic of Korea": "Asia/Seoul"}
}
```

日本会场自动按 `Asia/Tokyo` 处理，不需要配置。海外会场第一次遇到时会抓会场页取地址，识别不出会按 JST 写入并在描述里标注。

## 部署

1. 新建 **public** 仓库（不要初始化 README）
2. 上传全部文件，保持 `.github/workflows/update.yml` 的路径不变
3. **Settings → Actions → General → Workflow permissions** 选 **Read and write permissions**
4. **Actions → update-feed → Run workflow**
5. 仓库根目录出现 `feed.ics` 后即可订阅

订阅地址二选一：

| 方式 | 地址 | 说明 |
|---|---|---|
| jsDelivr | `https://cdn.jsdelivr.net/gh/<用户名>/<仓库>@main/feed.ics` | 国内一般可访问，有约 12 小时缓存 |
| GitHub Pages | `https://<用户名>.github.io/<仓库>/feed.ics` | 更新更快，需要开启 Pages，国内访问不一定稳 |

## 订阅

1. 在 ICSx⁵ 里点 `+`，粘贴上面的 URL
2. 设置名称、颜色和同步间隔（建议 1–4 小时）
3. 保存后，在系统日历的「要显示的日历」里勾选它

> 如果之前用 Eventernote 自带的日历同步，记得删掉旧订阅，避免同一活动出现两次。

## 输出格式

- **日本场次**：`开演 J20:00（B19:00）`，按 JST 写入，手机在北京自动显示北京时间
- **海外场次**：`开演 当地20:00`，不写北京时间，按会场时区写入
- **时间顺序**：开场 → 开演 → 终演；事件块从开演开始
- **没有开演时间**：全天事件，备注“时间未定”
- **没有场地**：`LOCATION` 留空
- **出演者**：分团换行，团内用 `、`，纯个人放最后一行，不截断
- **链接**：正文与第一条链接之间空两行，链接之间空一行，官方链接在上
- **提醒**：不写入 `VALARM`，由日历客户端自行设置

## 本地运行

```bash
pip install -r requirements.txt
python eventernote_ics.py               # 完整抓取
python eventernote_ics.py --no-details  # 跳过官方链接
python make_sample.py                   # 生成 sample.ics 预览格式
```

需要 Python 3.10+。

## 目录结构

```
.
├── eventernote_ics.py          # 主程序
├── targets.json                # 订阅名单
├── groups.json                 # 团体成员对照表
├── timezones.json              # 时区对照表
├── tools/gh.py                 # 可选：通过 GitHub API 管理名单
├── make_sample.py              # 生成格式样例
├── requirements.txt
├── .github/workflows/update.yml
└── feed.ics                    # 生成物
```

## 常见问题

| 症状 | 排查 |
|---|---|
| Actions 失败 | 看运行日志；确认 Workflow permissions 是 Read and write |
| 订阅 404 | 仓库是否 public；第一次 workflow 是否跑完 |
| 同一活动出现两次 | 是否还留着 Eventernote 自带的订阅 |
| 更新没出现 | jsDelivr 缓存（约 12 小时），或客户端同步间隔 |
| 时间差 1 小时 | 手机时区设置；日本和中国都没有夏令时 |
| 海外时间不对 | 描述里是否有“时区未识别”，有就补 `timezones.json` |
| 某个艺人 0 场 | 检查 `targets.json` 里的 ID 是否正确 |

## 已知限制

- 数据来自 Eventernote，由网友众包维护，可能漏、错、重复；重要场次以官方页面为准
- 订阅是只读的，事件不能在日历里修改
- 海外场次使用 IANA 时区名写入，没有附带 `VTIMEZONE` 定义；Android/ICSx⁵ 可以解析，个别老客户端可能不认
- 官方链接有缓存，活动页后来补充的链接不会自动更新
- 定时任务可能延迟几分钟到几十分钟
- 请控制请求频率，个人订阅量级即可
