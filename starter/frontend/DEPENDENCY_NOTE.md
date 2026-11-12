# 依赖与锁文件

依赖已安装，根目录 `package-lock.json` 统一锁定 npm workspace；新环境在根目录使用 `npm ci`。实际类型检查、构建及浏览器验收状态见 `docs/IMPLEMENTATION_REPORT.md`，安装完成不代表所有验收通过。

开发工具 typescript-eslint 依赖 minimatch 10，npm 审计发现 [GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249)。已仅对 `@typescript-eslint/typescript-estree` 的 minimatch 覆盖为修复版 11.0.1+；该包当前使用保留的 minimatch() 函数，不使用11移除的makeRe/AST接口。参见 [上游变更记录](https://github.com/isaacs/minimatch/blob/main/changelog.md)。应在上游升级后移除此覆盖；根目录全量检查用于验证当前兼容性。安装后npm审计为0漏洞（仅为当日审计结果）。
