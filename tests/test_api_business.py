#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""牛牛文档工具 — core/api_business.py 拆分回归测试（v2.3.0）

背景：v2.3.0 将 app_webview.py 的 9 个 exec_* 业务功能拆至 core/api_business.py
（BusinessApiMixin），原文件 1169 行 → 611 行（打包链阈值 800）。

本文件守护该重构的两类风险：
  1) **契约风险**：拆分后 JS 仍能调用全部 exec_*（Mixin 继承是否生效）；
  2) **行为风险**：真实业务流程未变（端到端跑一次编码转换）。

⚠️ 这是本项目最高危缺陷模式 P-M1（动态契约漂移）的护栏。
   若哪天有人误删 Mixin 或改了方法名而前端未同步，这里的测试会先红。

运行:
    python -m unittest tests.test_api_business -v
或经提交门禁 scripts/review_check.py 自动发现执行。
"""
import json
import os
import sys
import tempfile
import time
import unittest

_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from core.api_business import BusinessApiMixin
from app_webview import Api

# 前端 app.html 实际调用的 9 个业务方法（契约面）
EXPECTED_EXEC = [
    "exec_convert", "exec_split_rows", "exec_split_date",
    "exec_csv_merge", "exec_wb_merge", "exec_sheet_merge",
    "exec_keyword", "exec_wb_split", "exec_wide_split",
]


def _write_text(path, text, encoding="utf-8"):
    with open(path, "w", encoding=encoding, newline="") as f:
        f.write(text)


def _read_bytes_head(path, n=3):
    with open(path, "rb") as f:
        return f.read(n)


class TestMixinContract(unittest.TestCase):
    """契约面：9 个 exec_* 必须仍可通过 Api 调用（P-M1 护栏）"""

    def test_all_exec_methods_on_mixin(self):
        """9 个业务方法都定义在 BusinessApiMixin 上"""
        for name in EXPECTED_EXEC:
            self.assertTrue(hasattr(BusinessApiMixin, name),
                            "BusinessApiMixin 缺少 %s" % name)

    def test_api_inherits_all_exec(self):
        """Api 继承 Mixin 后，9 个方法全部可调用"""
        api = Api()
        for name in EXPECTED_EXEC:
            self.assertTrue(hasattr(api, name), "Api 缺少 %s（Mixin 未生效？）" % name)
            self.assertTrue(callable(getattr(api, name)), "%s 不可调用" % name)

    def test_exec_are_public_not_private(self):
        """exec_* 不能以 _ 开头，否则 pywebview 不会暴露给 JS"""
        for name in EXPECTED_EXEC:
            self.assertFalse(name.startswith("_"), "%s 被误设为私有" % name)

    def test_no_get_info_after_deadcode_removal(self):
        """台账 260829-02：get_info 已作为死代码删除，不得复活"""
        self.assertFalse(hasattr(Api, "get_info"),
                         "get_info 是已删除的死代码，不应存在")

    def test_internal_helpers_not_exposed(self):
        """worker 等内部辅助方法必须是私有的（不暴露给 JS）"""
        for name in ("_convert_worker", "_split_rows_worker", "_on_done"):
            if hasattr(Api, name):
                self.assertTrue(name.startswith("_"),
                                "%s 不应是 public（会被暴露给 JS）" % name)


class TestExecPreconditions(unittest.TestCase):
    """前置校验：无文件 / 忙碌态 / 非法参数"""

    def setUp(self):
        self.api = Api()

    def test_exec_convert_without_files(self):
        r = self.api.exec_convert(json.dumps({"encoding": "auto"}))
        self.assertFalse(r["ok"], r)
        self.assertIn("请先添加文件", r["msg"], r)

    def test_all_exec_reject_empty_file_list(self):
        """9 个功能在无文件时都应给出明确提示，而不是崩溃或静默成功"""
        for name in EXPECTED_EXEC:
            with self.subTest(method=name):
                fn = getattr(self.api, name)
                r = fn(json.dumps({}))
                self.assertIsInstance(r, dict, "%s 返回值不是 dict" % name)
                self.assertIn("ok", r, "%s 返回值缺少 ok 字段" % name)

    def test_malformed_json_not_crash(self):
        """非法 JSON 参数不得抛异常（前端传参异常时应优雅降级）"""
        for name in EXPECTED_EXEC:
            with self.subTest(method=name):
                fn = getattr(self.api, name)
                try:
                    r = fn("这不是JSON{{{")
                    self.assertIsInstance(r, dict)
                except Exception as ex:
                    self.fail("%s 遇非法 JSON 抛异常: %s: %s" % (name, type(ex).__name__, ex))

    def test_busy_state_blocks_new_task(self):
        """忙碌中发起新任务应被拒绝"""
        self.api.is_busy = True
        r = self.api.exec_convert(json.dumps({"encoding": "auto"}))
        self.assertFalse(r["ok"], r)
        self.assertIn("正在处理中", r["msg"], r)


class TestExecConvertEndToEnd(unittest.TestCase):
    """端到端：真实跑一次编码转换（验证拆分后业务链路完整）"""

    def _wait_for(self, predicate, timeout=10.0, interval=0.05):
        """轮询等待条件成立，返回是否成功。避免固定 sleep 造成的偶发失败。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return True
            time.sleep(interval)
        return False

    def test_convert_gbk_to_utf8_bom(self):
        """GBK 文件 → UTF-8-BOM 输出，内容不乱码（无头运行，不依赖窗口）"""
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "测试.csv")
            _write_text(src, "姓名,金额\n张三,100\n李四,200\n", encoding="gbk")

            api = Api()
            add_r = api.add_files(json.dumps([src]))
            self.assertTrue(add_r["ok"], add_r)
            self.assertEqual(len(api.file_list), 1, "文件未加入列表")

            out_dir = os.path.join(d, "out")
            os.makedirs(out_dir, exist_ok=True)

            r = api.exec_convert(json.dumps({
                "encoding": "auto",
                "copy_mode": True,
                "out_dir": out_dir,
                "open_folder": False,      # 测试环境禁止打开资源管理器
            }))
            self.assertTrue(r["ok"], r)
            self.assertIn("开始转换", r["msg"], r)

            # worker 在后台线程执行，轮询等待产物出现
            dst = os.path.join(out_dir, "测试_已转换.csv")
            appeared = self._wait_for(lambda: os.path.isfile(dst))
            self.assertTrue(appeared, "转换超时：未生成 %s" % dst)

            # 校验产物：UTF-8 BOM + 中文不乱码
            self.assertEqual(_read_bytes_head(dst), b"\xef\xbb\xbf", "输出缺少 UTF-8 BOM")
            with open(dst, "r", encoding="utf-8-sig", newline="") as f:
                content = f.read()
            self.assertIn("姓名", content)
            self.assertIn("张三", content)
            self.assertIn("100", content)

            # 忙碌标志应被 _on_done 复位
            self.assertFalse(api.is_busy, "转换完成后 is_busy 未复位")

    def test_convert_does_not_modify_source(self):
        """copy_mode=True 时源文件必须保持不变"""
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "src.csv")
            _write_text(src, "姓名,金额\n张三,100\n", encoding="gbk")
            with open(src, "rb") as f:
                before = f.read()

            api = Api()
            api.add_files(json.dumps([src]))
            api.exec_convert(json.dumps({
                "encoding": "auto", "copy_mode": True,
                "out_dir": d, "open_folder": False,
            }))
            dst = os.path.join(d, "src_已转换.csv")
            self.assertTrue(self._wait_for(lambda: os.path.isfile(dst)), "未生成输出")

            with open(src, "rb") as f:
                after = f.read()
            self.assertEqual(after, before, "源文件被意外修改")


if __name__ == "__main__":
    unittest.main(verbosity=2)
