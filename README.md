# ACL4SSR-Neo 🚀

> 基于 [ACL4SSR](https://github.com/ACL4SSR/ACL4SSR) 规则深度定制的订阅转换规则仓库，面向 Clash / Mihomo 等常见代理生态，整合了多家优质去广告规则源。
>
> 📍 **项目规划**：查看我们的 [未来路线图 (Roadmap)](./ROADMAP.md)

---

## 项目边界

本仓库是公开的代理规则与配置仓库，只维护 ACL4SSR/subconverter 配置、Clash/Mihomo 规则、通用构建脚本和自动同步流程。

以下内容不属于本项目，禁止提交到本仓库：

- 代理面板、订阅后端或控制平面的配置与修复脚本
- VPS、Xray、REALITY、SSH、Docker 或防火墙部署操作
- 实际面板域名、服务器地址、账号、令牌、密钥或私钥
- 绑定某个私有部署环境的模板和 provider 拆分逻辑；通用、无地址/凭据的客户端模板允许维护

仓库 CI 会对代码和配置目录执行边界与明显敏感信息检查。

---

## ✨ 特性

- 🎯 **精细分流**：按服务类型独立分组，国内直连 / 国外代理 / 媒体解锁开箱即用
- 🤖 **AI 深度优化**：针对 OpenAI、Claude、Gemini 独立分流，支持全节点独立手动/自动切换
- 🛡️ **Claude 防漏风控**：Claude 组强制禁直连，彻底杜绝因代理失效导致的真实 IP 泄露封号风险
- 🎬 **全球媒体解锁**：对齐 `RegionRestrictionCheck` 检测颗粒度，支持主流流媒体（Netflix/Disney+/HBO/PrimeVideo）及各国地区媒体独立分流
- 🛑 **多源去广告**：整合仓库规则与持续维护的 EasyList 系列上游，经过确定性去重和冲突处理
- 🎮 **Steam 专项优化**：针对前台社区与后台下载三级分流，强制代理与优先直连动态结合
- 🗺️ **智能区域路由**：自动按节点名称匹配🇩🇪德 / 🇭🇰港 / 🇨🇳台 / 🇸🇬新 / 🇯🇵日 / 🇺🇸美 / 🇰🇷韩；无匹配时回退全局自动组，不生成空组
- ✏️ **自定义直连表**：`CustomDirect.list` 优先级最高，可随时追加你自己的直连域名

---

## 📁 项目结构 (Active/Inactive Architecture)

```text
Config/
├── ACL4SSR_Online_Full.ini   # 当前 Subconverter 主配置入口
├── GeneralConfig.yml         # 主配置使用的基础模板
├── DynamicRegionContext.j2   # 根据节点显示名构建可用地区集合
└── DynamicProxyGroups.yml.j2 # 只渲染真实地区组的通用 Mihomo/Jinja partial

Legacy/
└── subconverter_pref.ini    # 历史示例文件，仅供参考
```

```text
Rules/
├── Core/                # 核心直连、代理规则和 GFWList 人工补充源
├── Ruleset/
│   ├── Active/          # 当前主配置和构建链路真正使用的规则
│   ├── Inactive/        # 保留但未接线的专题规则
│   ├── Active/China/    # 中国直连相关基础规则
│   └── Active/AdBlock/  # 广告与隐私原料规则
└── Outputs/             # 广告与隐私成品列表（MergedADBan / MergedPrivacy）
```

```text
scripts/
├── fetch_assets.py      # 事务式同步 GFWList / China / AdBlock 上游数据
├── build_rules.py       # 可复现地构建广告和隐私成品规则
├── sync_guard.py        # 自动同步后的轻量护栏，拦截空文件/异常小文件/错误页
├── dedupe_rules.py      # 去除 .list 文件内重复有效规则
├── audit_rules.py       # 可选手动审计：跨文件重复、覆盖关系、私有规则泄漏等
├── validate_rules.py    # 校验配置引用、YAML、规则类型和 CIDR 语义
├── check_repo_scope.py  # 阻止部署代码和明显敏感信息进入公开仓库
├── apply_dynamic_groups.py # 将通用动态地区组应用到 Jinja-enabled Clash 模板
└── list_to_yaml.py      # 通用 Mihomo classical rule-provider 转换工具
```

---

## 🚀 快速使用

配合 [Subconverter](https://github.com/tindy2013/subconverter) 在线订阅转换工具使用：

将以下地址作为「远程配置」粘贴到转换面板的配置文件栏：

```text
https://raw.githubusercontent.com/E-R-Butch/ACL4SSR-Neo/master/Config/ACL4SSR_Online_Full.ini
```

然后填入你的节点订阅地址，即可生成完整 Clash 配置。

---

## 🛠️ 维护与自动同步

PR 和推送会运行只读 CI，检查仓库边界、单元测试、重复规则、配置引用、YAML、规则类型和 CIDR。每日同步会完整拉取全部上游数据，任一强制来源失败即停止；全部转换成功后才替换正式文件，再执行护栏、构建和校验。无规则语义变化时不会创建自动提交。

如需更深入地排查规则质量，可手动运行 `python3 scripts/audit_rules.py`。该工具默认只输出报告，不参与每日 CI；需要让发现项返回失败状态时，可加 `--strict`。

---

## 🗂️ 策略组一览

| 策略组 | 类型 | 默认 | 说明 |
| :--- | :--- | :--- | :--- |
| 🚀 节点选择 | select | ♻️ 自动选择 | 主出口，统筹全局 |
| 🚀 手动切换 | select | — | 手动节点全量列表 |
| ♻️ 自动选择 | url-test | — | 全节点自动测速 |
| 🤖 OpenAI | select | 自动/手动 | ChatGPT 相关服务，支持全节点自动优选 |
| 🎭 Claude | select | 自动/手动 | Anthropic/Claude 服务，**强制禁直连**防封号 |
| 🧠 Gemini | select | 自动/手动 | Google Gemini AI 相关服务 |
| 🚀 Grok | select | 自动/手动 | xAI Grok 相关服务，独立分组 |
| 🎥 奈飞视频 | select | 自动过滤 | 自动筛选解锁节点，独立分组 |
| 🎬 迪士尼+ | select | 节点选择 | Disney+ 专用分组 |
| 🎥 HBO Max | select | 节点选择 | HBO Max / Max |
| 🎬 亚马逊视频 | select | 节点选择 | Amazon Prime Video |
| 🎼 海外音乐平台 | select | 节点选择 | Spotify, JOOX, KKBOX, Qobuz, TIDAL, YouTube Music, Pandora, Deezer, SoundCloud |
| 📹 油管视频 | select | 节点选择 | YouTube / YT Music |
| 🇭🇰 香港媒体 | select | 香港节点 | ViuTV, MyTV Super 等 |
| 🇨🇳 台湾媒体 | select | 台湾节点 | 巴哈姆特, KKTV, LiTV 等 |
| 🇯🇵 日本媒体 | select | 日本节点 | Abema, DMM, TVer 等 |
| 🇰🇷 韩国媒体 | select | 韩国节点 | Wavve, Tving 等 |
| 🇺🇸 北美媒体 | select | 美国节点 | Hulu, Paramount, Peacock 等 |
| 📲 电报消息 | select | 节点选择 | Telegram 专用分组 |
| 🎮 游戏代理 | select | 🚀 节点选择 | Steam 社区、商店，以及需要代理的游戏平台域名 |
| 🎮 游戏直连 | select | DIRECT | Steam 下载、Epic、Uplay、暴雪、PlayStation 等可直连平台域名 |
| Ⓜ️ 微软云盘 | select | DIRECT | OneDrive 专用分组 |
| 🍎 苹果服务 | select | DIRECT | Apple 相关服务 |
| 🛑 广告拦截 | select | REJECT | 多源合并广告规则 |
| 🔒 隐私保护 | select | REJECT-DROP | 隐私追踪与设备遥测拦截 |
| 🎯 全球直连 | select | DIRECT | 国内 / 自定义直连 |
| 🐟 漏网之鱼 | select | DIRECT | 未匹配规则兜底 |
| 🇩🇪/🇭🇰/🇨🇳/🇸🇬/🇯🇵/🇺🇸/🇰🇷 节点 | url-test | ♻️ 自动选择 | 按地区名自动归类；无匹配时保持非空 fallback |

通用 Subconverter 配置会保留所有地区组，并在地区正则没有命中时引用 `♻️ 自动选择`。Jinja partial 则更进一步：仅渲染实际存在节点的地区组；没有对应节点的地区媒体组直接回退 `🚀 节点选择`，不会把其他国家节点伪装成该地区。

---

## 📜 规则来源致谢

| 规则源 | 说明 |
| :--- | :--- |
| [LoveMyself546/ACL4SSR](https://github.com/LoveMyself546/ACL4SSR) | 本项目直接溯源 (Fork 来源) |
| ~~ACL4SSR/ACL4SSR~~ | 本项目初代规则集 (源项目已失效) |
| ~~ConnersHua/Profiles~~ | 广告/劫持拦截规则 (源项目已失效) |
| ~~lhie1/Rules~~ | 广告拦截规则 (源项目已失效) |
| [blackmatrix7/ios_rule_script](https://github.com/blackmatrix7/ios_rule_script) | lhie1 归档的社区维护版 |
| [easylist/easylist](https://github.com/easylist/easylist) | 广告与隐私规则上游来源（EasyList / EasyListChina / EasyPrivacy） |
| [Adblock Plus Filter Lists](https://easylist-downloads.adblockplus.org/) | 本项目自动同步使用的官方发布地址 |
| [lmc999/RegionRestrictionCheck](https://github.com/lmc999/RegionRestrictionCheck) | 流媒体解锁检测脚本（本项目对齐其颗粒度） |
| [gfwlist/gfwlist](https://github.com/gfwlist/gfwlist) | 本项目核心代理列表（GFWList）的官方来源 |
| [mayaxcn/china-ip-list](https://github.com/mayaxcn/china-ip-list) | 本项目中国 IP 列表的核心来源 |

---

## 📝 许可证

本项目基于 [GNU General Public License v3.0](./LICENCE) 开源。
