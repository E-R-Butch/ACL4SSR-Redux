# 🗺️ ACL4SSR-Neo Roadmap

本文件详细记录了 `ACL4SSR-Neo` 项目的未来演进方向与技术规划。我们的目标是打造一个**高度自动化、工业级颗粒度、且完美适配现代内核**的 Clash 规则集。

---

## 📅 路线图总览

| 阶段 | 核心目标 | 预计成果 | 状态 |
| :--- | :--- | :--- | :--- |
| **Phase 1** | **自动化基础设施** | 实现规则自动同步、多源广告自动合并、CI 语法校验。 | ✅ 已完成 |
| **Phase 2** | **服务深度定制** | 补全 AI 全家桶、重构全平台游戏逻辑、精简区域路由。 | 📅 计划中 |
| **Phase 3** | **现代内核重构** | 深度适配 Mihomo (Clash Meta) 内核，引入 `RULE-SET`。 | ⏳ 长期 |

---

## 🛠️ 第一阶段：自动化与基础设施 (Automation & Infrastructure)

**目标**：降低维护负担，确保核心规则（GFWList, AdBlock）始终与上游同步。

- [x] **GitHub Actions 自动同步**：
  - [x] 核心 GFWList 首次手动对齐同步。
  - [x] 中国 IPv4/IPv6 地址库首次手动对齐同步。
  - [x] 每日自动从 [gfwlist/gfwlist](https://github.com/gfwlist/gfwlist) 抓取并转换。
  - [x] 每日自动抓取各大 AdBlock 素材源。
- [x] **智能构建系统 (`scripts/build_rules.py`)**：
  - 开发 Python 构建程序，负责 `Ruleset/Active/AdBlock -> Outputs` 的流水线加工。
  - 实现多源广告列表的去重、冲突检测与合并算法。
- [x] **代码规范与 CI 校验**：
  - [x] 对 PR、Push、手动任务和每日同步执行自动校验。
  - [x] 校验 `.list`、`.ini`、YAML、CIDR、本仓库引用和项目边界。
  - [x] 为构建、同步转换和 provider 转换增加单元测试。

---

## 🎯 第二阶段：服务深度细化 (Service Deep-Dive)

**目标**：从“能用”继续往前走，让每一个核心服务都有独立且合理的路由逻辑。

- [x] **AI 矩阵扩展**：
  - [x] OpenAI, Claude, Gemini 独立分流与防泄漏重构。
  - [ ] 针对 Midjourney, Suno, Llama API, Grok 等新兴服务增加独立分流。
  - [x] 优化 AI 测速组的检测间隔与地址，提高“自动选择”的准确率。
- [/] **全平台游戏重构**：
  - [x] Steam 成功实现三级分流逻辑（强制代理/直连下载/测试中）。
  - [ ] 重构 PlayStation (PSN), Xbox, Ubisoft, EA App 等。
- [/] **区域路由精简 (6+1 布局)**：
  - [x] 已精简至：🇭🇰 香港、🇨🇳 台湾、🇸🇬 狮城、🇯🇵 日本、🇺🇸 美国、🇰🇷 韩国。
  - [ ] 整合 `🇪🇺 欧洲大区`，合并德、英、法、荷等常用欧洲节点，放弃边缘冷门区域。

---

## ⚡ 第三阶段：高性能内核重构 (Modern Core Refinement)

**目标**：充分利用 Mihomo (Clash Meta) 的新特性，提升性能与体验。

- [ ] **`RULE-SET` 迁移**：
  - 针对现代内核用户，弃用传统的 `DOMAIN-SUFFIX` 顺序匹配，全面引入 `rule-providers`配合 `RULE-SET`。
  - 大幅降低规则条数增加带来的内存占用。
- [ ] **脚本化策略组 (Script Group)**：
  - 探索使用策略脚本实现更复杂的逻辑（如：某个地区不可用时自动切换到备选区域）。
- [/] **GeoIP/GeoSite 深度集成**：
  - [x] 核心配置已激活 IPv6 支持。
  - [ ] 针对国内流量，优先使用更准确的外部资源库进行预分流。

---

## 🤝 参与规划

如果您对路线图有任何建议或希望贡献规则，请随时提交 **Issue** 或 **Pull Request**。我们共同打造一个更纯净、更强大的分流方案。
