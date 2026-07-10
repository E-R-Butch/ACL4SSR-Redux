# ACL4SSR-Neo 使用说明

本文只说明 `ACL4SSR-Neo` 当前仓库的实际用法、目录结构和维护方式。

项目地址：
https://github.com/E-R-Butch/ACL4SSR-Neo

主配置：
https://raw.githubusercontent.com/E-R-Butch/ACL4SSR-Neo/master/Config/ACL4SSR_Online_Full.ini


## 1. 项目定位

`ACL4SSR-Neo` 现在是一个面向订阅转换与代理内核生态的规则仓库，当前主要适配 `Clash / Mihomo`。

本仓库只维护公开规则、配置和通用构建工具，不承载代理面板、服务器、节点、账号、密钥或其他实际部署内容。

仓库当前重点是：

- 提供可直接用于订阅转换的远程配置
- 维护核心代理、直连、服务分流规则
- 自动同步上游基础数据
- 自动合并广告规则并输出成品列表
- 在 PR、Push 和每日同步中执行自动校验

本文不再讨论早期已经放弃的 `ACL` 兼容路线，也不再把旧项目历史作为主要使用说明。


## 2. 当前目录结构

`Rules/Core`

- 核心直连和代理碎片
- 例如 `ProxyGFWlist.list`、`CustomDirect.list`、`LocalAreaNetwork.list`

`Rules/Ruleset`

- 当前分成 `Active` 和 `Inactive` 两层
- `Active` 放当前主配置和构建链路真正使用的规则
- `Inactive` 放保留但未接线的专题规则
- 原来的中国直连和广告原料已经并入 `Rules/Ruleset/Active/China` 与 `Rules/Ruleset/Active/AdBlock`

`Rules/Outputs`

- 构建产物
- 当前核心产物是 `MergedADBan.list`

`Config`

- 订阅转换用的主配置和基础模板
- 当前主入口是 `ACL4SSR_Online_Full.ini`
- `GeneralConfig.yml` 作为主配置的基础模板

`scripts`

- 自动同步、构建、校验和公开仓库边界检查脚本
- 通用 provider 转换由 `list_to_yaml.py` 提供，不绑定任何私有部署平台


## 3. 当前自动化状态

项目第一阶段自动化已经完成。

当前会自动同步：

- `GFWList`
- `China IPv4`
- `China IPv6`
- `EasyList`
- `EasyListChina`
- `EasyPrivacy`

当前会自动构建：

- `Rules/Outputs/MergedADBan.list`
- `Rules/Outputs/MergedPrivacy.list`

当前会自动校验：

- 主配置里的规则组引用是否一致
- 本仓库 Raw 引用对应的文件是否存在
- 基础模板 YAML 是否可解析
- CIDR 是否规范且地址族正确
- 是否混入部署代码或明显敏感信息
- `.list` 文件是否为空
- `.list` 文件是否满足基础格式要求


## 4. 当前推荐使用方式

最推荐的使用方式，是把主配置地址填入支持 `subconverter` 语法的订阅转换服务，然后输入你自己的原始节点订阅。

主配置地址：

```text
https://raw.githubusercontent.com/E-R-Butch/ACL4SSR-Neo/master/Config/ACL4SSR_Online_Full.ini
```

如果你的输入源本身已经是完整的 `Mihomo YAML`，那它不属于“原始节点订阅”，不应该再拿来做二次订阅转换。


## 5. 主要规则说明

### 5.1 代理

当前主维护的核心代理列表是：

- `Rules/Core/ProxyGFWlist.list`

它的组成方式是：

- `Rules/Core/ProxyManual.list` 中单独维护的人工补充规则
- 自动同步的官方 `gfwlist`

如果你要跟随仓库当前主工作流，优先使用 `ProxyGFWlist.list`，不再以 `ProxyLite` 作为主推荐入口。


### 5.2 直连

当前主配置默认会使用这些直连相关规则：

- `Rules/Core/LocalAreaNetwork.list`
- `Rules/Core/UnBan.list`
- `Rules/Core/Download.list`
- `Rules/Ruleset/Active/China/ChinaDomain.list`
- `Rules/Ruleset/Active/China/ChinaCompanyIp.list`
- `Rules/Ruleset/Active/China/ChinaIp.list`
- `Rules/Ruleset/Active/China/ChinaIpV6.list`
- `Rules/Ruleset/Active/China/GoogleCN.list`
- `GEOIP,CN`

其中：

- `ChinaIp.list` 和 `ChinaIpV6.list` 当前都已接入主配置


### 5.3 广告拦截

当前广告链路分成两层：

原料层：

- `BanAD.list`
- `BanProgramAD.list`
- `BanEasyList.list`
- `BanEasyListChina.list`
- `BanEasyPrivacy.list`

产物层：

- `MergedADBan.list`
- `MergedPrivacy.list`（隐私追踪规则独立产物）

日常使用建议：

