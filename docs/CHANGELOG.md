# 更新日志

本项目的所有重要变更都会记录在本文件中。

格式遵循 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) 规范，版本号采用 [语义化版本](https://semver.org/spec/v2.0.0.html) 约定。

## [1.0.1] - 2026-09-03

### 新增功能

- **支持 Excel 97-2003（.xls）格式**：四大 Excel 工具（多工作簿合并 / 单簿内表合并 / 拆为 CSV / 超宽列拆分）现在可直接读取并处理 `.xls` 文件，与 `.xlsx` 无差别使用。
  - 技术说明：此前 Excel 读取仅依赖 `openpyxl`（只支持 `.xlsx/.xlsm`），`.xls` 为 BIFF/OLE2 旧格式，会在读取时抛出 `BadZipFile` 异常并被泛型异常吞掉而静默失败。本次新增 `xlrd` 依赖与 `load_workbook_any()` 统一加载器，`.xls` 经 `xlrd` 读入后转换为内存中的 `openpyxl.Workbook`（日期→datetime、布尔→bool、错误单元格→空），四个后端统一处理。
  - 新增 `tests/fixtures/sample.xls` 测试夹具与 `TestExcelXls` 回归测试（5 项）覆盖上述四个后端。

### 优化

- **异常提示与界面文案**：`.xls` 读取失败给出明确中文提示（“无法读取 .xls 文件（可能不是有效的 Excel 97-2003 文件或已损坏）”）；`.xlsx` 损坏或实为 .xls 误命名时提示“可能文件已损坏，或实为旧版 .xls 却以 .xlsx 命名”；入口层与文件选择标签补充 `.xls` 支持说明。

### 技术细节

- `requirements.txt` 新增 `xlrd>=2.0`；`build.py` 增加 `--collect-all xlrd` 确保打包包含。
- 单元测试总数由 85 项增至 90 项（新增 5 项 .xls 回归测试），代码门禁保持通过（EXIT=0）。

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
