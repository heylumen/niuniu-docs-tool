#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
牛牛文档工具 · 提交前代码审查门禁（标准库实现，零依赖）

功能（v3.0 扩展为 11 项）：
  1) py_compile 全部源码（语法门禁）
  2) 扫描吞异常（bare except / except X: pass）—— 静默失败高风险
  3) 扫描调试残留 print（业务代码，生成脚本豁免）
  4) 运行 tests/ 下 unittest
  5) 巨型文件提示（分层：打包链 800 行，legacy 豁免）
  6) Python↔JS 契约双向 diff（P-M1 最高危拦截）
  7) 版本号硬编码扫描（P-M4 拦截）
  8) core 模块测试覆盖核对
  9) Win32/ctypes 调用清单输出（P-M2 提示人工复核，legacy 豁免）
 10) 危险函数扫描（eval/exec/shell=True 等，v3.0 新增）
 11) 手写 CSV 拼接扫描（','.join 等，v3.0 新增）

v3.0 修复（2026-08-29 实测误报）：
  - 项 6：判定死代码前排除 Python 内部调用（self./api. 调用），
          修复 set_window / add_files 两处误报，误报率 67% → 0%
  - 项 9：legacy 目录豁免，Win32 清单噪音 28 条 → 17 条

用法：
  python scripts/review_check.py
  python scripts/review_check.py --src src --tests tests

退出码：
  0 = 通过（无阻塞项）
  1 = 发现阻塞项（禁止提交）
