市场开盘以后，VIX、VOO 和新闻消息会一起变化。长期持有并不等于完全不看市场，但如果每天反复刷新行情，原本很简单的资产安排也容易变成注意力消耗。

我想解决的是一个更小的问题：事先写下的观察条件，今天有没有进入我设定的区域？如果进入了，留下一条可以核对的记录就够了。下一步是否行动，仍然由人决定。

iMarketMessage（iMM）就是从这个需求开始的。2026 年 8 月 15 日，我发布了第一个公开版本 `v0.1.0-alpha`。这是一个面向 macOS 14+、使用 Swift 和 SwiftUI 编写的开源 MVP。项目地址：[neverasecond/iMarketMessage](https://github.com/neverasecond/iMarketMessage)，本次发布页在 [v0.1.0-alpha Pre-release](https://github.com/neverasecond/iMarketMessage/releases/tag/v0.1.0-alpha)。

这次发布是 source-only alpha。它已经可以从源码构建、测试和运行，但还不是一个签名、公证后可以直接双击安装的成品。

![iMarketMessage 只读演示界面](/images/imarketmessage-v010-alpha-demo.png)

## 从 VIX 和 VOO 的观察条件开始

以 VIX 和 VOO 为例，可以把 VIX 的收盘值和 VOO 的日涨跌幅放进同一条 AND 规则。只有条件同时满足，规则才会产生一次事件。

这里没有预设一个“正确”的 VIX 阈值，也没有把 VOO 的短期下跌直接等同于加仓机会。使用者需要自己决定证券代码、数据来源、指标、比较符、阈值和冷却时间。工具只按照已经写下来的条件计算，不替人解释市场。

规则支持 `close` 和 `dailyPercentChange`，比较符包括 `>=`、`<=`、`>` 和 `<`。同一条规则可以组合多个条件，也可以选择“仅在进入区域时触发”。

进入区域触发解决的是提醒噪声。指标已经留在条件区间内时，反复检查不应该不断制造相同提醒；交易日冷却还能限制随后几个交易日的再次触发。对于长期投资者，提醒少一点通常比提醒快一点更重要。

## 本地规则，以及一份严格的交接

iMarketMessage 把规则和运行状态保存在本机。条件满足后，程序把事件写入一个结构严格的 JSON outbox，只允许 `source`、`id` 和 `text` 三个字段，并限制正文大小、文件名和权限。

outbox 不是已经完成的消息推送系统。它更像一份本地交接合同：规则引擎负责产生什么，下游程序允许读取什么，边界都写得比较清楚。未来即使接入 iMessage gateway，也不应该让一条队列消息任意选择收件人。

项目目前没有遥测，不读取 Messages 数据库或联系人，不保存电话号码和 chat ID，也不会自动安装 LaunchAgent。现有 `iMM-gateway --dry-run` 只会检查已经存在的 outbox 文件，不发送消息、不写 ACK、不移动或删除文件。

真实 iMessage sender、配对界面和后台安装还没有提供。这些不是文档里的小缺口，而是后续必须单独审查的权限边界。

## 数据源不藏在黑盒里

VIX 日线数据来自 Cboe 公布的 CSV，不需要 API key。其他证券可以使用 Alpha Vantage 日线接口，key 由使用者自己准备，并通过 macOS Keychain 保存，不写进规则 JSON 或仓库。

这种 BYO key 方式减少了项目代管凭证的责任，但不会消除数据服务本身的问题。免费额度、限流、日期差异、数据缺失和服务中断，都可能影响提醒结果。电脑休眠或没有联网时，本地程序同样不可能持续工作。

所以，本地优先不等于绝对可靠。它只是让数据来源、凭证位置、规则状态和失败方式更容易被使用者看见。

## 怎样从源码运行

项目要求 macOS 14 或更高版本，以及包含 Swift 6 和 Swift Testing 运行时的完整 Xcode。只安装 CommandLineTools，可能缺少测试所需的运行时。

可以从公开仓库取得源码：

```sh
git clone https://github.com/neverasecond/iMarketMessage.git
cd iMarketMessage
swift build --scratch-path /tmp/imarketmessage-build
swift test --scratch-path /tmp/imarketmessage-test
```

运行一次示例 CLI 检查：

```sh
swift run --scratch-path /tmp/imarketmessage-cli market-message-cli \
  --config Config/example-rules.json \
  --outbox /tmp/imarketmessage-outbox \
  --state /tmp/imarketmessage-state.json
```

这个示例会访问 Cboe VIX 日线数据。SwiftUI 界面可以这样启动：

```sh
swift run --scratch-path /tmp/imarketmessage-app iMM
```

完整命令、目录权限和已知限制应以仓库当前的 [README](https://github.com/neverasecond/iMarketMessage/blob/v0.1.0-alpha/README.md) 与 [LIMITATIONS.md](https://github.com/neverasecond/iMarketMessage/blob/v0.1.0-alpha/LIMITATIONS.md) 为准。

发布前最近一次 GitHub Actions `macOS CI` 已经在 macOS 15、完整 Xcode 和 Swift 6+ 环境中通过 build/test。发布页只有 GitHub 自动生成的源码归档，没有 `.app`、DMG 或其他二进制附件。

## 为什么先发布一个不完整的 alpha

如果目标只是尽快出现一条 iMessage，直接调用现有脚本会更短。但一个准备公开使用的工具，需要先回答另外一些问题：行情响应为空时怎样报错，API 限流是否能被看见，规则从区间外进入区间内时是否只触发一次，跨次运行怎样保留状态，outbox 文件能否被伪造，未来的 sender 怎样确保只发给本人。

这些工作不如“自动发出一条消息”醒目，却决定了工具是否值得继续使用。v0.1.0-alpha 先公开规则引擎、数据适配、本地存储、健康状态和 outbox 协议，让这些边界可以被检查和讨论。

接下来更需要的是具体反馈：规则编辑是否容易理解，数据和 Keychain 错误能否被普通使用者发现，paired-self 的消息路径应该怎样实现，以及安装和卸载怎样做到清楚、可逆。

iMarketMessage 不预测市场，不提供买卖信号、回测成绩或收益承诺。VIX、VOO 和其他证券都可能出现超出预期的波动，行情也可能延迟、缺失或修订。本文介绍的是一个开源工具的设计和当前能力，不构成投资建议。

