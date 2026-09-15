# ACL4SSR-Redux 🚀

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
- 🛡️ **Claude 代理隔离**：使用专用自动/手动组，所有嵌套路径均禁用 DIRECT；没有可用节点时拒绝连接。此约束针对规则模式，不覆盖客户端全局直连模式或应用绕过代理的流量。
- 🎬 **全球媒体解锁**：对齐 `RegionRestrictionCheck` 检测颗粒度，支持主流流媒体（Netflix/Disney+/HBO/PrimeVideo）及各国地区媒体独立分流
- 🛑 **多源去广告**：整合仓库规则与持续维护的 EasyList 系列上游，经过确定性去重和冲突处理
- 🎮 **Steam 专项优化**：针对前台社区与后台下载三级分流，强制代理与优先直连动态结合
- 🗺️ **地区分流**：按节点名称匹配🇩🇪德 / 🇭🇰港 / 🇨🇳台 / 🇸🇬新 / 🇯🇵日 / 🇺🇸美 / 🇰🇷韩；地区测速组不混入全局节点，无匹配时为 REJECT，不会自动改用其他地区。
- ✏️ **按业务维护直连规则**：公共服务放入对应业务分类；`CustomDirect.list` 仅保留无合适分类的公共例外，个人服务地址留在私有覆写

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
https://raw.githubusercontent.com/E-R-Butch/ACL4SSR-Redux/master/Config/ACL4SSR_Online_Full.ini
```

然后填入你的节点订阅地址，即可生成完整 Clash 配置。

主 INI 会保留七个地区组；缺少对应节点的组只有 REJECT。需要跨地区降级时，请在服务组中明确选择“🚀 节点选择”或其他地区。地区识别依据节点名称，不代表对出口所在地或媒体解锁状态的检测。

`DynamicRegionContext.j2` 和 `DynamicProxyGroups.yml.j2` 是提供给已有 Jinja 渲染链路的可选组件，主 INI 不调用它们。可选组件只生成存在节点的地区组；对应地区缺失时，媒体组默认回到“🚀 节点选择”。两条链路的 Claude 组均使用专用代理组。

---

## 🛠️ 维护与自动同步

PR 和推送会运行只读 CI，检查仓库边界、单元测试、重复规则、配置引用、YAML、规则类型和 CIDR。分流回归测试还检查 Claude 的嵌套直连路径、空节点行为、地区组成员、奈飞节点筛选和 OneDrive 的首个匹配策略。每日同步会完整拉取全部上游数据，任一强制来源失败即停止；全部转换成功后才替换正式文件，再执行护栏、构建和校验。无规则语义变化时不会创建自动提交。

如需更深入地排查规则质量，可手动运行 `python3 scripts/audit_rules.py`。该工具默认只输出报告，不参与每日 CI；需要让发现项返回失败状态时，可加 `--strict`。

公共网页服务按用途维护：`RecruitmentDirect.list` 收录已核实的招聘页面和申请人门户资源，`ConsentDirect.list` 收录 Cookie 同意界面及配置接口，帮助中心归入 `CloudServiceDirect.list`。新增规则使用精确域名，招聘与同意资源位于广告、隐私列表之后；能直连不代表该服务完全不收集数据。

下载分流比较同一实际文件在直连与代理下的传输耗时、吞吐和重复请求表现，并核对内容一致性；首页返回 200 只证明可达。文档、网站、下载跳转入口和最终文件主机分别判断。`DeveloperDirect.list` 收录 Astral 安装与发布下载，`DeveloperProxy.list` 收录 IOTA 下载入口及其使用的 Spaces 区域主机，采用精确域名匹配。技嘉静态资源归入 `HardwareDirect.list`，官网在自动请求均返回 403、尚无有效性能样本的情况下由 `HardwareProxy.list` 保留代理路径。`deprecated.png` 作为已观察到的无效主机精确拒绝，不扩大到其他文件名。

服务的地区准入要求优先于直连可达性和速度。`opencode.ai` 同时承载官网与 Zen/Go API；[官方文档](https://opencode.ai/docs/go/#endpoints)列出的部分模型限制使用地区，因此该精确域名归入 `DeveloperProxy.list`，使用“🚀 节点选择”中的合适海外出口。

`easylist.to` 是 [EasyList 项目官网](https://easylist.to/pages/about.html)及广告、追踪拦截列表下载源，精确归入 `DeveloperProxy.list` 的浏览器扩展与过滤列表更新分类。实际完整 EasyPrivacy 文件在直连及代理下内容一致，重复传输样本中美国代理更快；其他出口仍可能出现连接超时。该规则不扩展到其他子域名，也不改变本项目自动同步使用的发布地址。

`api.oaistatsig.com` 在主 INI 中使用精确域名规则直接 `REJECT`，先于业务分流规则，不经过可切换策略组。[HaGeZi Ultimate](https://github.com/hagezi/dns-blocklists/blob/main/wildcard/ultimate.txt) 已收录该域名；[Statsig 文档](https://docs.statsig.com/infrastructure/statsig_domains)说明该服务包含配置与事件记录。

`analytics.brew.sh` 是 [Homebrew 使用统计上报端点](https://docs.brew.sh/Analytics)，在主 INI 中精确 `REJECT`，同时覆盖日志中出现的 `analytics.brew\.sh` 写法。该规则只拦截统计上报，保留 `formulae.brew.sh` 的开发代理分流；Homebrew 会静默处理上报失败。

Computer History Museum 按实际页面与资源区分：`computerhistory.org` 主站归入 `ScholarDirect.list`，`www.computerhistory.org` 藏品目录（含日志中的转义写法）归入 `ScholarProxy.list`。馆藏图片使用的 `s3.us-west-1.wasabisys.com` 是 Wasabi Oregon 共享对象存储入口，精确归入 `CloudServiceProxy.list`，不扩展到整个存储服务；有效图片测速需带页面的 Referer，并比较相同文件内容，缺失 Referer 导致的 403 不能用于判断下载速度。样本中美国代理快于直连，日本代理明显较慢且出现失败，代理地区选择仍影响实际表现。

`fast.fonts.net` 在主 INI 中直接 `REJECT`：[Monotype 官方说明](https://www.monotype.com/legal/privacy-policy/web-font-tracking-privacy-policy)其字体授权访问量统计；博物馆样式表引用该主机的 `/lt/1.css` 统计请求，字体文件则托管在本站。该主机也可能为其他网站提供字体，域名级拒绝可能使那些页面回退到默认字体。`images.fallout.wiki` 归入游戏代理；访问挑战导致无有效图片测速样本，保留代理路径。

`commandcode.ai` 官网与 `api.commandcode.ai` [模型 API](https://commandcode.ai/docs/provider)分别精确归入开发代理。公开模型列表的重复请求代理更快，但这不能证明账号的模型准入或流式推理速度。`r.jina.ai` 是 [Jina Reader 网页转文本接口](https://github.com/jina-ai/reader)，直连多次被重置、代理返回有效正文，归入开发代理；不扩展到 Jina 搜索或嵌入 API。`api.pullpush.io` 是 [PullPush Reddit 归档查询接口](https://www.pullpush.io/)，也精确归入开发代理；其 429 响应涉及自动抓取限制，不能当作地区封锁或下载测速结果，调整分流也不保证解除服务端限制。

`linustechtips.com` [硬件论坛](https://linustechtips.com/)与 `forums.developer.nvidia.com` [NVIDIA 开发者论坛](https://forums.developer.nvidia.com/)精确归入 `HardwareProxy.list`。LTT 自动请求在直连和代理下均遇到访问挑战，保留已有代理路径，不宣称代理能解除挑战。NVIDIA 的实际帖子列表重复传输测试中代理更快，不能仅凭首页可直连将论坛划入直连；NVIDIA 其他主机及已有遥测拦截规则不随论坛规则扩大放行。

`www.keebtalk.com` 是 [KeebTalk 机械键盘论坛](https://www.keebtalk.com/about)，实际帖子页传输样本代理更快，精确归入硬件代理，同时覆盖日志中的 `www\.keebtalk.com` 写法。`cdn.shopify.com` 是 [Shopify 共享资源 CDN](https://shopify.dev/docs/storefronts/themes/best-practices/performance/use-shopify-cdn)，承载图片、样式、字体、脚本和商家文件；键盘图片同一字节范围与 VIA 配置文件的重复下载样本中美国代理更快，精确归入 `EcommerceProxy.list`，不扩展到整个 Shopify 域名。该分类位于广告和隐私拦截之后，保留独立统计端点的原有拦截；共享 CDN 也会分发统计脚本，[EasyPrivacy 的路径过滤规则](https://github.com/easylist/easylist/blob/master/easyprivacy/easyprivacy_general.txt)包含 Shopify 相关脚本。HTTPS 域名分流不能单独拦截同一主机下的统计脚本路径，不能将 CDN 放行等同于完整过滤遥测。

---

## 🗂️ 策略组一览

| 策略组 | 类型 | 默认 | 说明 |
| :--- | :--- | :--- | :--- |
| 🚀 节点选择 | select | ♻️ 自动选择 | 主出口，统筹全局 |
| 🚀 手动切换 | select | — | 手动节点全量列表 |
| ♻️ 自动选择 | url-test | — | 全节点自动测速 |
| 🤖 OpenAI | select | 自动/手动 | ChatGPT 相关服务，支持全节点自动优选 |
| 🎭 Claude | select | 🎭 Claude 自动 | Anthropic/Claude 服务，规则模式下禁止直接或间接选择 DIRECT |
| 🎭 Claude 自动 / 手动 | url-test / select | 全部节点 | Claude 专用代理候选，无节点时 REJECT |
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
