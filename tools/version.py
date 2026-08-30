#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
牛牛文档转换工具 — 版本助手
子命令:
  current                  显示当前版本号与 git 描述
  list                     列出所有版本标签
  switch <版本>            切换到指定历史版本（detached HEAD，仅查看）
  restore                  恢复到最新开发分支（main）
  bump <major|minor|patch> 递增版本号并提交打 tag
说明: 版本号保存在 VERSION 文件；每次发布对应一个 git tag vX.Y.Z。
"""
import os
import sys
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
# tools/version.py 的上一级即项目根
PROJECT_ROOT = os.path.dirname(ROOT)
VERSION_FILE = os.path.join(PROJECT_ROOT, "VERSION")
MAIN_BRANCH = "main"


def run(args, cwd=PROJECT_ROOT):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def read_version():
    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "(未知)"


def write_version(v):
    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        f.write(v + "\n")


def parse_version(v):
    parts = v.split(".")
    nums = []
    for p in parts[:3]:
        try:
            nums.append(int(p))
        except ValueError:
            nums.append(0)
    while len(nums) < 3:
        nums.append(0)
    return nums[0], nums[1], nums[2]


def cmd_current():
    print(f"当前版本: {read_version()}")
    r = run(["git", "describe", "--tags", "--always"])
    if r.returncode == 0:
        print(f"Git 描述: {r.stdout.strip()}")


def cmd_list():
    r = run(["git", "tag", "--sort=-v:refname"])
    if r.returncode != 0:
        print("未初始化 Git 仓库。")
        return
    tags = r.stdout.strip().splitlines()
    if not tags:
        print("暂无版本标签。")
        return
    print("已发布版本:")
    for t in tags:
        print(f"  {t}")


def _is_dirty():
    r = run(["git", "status", "--porcelain"])
    return bool(r.stdout.strip())


def cmd_switch(version):
    tag = version if version.startswith("v") else f"v{version}"
    r = run(["git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}"])
    if r.returncode != 0:
        print(f"错误: 不存在版本标签 {tag}")
        return
    if _is_dirty():
        print("检测到未提交改动，先 git stash ...")
        run(["git", "stash"])
    run(["git", "checkout", tag])
    print(f"已切换到 {tag}（分离 HEAD，仅供查看）。")
    print(f"查看完毕后执行: python tools/version.py restore 回到 {MAIN_BRANCH}。")


def cmd_restore():
    run(["git", "checkout", MAIN_BRANCH])
    print(f"已恢复到开发分支 {MAIN_BRANCH}（最新版本）。")


def cmd_bump(level):
    level = level.lower()
    if level not in ("major", "minor", "patch"):
        print("用法: python tools/version.py bump <major|minor|patch>")
        return
    x, y, z = parse_version(read_version())
    if level == "major":
        x, y, z = x + 1, 0, 0
    elif level == "minor":
        y, z = y + 1, 0
    else:
        z = z + 1
    new_v = f"{x}.{y}.{z}"
    write_version(new_v)
    tag = f"v{new_v}"
    run(["git", "add", "VERSION"])
    run(["git", "commit", "-m", f"chore: 发布版本 {new_v}"])
    run(["git", "tag", tag])
    print(f"版本已递增为 {new_v} 并提交打 tag {tag}。")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    sub = sys.argv[1].lower()
    if sub == "current":
        cmd_current()
    elif sub == "list":
        cmd_list()
    elif sub == "switch":
        if len(sys.argv) < 3:
            print("用法: python tools/version.py switch <版本>")
            return
        cmd_switch(sys.argv[2])
    elif sub == "restore":
        cmd_restore()
    elif sub == "bump":
        if len(sys.argv) < 3:
            print("用法: python tools/version.py bump <major|minor|patch>")
            return
        cmd_bump(sys.argv[2])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
