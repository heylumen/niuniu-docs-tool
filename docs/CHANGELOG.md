# 更新日志

本项目的所有重要变更都会记录在本文件中。

格式遵循 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) 规范，版本号采用 [语义化版本](https://semver.org/spec/v2.0.0.html) 约定。

## [1.0.0] - 2026-08-30

首个公开版本。

### 功能

- **九大文档处理工具集于一身**：
  1. 编码转换（自动识别 BOM/UTF-8/GBK → UTF-8-BOM）
  2. 按行数拆分 CSV（每个分片均含表头）
  3. 按日期列拆分 CSV（支持日/月/年粒度）
  4. 合并 CSV 文件（快速二进制拼接 / 表头去重 / 追加来源文件名）
  5. 多工作簿合并为单个 Excel
  6. 单工作簿内多工作表合并
  7. CSV 关键词提取（包含 / 精确 / 正则）
  8. 将 Excel 工作簿拆分为 CSV（每表一个文件）
  9. 超宽工作表（>256 列）拆分为多表

- **界面**：原生 WebView2 渲染（pywebview + EdgeWebView2），像素级还原 Fluent Design 风格
- **主题**：浅色/深色模式并持久化保存
- **拖拽**：支持拖拽添加文件
- **缩放**：窗口支持 DPI 自适应缩放与边缘拖拽调整大小
- **大文件**：流式读写，支持多 GB 大文件（内存占用恒定）
- **输出**：完成后自动打开输出文件夹

### 技术细节

- Python 3.13+（文件对话框依赖 tkinter）
- 使用 pywebview + pythonnet 作为 WebView2 后端
- 使用 openpyxl 读写 Excel
- 使用 PyInstaller 打包为单文件 EXE
- 85 项单元测试全部通过
