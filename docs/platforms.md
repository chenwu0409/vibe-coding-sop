# 目标平台验证能力边界

本文件定义 Agent 可以协助执行的验证，不把“能读源码”或“能运行单元测试”写成平台通过。

## 微信小程序

Agent 可以检查 `project.config.json`、`miniprogramRoot`、sitemap 和源码边界，扫描微信保留目录/文件名，运行 Node/领域/存储测试；在本机安装微信开发者工具且 CLI/IDE 服务可用时，可以调用 CLI 或操作开发者工具完成导入、编译和预览前检查。桌面自动化能力可用时，还可以操作开发者工具并记录截图/日志。

微信开发者工具未安装、IDE 服务端口未开启、账号/二维码/设备不可用时，必须记录 ENV 阻塞。Node 测试不能证明微信平台编译通过。

## Android

在 Android SDK、Gradle、ADB 和可启动的 Android Emulator 已安装且环境可用时，Agent 可以构建 APK/AAB，启动模拟器，安装 APK，使用 ADB、UIAutomator、Espresso、Appium 或 Maestro 执行路径，并读取 logcat、截图和测试报告。

没有 SDK、模拟器、设备或自动化入口时，只能完成静态、单元和构建层验证，不能标记 Android 冒烟通过。

## iOS

iOS Simulator 依赖 macOS、Xcode 和模拟器运行时。Windows Agent 不能本地启动 Apple 的 iOS Simulator。若连接了 macOS 远程执行环境或真实 iOS 设备，并且授权、证书和工具可用，Agent 可以通过 Xcode CLI、simctl、XCUITest、Appium 或 Maestro 协助验证；否则记录 ENV 未验证。

## 记录要求

启用 `project.json` 的 `platform.required=true` 后，先保存真实编译和冒烟输出或截图，再运行：

```sh
python .sop/runtime/sop.py attest-platform --environment local-dev --tool wechatide --tool-version 2.x --source-root miniprogram --compile-evidence .sop/evidence/compile.txt --smoke-evidence .sop/evidence/smoke.txt
```

该命令只接受项目内已有且非空的证据，将其哈希、工具版本、源码指纹和当前 Git commit/tree 写入 `.sop/platform-verification.json`。证据变化、源码变化或绑定提交不在当前 Git 历史中时，L4 失败。后续仅提交治理文件不会使源码证据过期，但源码变化会。直接手改 `compile/smoke=passed` 只兼容旧版 L3 迁移检查，不能通过 v2 的 L4。

凭据证明“指定证据与指定源码版本绑定且当前未变化”，不能独立证明截图语义真实；UI 行为仍需自动化断言或真实人工验收。平台不可用时保留 blocker，不生成伪 passed 凭据。