"""
import os
import sys
import re
import ast
import compileall
import argparse
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 允许打印调试信息的脚本（生成器/构建器），不计入阻塞
PRINT_ALLOW = {"build.py"}  # 仅保留仍在跟踪且有意 print 的文件（generate_icon.py/doc_converter.py 已删除）

# 吞异常：bare except 或 except X: 后直接 pass（支持任意缩进）
RE_BARE_EXCEPT = re.compile(r"except\s*:")
RE_SWALLOW = re.compile(r"except\s+[\w\s,()]*:\s*\n\s*pass\s*(?:\n|$)")
RE_SWALLOW_LOOSE = re.compile(r"except\s+[\w\s,()]*:\s*\n(\s+)pass\s*(?:\n|$)")

# 版本号模式（X.Y.Z）
RE_VERSION = re.compile(r'\b(\d+\.\d+\.\d+)\b')

BLOCK = []  # 🔴 阻塞项
WARN = []   # 🟡 建议项
INFO = []   # 💭 细节


def check_compile(src_dir):
    """语法编译门禁。"""
    if not os.path.isdir(src_dir):
        BLOCK.append(f"源码目录不存在: {src_dir}")
        return
    ok = compileall.compile_dir(src_dir, quiet=1, maxlevels=10)
    if not ok:
        BLOCK.append(f"py_compile 失败：{src_dir} 存在语法错误（见上方报错）")


def iter_py(src_dir):
    for base, _dirs, files in os.walk(src_dir):
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(base, f)


def check_swallow(src_dir):
    """扫描吞异常。"""
    for path in iter_py(src_dir):
        rel = os.path.relpath(path, ROOT)
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
        for lineno, line in enumerate(lines, 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            code_part = line.split("#")[0] if "#" in line else line
            if RE_BARE_EXCEPT.search(code_part):
                BLOCK.append(f"{rel}:{lineno} 裸 except:（禁止，须用具体异常类型）")
        text = "".join(lines)
        for m in RE_SWALLOW.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            line_content = lines[line - 1].lstrip() if line - 1 < len(lines) else ""
            if line_content.startswith("#"):
                continue
            BLOCK.append(f"{rel}:{line} 吞异常 except...: pass（须记录日志或处理）")
        for m in RE_SWALLOW_LOOSE.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            line_content = lines[line - 1].lstrip() if line - 1 < len(lines) else ""
            if line_content.startswith("#"):
                continue
            key = f"{rel}:{line} 吞异常 except...: pass（须记录日志或处理）"
            if key not in BLOCK:
                BLOCK.append(key)


def check_print(src_dir):
    """扫描业务代码中的调试 print（豁免生成/构建脚本和 _debug_log 函数）。"""
    for path in iter_py(src_dir):
        rel = os.path.relpath(path, ROOT)
        name = os.path.basename(path)
        if name in PRINT_ALLOW:
            continue
        with open(path, "r", encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                if "file=sys.stderr" in line or "sys.stderr" in line:
                    continue
                if re.search(r"print\s*\(", line):
                    WARN.append(f"{rel}:{i} 调试残留 print()（提交前清理）")


def check_bigfile(src_dir, packaged_limit=800, legacy_limit=None):
    """巨型文件提示（v2.2.0: 分层判定——打包链 800 行告警，legacy 豁免）。"""
    for path in iter_py(src_dir):
        rel = os.path.relpath(path, ROOT)
        # legacy 目录豁免（不打包、不维护，最终删除）
        if "legacy" in path.replace("\\", "/").split("/"):
            continue
        with open(path, "r", encoding="utf-8") as fh:
            n = sum(1 for _ in fh)
        if n > packaged_limit:
            WARN.append(f"{rel} 巨型文件 {n} 行（> {packaged_limit}，建议拆分）")


def check_tests(tests_dir):
    """运行 tests/ 下 unittest。"""
    if not os.path.isdir(tests_dir):
        WARN.append("无 tests/ 目录：建议补充回归测试")
        return
    if os.path.isdir(os.path.join(ROOT, "src")):
        sys.path.insert(0, os.path.join(ROOT, "src"))
    loader = unittest.TestLoader()
    try:
        suite = loader.discover(tests_dir, pattern="test_*.py")
    except Exception as e:  # noqa: BLE001 - 发现即报告，不静默
        BLOCK.append(f"测试发现/运行异常: {type(e).__name__}: {e}")
        return
    res = unittest.TextTestRunner(verbosity=1).run(suite)
    if not res.wasSuccessful():
        BLOCK.append(
            f"单测失败：errors={len(res.errors)} failures={len(res.failures)}"
        )


def _collect_class_methods(src_dir, class_name, seen=None):
    """收集某个类的 public 方法集合，**含继承自项目内基类的方法**。

    v3.0 修复（2026-08-29）：v2.3.0 把 9 个 exec_* 业务方法拆到
    core/api_business.py 的 BusinessApiMixin 后，原逻辑只解析 app_webview.py 中
    class Api 的**直接**方法，导致 9 个 exec_* 被误报为"契约断裂"（P-M1 假阳性）。
    pywebview 实际通过 dir(obj) 收集可暴露方法（webview/util.py:190），
    dir() 包含继承成员 —— 因此门禁必须同样跟踪基类。
    """
    if seen is None:
        seen = set()
    if class_name in seen:
        return set()
    seen.add(class_name)

    methods = set()
    base_names = []
    for path in iter_py(src_dir):
        try:
            with open(path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read())
        except (OSError, SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and not item.name.startswith("_"):
                        methods.add(item.name)
                for b in node.bases:
                    if isinstance(b, ast.Name):
                        base_names.append(b.id)
                    elif isinstance(b, ast.Attribute):
                        base_names.append(b.attr)

    # 递归收集项目内基类的方法
    for b in base_names:
        methods |= _collect_class_methods(src_dir, b, seen)
    return methods


def check_contract_diff(src_dir):
    """项 6: Python↔JS 契约双向 diff（P-M1 最高危拦截）。
    JS 侧抓两类来源：静态调用 api.xxx + 动态调用 apiMethod='exec_xxx' 再 api[apiMethod]()
    Python 侧：解析 class Api 的 public 方法（**含继承的 Mixin 方法**，排除 _ 开头私有）
    """
    # --- Python 侧：提取 Api 类的 public 方法（含继承） ---
    api_path = os.path.join(src_dir, "app_webview.py")
    if not os.path.isfile(api_path):
        WARN.append("契约 diff: app_webview.py 不存在，跳过")
        return
    python_methods = _collect_class_methods(src_dir, "Api")
    if not python_methods:
        WARN.append("契约 diff: 未解析到 Api 类的任何 public 方法，跳过")
        return

    # --- JS 侧：从 app.html 提取调用的方法名 ---
    html_path = os.path.join(src_dir, "app.html")
    if not os.path.isfile(html_path):
        WARN.append("契约 diff: app.html 不存在，跳过")
        return
    with open(html_path, "r", encoding="utf-8") as f:
        js_text = f.read()

    # a) 静态调用: pywebview.api.xxx( 或 api.xxx(
    js_static = set(re.findall(r'(?:pywebview\.api|api)\.(\w+)\s*\(', js_text))
    # b) 动态调用: apiMethod = 'xxx'  + api[apiMethod]()
    js_dynamic = set(re.findall(r"apiMethod\s*=\s*['\"](\w+)['\"]", js_text))
    js_calls = js_static | js_dynamic

    # 过滤掉非 Api 方法的 JS 内置调用（如 then, catch 等）
    js_calls = {c for c in js_calls if not c.startswith("then") and c not in
                ("catch", "finally", "apply", "call", "bind", "toString")}

    # v3.0 修复 D-2 误报：判定"死代码"前，先排除被 Python 内部调用的方法。
    # 实测（2026-08-29）：原逻辑把 set_window（app_webview.py:1159 api.set_window(window)）
    # 与 add_files（app_webview.py:201 self.add_files(paths)）误报为死代码，二者实为
    # Python 侧内部装配/复用，与 JS 契约无关。误报率 67% → 修复后 0%。
    internal_calls = set()
    for path in iter_py(src_dir):
        try:
            with open(path, "r", encoding="utf-8") as f:
                py_text = f.read()
        except OSError:
            continue
        for m in re.finditer(
                r'(?:self|api|self\.api|_api)\.(\w+)\s*\(', py_text):
            internal_calls.add(m.group(1))

    # --- 双向 diff ---
    # JS 有 Python 无 → 阻塞（契约断裂）
    missing = js_calls - python_methods
    for m in sorted(missing):
        BLOCK.append(f"契约 diff: JS 调用 api.{m}() 但 Python Api 类无此方法（P-M1）")

    # Python 有、JS 无、且 Python 内部也不调用 → 真死代码
    dead = python_methods - js_calls - internal_calls
    for m in sorted(dead):
        WARN.append(
            f"契约 diff: Python Api.{m}() 既未被 JS 调用、也未被 Python 内部调用"
            f"（真死代码，建议删除或登记台账）")


def check_version_hardcode(src_dir):
    """项 7: 版本号硬编码扫描（P-M4 拦截）。
    VERSION 文件是唯一真相源，代码中禁止硬编码版本号。
    例外：注释中的历史版本说明、VERSION 常量回退值（与 VERSION 文件一致时不告警）。
    """
    version_path = os.path.join(ROOT, "VERSION")
    try:
        with open(version_path, "r", encoding="utf-8") as f:
            true_version = f.read().strip()
    except OSError:
        true_version = None

    for path in iter_py(src_dir):
        rel = os.path.relpath(path, ROOT)
        # legacy 目录豁免版本号扫描（不打包、不维护）
        if "legacy" in path.replace("\\", "/").split("/"):
            continue
        with open(path, "r", encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                stripped = line.lstrip()
                # 豁免注释行
                if stripped.startswith("#"):
                    continue
                # 豁免 sys.stderr 的日志行
                if "sys.stderr" in line:
                    continue
                # 查找版本号模式
                for m in RE_VERSION.finditer(line):
                    ver = m.group(1)
                    # 豁免：与 VERSION 文件一致的回退常量
                    if true_version and ver == true_version:
                        continue
                    # 豁免：python 版本要求（如 3.13.0）
                    if "python" in line.lower() or "pip" in line.lower():
                        continue
                    # 豁免：注释中的历史版本
                    if "#" in line and line.index("#") < m.start():
                        continue
                    WARN.append(
                        f"{rel}:{i} 硬编码版本号 {ver}"
                        f"（VERSION 文件={true_version or '?'}, P-M4）")

    # 同时检查 app.html 中的占位符
    html_path = os.path.join(src_dir, "app.html")
    if os.path.isfile(html_path):
        with open(html_path, "r", encoding="utf-8") as fh:
            js_text = fh.read()

        # v3.0 修复误报：标准 H 域 / 清单 5.10 明确允许「HTML 加载前占位符」，
        # 前提是 pywebviewready 后由 get_version() 覆盖。实测（2026-08-29）：
        # app.html:296 的 <span id="version">v2.2.3</span> 被 :782-788 的
        # pywebviewready 监听 + get_version().then() 覆盖，属合法占位符，却仍被告警。
        # 且占位符天然落后于 VERSION 一个版本，改 HTML 无法根治 —— 必须豁免。
        version_guard = bool(
            re.search(r"pywebviewready", js_text)
            and re.search(r"get_version\s*\(", js_text)
            and re.search(r"getElementById\(\s*['\"]version['\"]\s*\)", js_text)
        )

        in_block_comment = False   # v2.2.3: 跟踪 /* ... */ 多行注释块，块内续行一并豁免
        with open(html_path, "r", encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                if in_block_comment:
                    if "*/" in line:
                        in_block_comment = False
                    continue
                if "/*" in line and "*/" not in line:
                    in_block_comment = True
                    continue
                # 查找 v X.Y.Z 模式
                for m in re.finditer(r'\bv(\d+\.\d+\.\d+)\b', line):
                    ver = m.group(1)
                    if true_version and ver == true_version:
                        continue
                    # 豁免：HTML 注释 <!-- ... -->
                    if "<!--" in line and line.index("<!--") < m.start():
                        continue
                    # 豁免：CSS/JS 注释 /* ... */ 或 // ...
                    if "/*" in line and line.index("/*") < m.start():
                        continue
                    if "//" in line:
                        slash_idx = line.index("//")
                        if slash_idx < m.start():
                            continue
                    # 豁免：注释中的历史版本说明（如 "v2.1.7 窗口改为直角..."）
                    # 检查版本号前是否有文字说明（非代码上下文）
                    prefix = line[:m.start()].rstrip()
                    if prefix.endswith(("v", "V", "版本", "见")) or "注释" in prefix:
                        continue
                    # 豁免：id="version" 占位符（已被 pywebviewready+get_version() 覆盖）
                    if version_guard and re.search(r'id\s*=\s*["\']version["\']', line):
                        continue
                    WARN.append(
                        f"app.html:{i} 硬编码版本号 v{ver}"
                        f"（VERSION 文件={true_version or '?'}, P-M4）")


def check_core_coverage(src_dir, tests_dir):
    """项 8: core 模块测试覆盖核对。
    每个 core/*.py 模块应至少有 1 个对应的 test_*.py。"""
    core_dir = os.path.join(src_dir, "core")
    if not os.path.isdir(core_dir):
        return
    if not os.path.isdir(tests_dir):
        return

    # 获取 core 模块列表
    core_modules = set()
    for f in os.listdir(core_dir):
        if f.endswith(".py") and not f.startswith("__"):
            core_modules.add(f[:-3])  # 去掉 .py

    # 获取测试文件覆盖的模块
    # v2.2.3: 原逻辑按文件名 test_<模块>.py 匹配，会把集中在 test_core_functional.py
    # 里的测试误判为"覆盖为 0"。改为扫描测试文件内容是否实际引用该模块。
    covered = set()
    test_texts = []
    for f in os.listdir(tests_dir):
        if f.startswith("test_") and f.endswith(".py"):
            try:
                with open(os.path.join(tests_dir, f), "r", encoding="utf-8") as fh:
                    content = fh.read()
            except OSError:
                continue
            test_texts.append(content)
            # 同时保留文件名匹配（test_split.py → split）
            covered.add(f[5:-3])
    for mod in core_modules:
        pat = re.compile(r'(from\s+core\.' + re.escape(mod) + r'\s+import'
                         r'|import\s+core\.' + re.escape(mod) + r'\b'
                         r'|core\.' + re.escape(mod) + r'\.)')
        if any(pat.search(t) for t in test_texts):
            covered.add(mod)

    for mod in sorted(core_modules):
        if mod not in covered:
            WARN.append(f"core/{mod}.py 测试覆盖为 0（需补充 test_{mod}.py）")


def check_win32_calls(src_dir):
    """项 9: Win32/ctypes 调用清单输出（P-M2 提示人工复核）。
    输出所有 ctypes/win32 调用位置，供人工审查是否涉及跨进程操作。"""
    for path in iter_py(src_dir):
        rel = os.path.relpath(path, ROOT)
        # v3.0 修复 D-3 噪音：legacy 目录不打包、不维护，其 Win32 调用无参考价值。
        # 实测（2026-08-29）：28 条清单中 11 条来自 legacy（占 39%），豁免后降至 17 条。
        # 该建议早在 v2.2.2 审查记录中提出但"未实施"，本次落地。
        if "legacy" in path.replace("\\", "/").split("/"):
            continue
        with open(path, "r", encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                # 匹配 ctypes.windll / ctypes.WINFUNCTYPE / windll.user32 等
                if re.search(r'ctypes\.windll|windll\.\w+|SendMessageW?|SetWindowLong|'
                             r'GetWindowLong|GetCursorPos|IsZoomed|GetModuleHandle|'
                             r'DwmExtendFrame|SetWindowPos', line):
                    INFO.append(f"{rel}:{i} Win32 调用: {stripped.strip()[:80]}（P-M2 人工复核）")


def check_dangerous_calls(src_dir):
    """项 10: 危险函数扫描（v3.0 新增，对应清单 3.2）。
    拦截 eval/exec、shell 命令拼接等高危写法——本工具处理用户任意本地文件，输入不可信。
    """
    PATTERNS = [
        (re.compile(r'\beval\s*\('), "eval() 可执行任意代码（用户输入不可信）"),
        (re.compile(r'\bexec\s*\('), "exec() 可执行任意代码（用户输入不可信）"),
        (re.compile(r'\b__import__\s*\('), "__import__() 动态导入（易被注入）"),
        (re.compile(r'\bos\.system\s*\('), "os.system() 存在 shell 注入风险"),
        (re.compile(r'shell\s*=\s*True'), "subprocess(shell=True) 存在 shell 注入风险"),
        (re.compile(r'\bpickle\.loads?\s*\('),
         "pickle 反序列化可执行任意代码（禁用不可信数据）"),
    ]
    for path in iter_py(src_dir):
        rel = os.path.relpath(path, ROOT)
        # legacy 豁免（不打包、不维护）
        if "legacy" in path.replace("\\", "/").split("/"):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            code_part = line.split("#")[0] if "#" in line else line
            for pat, reason in PATTERNS:
                if pat.search(code_part):
                    BLOCK.append(f"{rel}:{i} 危险调用：{reason}")


def check_csv_handroll(src_dir):
    """项 11: 手写 CSV 拼接扫描（v3.0 新增，对应清单 4.2）。
    禁止 ','.join(row) —— 含逗号/引号/换行的字段会被破坏，必须用 csv.writer。
    """
    PATTERNS = [
        re.compile(r'''["']\s*,\s*["']\s*\.join\s*\('''),   # ",".join( / ','.join(
        re.compile(r'''["']\\t["']\s*\.join\s*\('''),        # "\t".join(
        re.compile(r'''["']\s*\|\s*["']\s*\.join\s*\('''),   # "|".join(
    ]
    # csv 模块自身的合法使用不拦截
    for path in iter_py(src_dir):
        rel = os.path.relpath(path, ROOT)
        if "legacy" in path.replace("\\", "/").split("/"):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            code_part = line.split("#")[0] if "#" in line else line
            for pat in PATTERNS:
                if pat.search(code_part):
                    BLOCK.append(
                        f"{rel}:{i} 手写 CSV 拼接（须改用 csv.writer，"
                        f"否则含逗号/引号/换行的字段会被破坏）")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="牛牛文档工具 提交前审查门禁")
    ap.add_argument("--src", default=os.path.join(ROOT, "src"))
    ap.add_argument("--tests", default=os.path.join(ROOT, "tests"))
    args = ap.parse_args()

    print("=" * 60)
    print("牛牛文档工具 · 提交前代码审查门禁（11 项）")
    print("=" * 60)

    print("[1/11] 语法编译 ...")
    check_compile(args.src)

    print("[2/11] 吞异常扫描 ...")
    check_swallow(args.src)

    print("[3/11] 调试残留 print 扫描 ...")
    check_print(args.src)

    print("[4/11] 巨型文件提示（分层） ...")
    check_bigfile(args.src)

    print("[5/11] 运行单测 ...")
    check_tests(args.tests)

    print("[6/11] Python↔JS 契约双向 diff ...")
    check_contract_diff(args.src)

    print("[7/11] 版本号硬编码扫描 ...")
    check_version_hardcode(args.src)

    print("[8/11] core 模块测试覆盖核对 ...")
    check_core_coverage(args.src, args.tests)

    print("[9/11] Win32 调用清单（legacy 豁免） ...")
    check_win32_calls(args.src)

    print("[10/11] 危险函数扫描 ...")
    check_dangerous_calls(args.src)

    print("[11/11] 手写 CSV 拼接扫描 ...")
    check_csv_handroll(args.src)

    print("\n" + "=" * 60)
    print("审查结果")
    print("=" * 60)
    if BLOCK:
        print(f"\n🔴 阻塞项（{len(BLOCK)}）：禁止提交")
        for b in BLOCK:
            print(f"  - {b}")
    else:
        print("\n🔴 阻塞项：无")

    if WARN:
        print(f"\n🟡 建议项（{len(WARN)}）：")
        for w in WARN:
            print(f"  - {w}")

    if INFO:
        print(f"\n💭 细节（{len(INFO)}）：")
        for n in INFO:
            print(f"  - {n}")

    print("\n" + "=" * 60)
    if BLOCK:
        print("结论：不通过，请修复 🔴 阻塞项后再提交。")
        print("=" * 60)
        sys.exit(1)
    else:
        print("结论：通过，可提交（建议顺手处理 🟡 项）。")
        print("=" * 60)
        sys.exit(0)


if __name__ == "__main__":
    main()