- 优先直接使用 `MergedADBan.list`
- 不建议在主配置里再手动叠加多份同类广告规则，否则重复度和误拦概率都会明显上升


### 5.4 服务分流

当前仓库已经明确维护这些独立服务分流：

- `OpenAI`
- `Claude`
- `Gemini`
- `Grok`
- `Telegram`
- `YouTube`
- `Netflix`
- `DisneyPlus`
- `HBO`
- `Amazon`
- `Music`
- `OneDrive`
- `Apple`
- `Steam`

如果某个服务已经有独立规则，建议优先放在普通代理和普通直连规则之前。


## 6. 当前区域路由

当前主配置采用 6 组地区节点布局：

- `🇭🇰 香港节点`
- `🇨🇳 台湾节点`
- `🇸🇬 狮城节点`
- `🇯🇵 日本节点`
- `🇺🇸 美国节点`
- `🇰🇷 韩国节点`

这些地区组依赖节点名称正则匹配。

如果你的节点名称里没有地区关键词，即使规则写对了，也不会自动进入对应地区组。


## 7. 如何找规则文件

以 `ProxyGFWlist.list` 为例：

GitHub 页面：

```text
https://github.com/E-R-Butch/ACL4SSR-Neo/blob/master/Rules/Core/ProxyGFWlist.list
```

Raw 地址：

```text
https://raw.githubusercontent.com/E-R-Butch/ACL4SSR-Neo/master/Rules/Core/ProxyGFWlist.list
```

同理，仓库里其他 `.list` 文件都可以用相同方式找到对应的 Raw 地址。

如果你要看主配置，请直接访问：

```text
https://github.com/E-R-Butch/ACL4SSR-Neo/blob/master/Config/ACL4SSR_Online_Full.ini
```


## 8. 简化示例

下面这个例子只演示当前仓库常见的最小组合思路，不代表完整主配置。

```ini
[custom]
;不要随意改变关键字，否则会导致出错

surge_ruleset=🛑 广告拦截,https://raw.githubusercontent.com/E-R-Butch/ACL4SSR-Neo/master/Rules/Outputs/MergedADBan.list
surge_ruleset=📲 电报消息,https://raw.githubusercontent.com/E-R-Butch/ACL4SSR-Neo/master/Rules/Ruleset/Active/Telegram.list
surge_ruleset=🚀 节点选择,https://raw.githubusercontent.com/E-R-Butch/ACL4SSR-Neo/master/Rules/Core/ProxyGFWlist.list
surge_ruleset=🎯 全球直连,https://raw.githubusercontent.com/E-R-Butch/ACL4SSR-Neo/master/Rules/Core/LocalAreaNetwork.list
surge_ruleset=🎯 全球直连,https://raw.githubusercontent.com/E-R-Butch/ACL4SSR-Neo/master/Rules/Ruleset/Active/China/ChinaDomain.list
surge_ruleset=🎯 全球直连,https://raw.githubusercontent.com/E-R-Butch/ACL4SSR-Neo/master/Rules/Ruleset/Active/China/ChinaCompanyIp.list
surge_ruleset=🎯 全球直连,https://raw.githubusercontent.com/E-R-Butch/ACL4SSR-Neo/master/Rules/Ruleset/Active/China/ChinaIp.list
surge_ruleset=🎯 全球直连,[]GEOIP,CN
surge_ruleset=🐟 漏网之鱼,[]FINAL

custom_proxy_group=🚀 节点选择`select`[]♻️ 自动选择`[]DIRECT`.*
custom_proxy_group=♻️ 自动选择`url-test`.*`http://www.gstatic.com/generate_204`300
custom_proxy_group=📲 电报消息`select`[]🚀 节点选择`[]DIRECT
custom_proxy_group=🛑 广告拦截`select`[]REJECT`[]DIRECT
custom_proxy_group=🐟 漏网之鱼`select`[]DIRECT`[]🚀 节点选择`[]♻️ 自动选择

enable_rule_generator=true
overwrite_original_rules=true
```


## 9. 常见问题

### 9.1 规则越多越好吗

不建议这样理解。

规则应该以“有效、清晰、少重复”为目标，数量控制在合理范围更合适。

当前仓库的广告合并产物已经是大规则集，这属于正常设计结果，不代表你还应该继续额外叠加多份同类拦截列表。


### 9.2 为什么分流看起来没生效

常见原因有几种：

- 输入源本身已经是完整配置，不是原始节点订阅
- 节点名称没有命中地区组正则
- 某条规则引用了不存在的策略组
- 客户端拿到的是旧缓存

项目当前已经加入基础校验脚本，用来减少“规则引用错了但不容易发现”的问题。


### 9.3 为什么同类规则不建议叠加很多份

常见问题通常集中在这几类：

- 重复度太高
- 命中顺序混乱
- 误拦概率上升
- 转换结果更大、更慢

因此，代理、直连、广告三类规则更适合按职责清晰组合，避免无上限叠加。
