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

证书相关服务分别维护：`CertificateDirect.list` 收录已验证的 Certum、Sectigo 证书下载主机以及 Let's Encrypt CRL 主机，避免证书检查依赖代理连接；原先的 `e8.c.lencr.org` 同策略迁入此分类。`CertificateProxy.list` 收录传输样本代理更快的 Certum 官网文档，包含日志中的转义写法。[Certum 证书目录](https://www.certum.eu/en/cert_expertise_root_certificates/)、[Sectigo 证书说明](https://www.sectigo.com/knowledge-base/detail/Sectigo-Root-Certificates)和 [Let's Encrypt 的 lencr.org 说明](https://letsencrypt.org/docs/lencr.org/)可用于核实业务。只匹配具体主机，不按 `trustd`、`svchost.exe` 或证书机构整个域名后缀放行。

`ocsp.usertrust.com`、`ocsp.comodoca.com` 是 [Sectigo 官方列出的 OCSP 证书状态查询服务](https://www.sectigo.com/knowledge-base/detail/OCSP-and-CRL-access-information)，以精确主机加入 `CertificateDirect.list`。使用公开的 R46 交叉签名证书生成有效 OCSP 请求，两个主机的直连与代理响应均通过签名验证并返回 `good`；这次直连样本约 0.17 / 0.43 秒，代理约 0.70 / 0.59 秒。此结果验证的是公开证书状态查询，不代表重放了日志中的原始证书请求；不扩大证书机构域名或 CDN 地址范围。

`gateway.fe2.apple-dns.net` 是实测 DNS 中 `gateway.icloud.com` 的 CNAME；[Apple 官方网络清单](https://support.apple.com/en-us/101555)将原主机列为 CloudKit 内容服务，包括 XProtect 更新和语音控制资源。该精确别名加入 `AppleDirect.list`，跟随既有 iCloud 的 `🍎 苹果服务` 策略（默认直连）。域名带有 `dns` 不意味着该连接在提供 DNS 解析，也没有依据将共享内容网关当作专用遥测。没有实际内容下载样本，不能据此声称直连更快。

`apple-relay.fastly-edge.com` 则被同一份 Apple 官方清单明确列为 Apple Intelligence 的 Private Cloud Compute 中继，使用 TCP/UDP 443。以精确域名加入 `AppleProxy.list`，保留已观察到的代理方向；不扩大到整个 Fastly 后缀。未经认证的探测只返回 HTTP 401，尚未验证实际 PCC 请求、地区资格或 UDP 会话，不能声称功能已恢复或代理更快。

Paradox 按功能分流：现有 `api.paradox-interactive.com` 保持游戏直连；`revocation-prod.paradox-interactive.com` 返回 `revocation-certificates-prod` 存储桶标识，作为更新器证书撤销相关资源归入游戏直连。官方[游戏 API](https://api.paradox-interactive.com/mods/games)引用的图片主机 `metadata-assets.paradox-interactive.com`、模组网站、官网及[启动器安装包入口](https://www.paradoxinteractive.com/our-games/launcher)精确归入游戏代理，完整资源或相同字节范围的有效样本支持该方向。`distribution-fastly-prod.paradox-interactive.com` 根据启动器更新日志归入游戏代理；根路径 403 不作为真实补丁下载测速依据。官方模组站脚本明确使用 `prod-telemetry.paradox-interactive.com` 上报遥测，该精确主机在主 INI 中直接 `REJECT`。

`rog-live-service.asus.com` 是 ASUS ROG / Armoury Crate 更新接口主机，[ASUS 论坛的更新日志](https://rog-forum.asus.com/t5/armoury-crate/rogliveservice-update-fails/td-p/1044038)明确记录 `/service/update2`。精确归入硬件代理以保留原代理方向；无设备参数的 GET 在直连及代理下都返回 405，不能用该错误响应推断实际设备更新或安装包速度。公开资源测速结果与 Windows 上的实际更新完成是不同验证层级。

`wiki.eufymake.com` 是 [eufyMake 打印机支持知识库](https://wiki.eufymake.com/en/home)，正文与样式资源的直连样本较慢或失败，精确归入硬件代理。`openrgb.org` 是 [OpenRGB 官网及设备支持资料入口](https://openrgb.org/)，直连样本全部成功，综合稳定性与页面/资源时延归入硬件直连；部分资源的美国代理更快，不宣称直连在所有资源上最快。[正式发行包](https://openrgb.org/releases.html)链接到其他主机，官网测速不能代表安装包下载速度。

`monitorcontrol.app` 是 [MonitorControl 官方网站](https://github.com/MonitorControl/MonitorControl)，[应用配置](https://github.com/MonitorControl/MonitorControl/blob/main/MonitorControl/Info.plist)将 Sparkle 更新清单指向该主机的 `/appcast2.xml`。它会被广告原料及合并列表中的 `DOMAIN-KEYWORD,monitor` 误拦，因此在广告规则之前的 `HardwareProxy.list` 添加精确主机例外。完整更新清单的重复传输代理更快；实际安装包链接到 GitHub，沿用 GitHub 自身分流。本例外不修改上游广告关键词，也不扩大为域名后缀放行。

`sstats.adobe.com` 由 [Adobe 官方文档](https://experienceleague.adobe.com/en/docs/target/using/integrate/a4t/analytics-tracking-server)明确列为 HTTPS Analytics 跟踪服务器，在主 INI 中精确、直接 `REJECT`，先于业务规则且不经过可切换策略组。Adobe 登录与其他业务主机保持原分类。

Chub 按用途维护为 `ChubProxy.list` 与 `ChubDirect.list`，均位于广告和隐私规则之后。[官方指南](https://docs.chub.ai/docs/the-basics/getting-started)说明其角色聊天与多模型 API 功能；前端公开脚本将 `gateway.chub.ai` 设为业务网关、`ro.chub.ai` 设为读取接口，后者的 `GET /api/events` 返回站内活动和评选数据。`chub.ai` 的实际页面/脚本以及网关公开状态 JSON 样本总体支持代理；`ro.chub.ai` 在补齐浏览器 Origin、Referer 后的有效 JSON 重复请求直连更快，归入直连。`avatars.charhub.io` 承载头像、角色卡和图片，默认头像及 PNG 样本直连稳定、耗时略低，归入直连；favicon 样本代理更快，不宣称所有对象都适合相同线路。仅使用精确主机，不扩展到整个域名后缀，也不代替登录或模型生成验证。默认 curl User-Agent 的地域提示和缺失浏览器请求头时的 403 不计入有效性能样本。

`static.cloudflareinsights.com` 与 `odo.chub.ai` 在主 INI 中精确、直接 `REJECT`。前者承载 [Cloudflare Web Analytics 统计脚本](https://developers.cloudflare.com/web-analytics/data-metrics/data-origin-and-collection/)，后者的[实际脚本](https://odo.chub.ai/js/script.local.js)使用 Plausible，向 `/api/event` 上报页面 URL、来源和 `pageview` 事件。它与 `ro.chub.ai` 的活动读取接口用途不同。拦截范围不覆盖 Cloudflare 验证/CDN 主机；同站 `/cdn-cgi/rum` 等路径不能用 HTTPS 域名规则单独过滤。

`artalk.bambulab.com` 同时承载 Bambu Lab Wiki 的 Artalk 评论组件与浏览量统计。[Wiki 页面](https://wiki.bambulab.com/en/home)将评论服务指向该主机；脚本、样式和评论接口共用主机，因此精确归入 `HardwareProxy.list`，保留评论功能及原代理方向。[实际前端脚本](https://artalk.bambulab.com/dist/Artalk.js?v=5)默认开启浏览量上报；整主机拒绝会连评论一起停用，不能将这种共享业务主机按纯遥测端点处理。单独关闭上报需由站点设置 [`pvAdd: false`](https://artalk.js.org/typedoc/interfaces/config#pvadd)，或在支持 HTTPS URL 过滤的浏览器中拦截 `/api/v2/pages/pv`。**本项目的域名分流没有单独拦截该统计路径**，也不部署 TLS 解密；规则不扩展到整个 `bambulab.com`。其他独立统计主机继续按原策略拒绝。

`portal.nousresearch.com` 是 Nous Portal 的账户和认证门户；[Hermes Agent 官方代码](https://github.com/NousResearch/hermes-agent/blob/main/hermes_cli/auth_nous.py)将令牌刷新请求发送到该主机的 `/api/oauth/token`。完整门户页面和样式资源重复传输样本支持代理，精确归入 `DeveloperProxy.list`。公开页面测速不代表已完成用户认证、令牌刷新或另一主机上的模型推理。

`hermes-agent.nousresearch.com` 承载 [Hermes Agent 官网、文档及安装入口](https://hermes-agent.nousresearch.com/docs/)，与账户门户分别匹配。官网、样式表、文档页和文档索引的完整重复下载总体支持代理，精确归入 `DeveloperProxy.list`；该主机的结论不扩展到其他 Nous 子域。

`openrouter.ai` 是 [OpenRouter 模型聚合服务](https://openrouter.ai/docs/quickstart)，官网、模型目录和 `/api/v1/chat/completions` 使用同一主机。有效模型目录 JSON 的重复传输代理更快，精确归入 `DeveloperProxy.list`，不混入 OpenAI 专属规则，也不扩展到地区子域。[模型供应商的地区与实体限制](https://openrouter.ai/terms)仍需遵守；公开目录可访问及代理分流都不等同于账号具有所有模型的使用权限，本次未使用令牌或调用付费推理。

`search.parallel.ai` 是 [Parallel 官方 Search MCP](https://docs.parallel.ai/integrations/mcp/search-mcp) 的托管主机，`/mcp` 提供 `web_search` 与 `web_fetch`，支持匿名免费使用。使用真实 MCP 初始化、工具列表和读取同一篇公开文档的 `web_fetch` 调用验证，直连稳定，调用时延与美国代理接近、低于日本代理，因此精确归入 `DeveloperDirect.list`；根路径的 404 不参与性能判断，也不将该结论扩大到 `api.parallel.ai` 或所有搜索任务。

下载分流比较同一实际文件在直连与代理下的传输耗时、吞吐和重复请求表现，并核对内容一致性；首页返回 200 只证明可达。文档、网站、下载跳转入口和最终文件主机分别判断。`DeveloperDirect.list` 收录 Astral 安装与发布下载，`DeveloperProxy.list` 收录 IOTA 下载入口及其使用的 Spaces 区域主机，采用精确域名匹配。技嘉静态资源归入 `HardwareDirect.list`，官网在自动请求均返回 403、尚无有效性能样本的情况下由 `HardwareProxy.list` 保留代理路径。`deprecated.png` 作为已观察到的无效主机精确拒绝，不扩大到其他文件名。

Steam 的 `api.steampowered.com` 使用精确游戏代理规则，修正受影响客户端直连超时的问题；[Valve 的 GetServerInfo 接口](https://partner.steamgames.com/doc/webapi/isteamwebapiutil)用于验证无密钥的正常 API 响应，不等同于完成账号登录。社区图片 `images.steamusercontent.com` 的同图重复传输样本直连更快，因此保持游戏直连，其他 Steam 内容下载主机也保留原策略。

Windows 的联网探测与局域网更新互传分别处理：[Microsoft NCSI](https://learn.microsoft.com/en-us/windows-server/networking/ncsi/ncsi-overview)使用 IPv4/IPv6 探测判断联网状态，IPv6 专用探测在禁用 IPv6 的解析/连接配置下可能失败；不能用代理成功或伪造 IPv4 地址代替本机 IPv6 连通性。局域网 TCP 7680 是 [Delivery Optimization 更新互传](https://learn.microsoft.com/en-us/windows/deployment/do/delivery-optimization-configure)，直连超时需要检查对端服务、路由和防火墙。公共规则保持这些流量直连，不因单台设备的日志统一拒绝互传、关闭联网探测或修改全局 IPv6 设置。

服务的地区准入要求优先于直连可达性和速度。`opencode.ai` 同时承载官网与 Zen/Go API；[官方文档](https://opencode.ai/docs/go/#endpoints)列出的部分模型限制使用地区，因此该精确域名归入 `DeveloperProxy.list`，使用“🚀 节点选择”中的合适海外出口。

`easylist.to` 是 [EasyList 项目官网](https://easylist.to/pages/about.html)及广告、追踪拦截列表下载源，精确归入 `DeveloperProxy.list` 的浏览器扩展与过滤列表更新分类。实际完整 EasyPrivacy 文件在直连及代理下内容一致，重复传输样本中美国代理更快；其他出口仍可能出现连接超时。该规则不扩展到其他子域名，也不改变本项目自动同步使用的发布地址。

`download.blender.org` 是 [Blender 官方发行文件下载主机](https://download.blender.org/release/)，精确归入 `DeveloperProxy.list` 的工具下载规则。实际 Windows 安装包相同字节范围的重复传输样本中代理更快，已核对有效 HTTP 206 响应、范围长度及内容一致性；分段测试不等于完整安装包的持续下载速度。

`softwareupdate.pilotmoon.com` 是 Scroll Reverser 的 Sparkle 更新清单主机，[官方源码](https://github.com/pilotmoon/Scroll-Reverser/blob/master/AppDelegate.m)明确指定其 appcast 地址；清单中的完整发行 ZIP 托管在 `pilotmoon.com`。两者精确归入 `DeveloperProxy.list` 的工具更新分类。三轮相同清单及完整安装包下载内容一致，代理总体更快；不扩大到整个 Pilotmoon 域名后缀。更新检查不等同于遥测，[项目配置](https://github.com/pilotmoon/Scroll-Reverser/blob/master/ScrollReverser-Info.plist)关闭了 Sparkle 系统信息采集。

Apple 的 NetworkServiceProxy 配置为 `tether.edge.apple` / `a.tthr.apple.com` 列出了 `2620:149:af1::10`、`2620:149:af6::10`，标签包括 `EdgeHog` 和 `EdgeHog_Weather_China_A`，协议标记为 [RFC 9298 UDP 中继](https://www.rfc-editor.org/rfc/rfc9298.html)。这是应用配置直接提供地址的证据，裸 IP 本身不能证明 DNS 被其他程序抢先解析；[Apple 也说明网络中继用于多种隐私功能](https://developer.apple.com/videos/play/wwdc2023/10002/)，不能只按进程名认定为遥测或某一条具体天气请求。这两个公共 IPv6 地址以 `/128,no-resolve` 精确归入 `AppleProxy.list`，保留原代理方向。普通 HTTPS 和未认证 QUIC 探测未能验证实际中继业务或证明直连更快；分类完成不等于中继业务已恢复。其他 Apple 地址、域名和隐私拦截策略不随之扩大。

`cua.ai` 是 Cua 计算机自动化工具与云桌面平台的[官网和文档](https://cua.ai/docs)，页面与资源传输样本支持开发代理；[官方认证文档](https://cua.ai/docs/reference/cua-cli/authentication)将登录与 Fleet API 放在独立主机，因此此处只匹配 `cua.ai`，不推断账号、云桌面或模型服务的地区可用性。`models.dev` 是[模型与供应商资料库](https://models.dev/)，其公开 `api.json` 提供规格、能力和价格等元数据，按完整 JSON 传输样本精确归入开发代理。

`eu.i.posthog.com` 在主 INI 中精确、直接 `REJECT`，先于业务分流且不经过可切换策略组。Cua 的[公开 PostHog 配置](https://cua.ai/assets/PostHogProvider-vgtdN9yw.js)将统计主机指向该地址；[PostHog SDK 文档](https://posthog.com/docs/libraries/python)说明其事件采集、用户识别与配置能力。官网资料访问与统计上报分别匹配，拒绝范围不扩大到整个 PostHog 域名。

`us.i.posthog.com` 是 [PostHog Node SDK](https://posthog.com/docs/libraries/node) 使用的美国区采集主机，可接收事件、页面访问和用户属性等统计数据，已观察到 Freebuff 向其连接。与欧洲区相同，在主 INI 中精确、直接 `REJECT`，保留 Freebuff/Codebuff 业务主机的代理规则；不将所有 PostHog 子域一起拒绝。

`2a01:b740:a30:2000::171` 的反向 DNS 为 `defra1-edge-fx-023.b.aaplimg.com`，该主机的 AAAA 又指回同一地址；[RIPE 注册信息](https://rdap.db.ripe.net/ip/2a01:b740:a30:2000::171)及 [Apple 官方地址表](https://ip-geolocation.apple.com/)确认其归属 Apple、所在地为法兰克福。该地址被 WeatherWidget 的 UDP 443 连接使用，但日志缺少域名/路径，未还原到具体预报或资源接口；CDN 也可能被多个业务共用。仅以 `/128,no-resolve` 精确加入 `AppleProxy.list`，保留原代理方向。现有证据不能证明 DNS 被抢答、该连接属于遥测或直连更快；无认证天气请求的完成验证，也不扩大 Apple 网段或按进程放行。

`aistacknav.com` 是 [AI 工具导航、技术教程与数字资料站](https://aistacknav.com/)，公开首页及前端资源的重复传输样本支持开发代理，采用主机精确匹配。页面嵌入的 `analytics.aistacknav.com/script.js` 是独立 Umami 统计脚本，代码将数据发送到该主机的 `/api/send`；该统计主机在主 INI 中精确 `REJECT`。[Umami 文档](https://docs.umami.is/docs/collect-data)说明了脚本的采集用途。现有 Google 广告、统计拦截保持优先；登录、购买及付费资料下载未作为测速样本。

`api.oaistatsig.com` 在主 INI 中使用精确域名规则直接 `REJECT`，先于业务分流规则，不经过可切换策略组。[HaGeZi Ultimate](https://github.com/hagezi/dns-blocklists/blob/main/wildcard/ultimate.txt) 已收录该域名；[Statsig 文档](https://docs.statsig.com/infrastructure/statsig_domains)说明该服务包含配置与事件记录。

`analytics.brew.sh` 是 [Homebrew 使用统计上报端点](https://docs.brew.sh/Analytics)，在主 INI 中精确 `REJECT`，同时覆盖日志中出现的 `analytics.brew\.sh` 写法。该规则只拦截统计上报，保留 `formulae.brew.sh` 的开发代理分流；Homebrew 会静默处理上报失败。

Computer History Museum 按实际页面与资源区分：`computerhistory.org` 主站归入 `ScholarDirect.list`，`www.computerhistory.org` 藏品目录（含日志中的转义写法）归入 `ScholarProxy.list`。馆藏图片使用的 `s3.us-west-1.wasabisys.com` 是 Wasabi Oregon 共享对象存储入口，精确归入 `CloudServiceProxy.list`，不扩展到整个存储服务；有效图片测速需带页面的 Referer，并比较相同文件内容，缺失 Referer 导致的 403 不能用于判断下载速度。样本中美国代理快于直连，日本代理明显较慢且出现失败，代理地区选择仍影响实际表现。

`fast.fonts.net` 在主 INI 中直接 `REJECT`：[Monotype 官方说明](https://www.monotype.com/legal/privacy-policy/web-font-tracking-privacy-policy)其字体授权访问量统计；博物馆样式表引用该主机的 `/lt/1.css` 统计请求，字体文件则托管在本站。该主机也可能为其他网站提供字体，域名级拒绝可能使那些页面回退到默认字体。`images.fallout.wiki` 归入游戏代理；访问挑战导致无有效图片测速样本，保留代理路径。

`commandcode.ai` 官网与 `api.commandcode.ai` [模型 API](https://commandcode.ai/docs/provider)分别精确归入开发代理。公开模型列表的重复请求代理更快，但这不能证明账号的模型准入或流式推理速度。`r.jina.ai` 是 [Jina Reader 网页转文本接口](https://github.com/jina-ai/reader)，直连多次被重置、代理返回有效正文，归入开发代理；不扩展到 Jina 搜索或嵌入 API。`api.pullpush.io` 是 [PullPush Reddit 归档查询接口](https://www.pullpush.io/)，也精确归入开发代理；其 429 响应涉及自动抓取限制，不能当作地区封锁或下载测速结果，调整分流也不保证解除服务端限制。

`linustechtips.com` [硬件论坛](https://linustechtips.com/)与 `forums.developer.nvidia.com` [NVIDIA 开发者论坛](https://forums.developer.nvidia.com/)精确归入 `HardwareProxy.list`。LTT 自动请求在直连和代理下均遇到访问挑战，保留已有代理路径，不宣称代理能解除挑战。NVIDIA 的实际帖子列表重复传输测试中代理更快，不能仅凭首页可直连将论坛划入直连；NVIDIA 其他主机及已有遥测拦截规则不随论坛规则扩大放行。

`ota.nvidia.com` 承载 NVIDIA 软件更新与安装包分发：[NVIDIA 官方支持页](https://nvidia.custhelp.com/app/answers/detail/a_id/5799)直接提供该主机上的 NVIDIA App 安装包链接。为保留更新功能，该主机精确归入 `HardwareProxy.list`；同一官方安装包前 2 MiB 的重复传输中，美国代理全部成功且更快，直连和日本代理各有一次超时。有效 HTTP 206 样本已核对范围、长度与内容一致性，根路径 503 和未完成样本不计为有效下载速度。分段测速不等于整个安装包持续吞吐；规则不扩展到 NVIDIA 其他主机，独立统计端点保持原拦截策略。

`www.keebtalk.com` 是 [KeebTalk 机械键盘论坛](https://www.keebtalk.com/about)，实际帖子页传输样本代理更快，精确归入硬件代理，同时覆盖日志中的 `www\.keebtalk.com` 写法。`cdn.shopify.com` 是 [Shopify 共享资源 CDN](https://shopify.dev/docs/storefronts/themes/best-practices/performance/use-shopify-cdn)，承载图片、样式、字体、脚本和商家文件；键盘图片同一字节范围与 VIA 配置文件的重复下载样本中美国代理更快，精确归入 `EcommerceProxy.list`，不扩展到整个 Shopify 域名。该分类位于广告和隐私拦截之后，保留独立统计端点的原有拦截；共享 CDN 也会分发统计脚本，[EasyPrivacy 的路径过滤规则](https://github.com/easylist/easylist/blob/master/easyprivacy/easyprivacy_general.txt)包含 Shopify 相关脚本。HTTPS 域名分流不能单独拦截同一主机下的统计脚本路径，不能将 CDN 放行等同于完整过滤遥测。

---

`api.deps.dev` 是 [Google Open Source Insights API](https://docs.deps.dev/api/v3/)，提供包版本、许可和依赖图等数据；[Tirith 官方说明](https://github.com/sheeki03/tirith)将其用于包健康与安全检查。有效包信息和依赖图 JSON 的重复请求直连稳定，精确归入 `DeveloperDirect.list`。`cdn.simpleicons.org` 是 [Simple Icons 的 SVG 图标 CDN](https://github.com/LitoMore/simple-icons-cdn)，实际页面引用的图标三轮直连成功，也精确归入开发直连；这不意味着每个出口、每项请求的直连都最快。

`freebuff.com`、`codebuff.com` 及其实际跳转目标 `www.codebuff.com` 精确归入 `DeveloperProxy.list`，保留既有代理方向。Freebuff/Codebuff 是编码产品；[官方国家配置](https://github.com/CodebuffAI/codebuff/blob/main/common/src/constants/freebuff-countries.ts)和 [Freebuff 网站](https://freebuff.com/)说明国家与 VPN 会影响功能、模型及额度。公开页面直连较快不能证明认证模型业务适合改变出口，代理也不保证获得完整权限；本次未登录或调用模型。网站通过广告支持运营，独立广告/录制脚本与业务主机分别处理，域名分流不能阻止业务服务端对用户主动提交内容的处理。

`code.trygravity.ai`、`api.trygravity.ai`、`cdn.humanbehavior.co`、`ingest.humanbehavior.co` 在主 INI 中精确、直接 `REJECT`。Freebuff 页面加载 Gravity 的 [gr-pix.js](https://code.trygravity.ai/gr-pix.js)，其中包含广告归因、会话、点击和指纹相关配置，并把事件与会话发往 `api.trygravity.ai/track/*`，因此同时拒绝这个已核实的采集主机。Human Behavior 的 [CDN loader](https://cdn.humanbehavior.co/v1/loader.js)加载会话录制器，其[官方采集文档](https://docs.humanbehavior.co/docs/developers/ingestion-api)确认事件、回放和心跳等数据发送到 ingestion 主机。规则只覆盖这些已核实的独立主机，不拒绝 Freebuff/Codebuff 整站，也不扩展到整个供应商域名后缀。

---

`GoogleAPIProxy.list` 仅补充已观察到的四个 Google API 共享地址：`172.217.114.4`、`172.217.115.4`、`172.217.116.4`、`172.217.118.4`，均为 `/32,no-resolve`。[Google 官方地址表](https://www.gstatic.com/ipranges/goog.json)、Google 公共 DNS 中 `www.googleapis.com` / `maps.googleapis.com` 等主机的 A 记录及固定目标 IP 的 [Discovery API](https://developers.google.com/discovery/v1/reference/apis/list) 有效响应交叉确认了用途。四个地址直连 TCP/443 均超时，经已测试的代理均返回有效 JSON；共享 IP 无法还原浏览器具体调用的 API，也不能仅凭裸 IP 判断 DNS 被抢答。该列表位于既有域名、广告/隐私和国内直连例外之后、GEOIP/FINAL 之前，避免覆盖已有域名策略。保持兜底组原配置，不代理整个 Google 网段；没有域名时仍无法按具体 API 区分业务与统计。

`rdap.arin.net` 是 [ARIN 的 IP/ASN 注册资料查询接口](https://www.arin.net/resources/registry/whois/rdap/)，精确归入开发代理。实际注册信息 GET 的直连路径超时，代理返回有效 RDAP JSON；仅匹配这个查询主机，不扩大到整个 ARIN 域名或硬编码其后端地址。

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
