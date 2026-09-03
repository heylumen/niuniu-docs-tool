#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
牛牛文档工具 — 一键打包脚本（v2.1.0+ WebView 版）
功能: 创建/复用虚拟环境 → 安装依赖 → 重新生成图标 → 用 PyInstaller 打包为单文件 EXE
输出: dist/牛牛文档工具_vX.Y.Z.exe （版本号取自 VERSION 文件）
      并自动复制带版本号 EXE 到项目根目录(首页)，旧版本归档到 releases/
源码位置: src/app_webview.py（主程序）与 src/core/（业务模块）
用法: python build.py
"""
import os
import sys
import subprocess
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(ROOT, ".venv")
VERSION_FILE = os.path.join(ROOT, "VERSION")
SRC = os.path.join(ROOT, "src")
APP_NAME = "牛牛文档工具"


def read_version():
    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            return f.read().strip() or "1.0.0"
    except OSError:
        return "1.0.0"


def venv_python():
    if sys.platform.startswith("win"):
        return os.path.join(VENV_DIR, "Scripts", "python.exe")
    return os.path.join(VENV_DIR, "bin", "python")


def ensure_venv():
    if not os.path.isdir(VENV_DIR):
        print("[1/4] 创建虚拟环境 .venv ...")
        subprocess.check_call([sys.executable, "-m", "venv", VENV_DIR])
    py = venv_python()
    print("[2/4] 安装依赖 (Pillow, PyInstaller, openpyxl, pywebview, pythonnet) ...")
    subprocess.check_call([py, "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_call([py, "-m", "pip", "install", "-r", os.path.join(ROOT, "requirements.txt")])
    return py


def regen_icon(py):
    """重新生成图标（v2.4.0 起：萌系小牛 v4 引擎，暖橙容器·白牛）。

    旧工具 tools/generate_icon.py（Fluent 文档图标方案）已删除——若继续调用它会把
    src/app_icon.ico 覆盖回旧图标，导致新图标静默失效。
    """
    print("[3/4] 重新生成图标 src/app_icon.ico ...")
    subprocess.check_call([py, os.path.join(ROOT, "tools", "cow_icon_v4.py"), "build"])


def publish(version):
    """发布最新版到首页(根目录)，并把旧版本归档到 releases/"""
    exe_base = f"{APP_NAME}_v{version}"
    built = os.path.join(ROOT, "dist", f"{exe_base}.exe")
    home = os.path.join(ROOT, f"{exe_base}.exe")
    if os.path.exists(built):
        shutil.copy2(built, home)
        print(f"[发布] 首页入口已更新: {home}")
    else:
        print("  警告: 未找到打包产物", built)
    # 归档旧版本（根目录中版本号不等于当前的同名 EXE）
    rel_dir = os.path.join(ROOT, "releases")
    os.makedirs(rel_dir, exist_ok=True)
    for fn in os.listdir(ROOT):
        if fn.startswith(f"{APP_NAME}_v") and fn.endswith(".exe") and fn != f"{exe_base}.exe":
            old = os.path.join(ROOT, fn)
            shutil.move(old, os.path.join(rel_dir, fn))
            print(f"[归档] 旧版本已移入 releases/: {fn}")


def build(py, version):
    exe_base = f"{APP_NAME}_v{version}"
    print(f"[4/4] 打包 EXE → dist/{exe_base}.exe")
    subprocess.check_call([
        py, "-m", "PyInstaller", "--onefile", "--windowed",
        f"--name={exe_base}", "--icon=src/app_icon.ico",
        "--add-data", "src/app.html;.",
        "--add-data", "src/app_icon.ico;.",
        "--add-data", "VERSION;.",
        "--add-data", "src/core;core",
        "--collect-all", "webview",
        "--collect-all", "pythonnet",
        "--collect-all", "clr_loader",
        "--collect-all", "openpyxl",
        "--collect-all", "xlrd",
        # OPT-1: 裁剪跨平台后端（仅用 winforms + edgechromium）
        "--exclude-module", "webview.platforms.gtk",
        "--exclude-module", "webview.platforms.cocoa",
        "--exclude-module", "webview.platforms.qt",
        "--exclude-module", "webview.platforms.cef",
        "--exclude-module", "webview.platforms.mshtml",
        "--exclude-module", "webview.platforms.android",
        # OPT-2: openpyxl 不使用的高级子模块
        "--exclude-module", "openpyxl.chart",
        "--exclude-module", "openpyxl.drawing",
        "--exclude-module", "openpyxl.pivot",
        # OPT-3: 移除 assert 与 docstring，减小 PYZ 体积
        "--optimize=2",
        "--clean", "--noconfirm",
        "--distpath", "dist", os.path.join(SRC, "app_webview.py")
    ])
    # 重命名为带版本号（PyInstaller 已直接用带版本号的名称，无需重命名）
    dst = os.path.join(ROOT, "dist", f"{exe_base}.exe")
    if os.path.exists(dst):
        print(f"  完成: {dst}")
    else:
        print("  警告: 未找到打包产物", dst)
    # 发布到首页 + 归档旧版本（v2.4.1: publish 先于清理，防 rmtree 失败阻断交付）
    publish(version)
    # 清理中间文件
    junk_build = os.path.join(ROOT, "build")
    if os.path.isdir(junk_build):
        shutil.rmtree(junk_build)


if __name__ == "__main__":
    py = ensure_venv()
    regen_icon(py)
    build(py, read_version())
    print("\n打包完成。最新 EXE 已发布到项目根目录(首页)，历史版本见 releases/。")
