#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""牛牛文档工具 — core/utils.py 单元测试（台账 260829-03）

背景：utils.py 此前测试覆盖为 0，是唯一未被覆盖的 core 模块。
本文件覆盖 format_elapsed / format_size 的全部分支与边界值。

覆盖策略（分支 + 边界，优先于 happy path）：
  format_elapsed : 毫秒 / 秒 / 分秒 / 时分秒 四档，含各档临界值
  format_size    : 0 / B / KB / MB / GB 五档，含 1024 临界与超大值、负数

运行:
    python -m unittest tests.test_utils -v
或经提交门禁 scripts/review_check.py 自动发现执行。
"""
import os
import sys
import unittest

_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from core.utils import format_elapsed, format_size


class TestFormatElapsed(unittest.TestCase):
    """format_elapsed：四档时间格式化"""

    # --- 第一档：< 1 秒 → 毫秒 ---
    def test_zero(self):
        self.assertEqual(format_elapsed(0), "0 毫秒")

    def test_sub_second(self):
        self.assertEqual(format_elapsed(0.5), "500 毫秒")

    def test_just_below_one_second(self):
        """临界值：0.999 秒仍走毫秒档（不四舍五入进位到 1 秒）"""
        self.assertEqual(format_elapsed(0.999), "999 毫秒")

    # --- 第二档：1 ~ 60 秒 → 秒（两位小数）---
    def test_exactly_one_second(self):
        self.assertEqual(format_elapsed(1), "1.00 秒")

    def test_fractional_seconds(self):
        self.assertEqual(format_elapsed(12.345), "12.35 秒")

    def test_just_below_one_minute(self):
        self.assertEqual(format_elapsed(59.99), "59.99 秒")

    # --- 第三档：60 秒 ~ 1 小时 → 分秒 ---
    def test_exactly_one_minute(self):
        self.assertEqual(format_elapsed(60), "1分0.0秒")

    def test_minutes_and_seconds(self):
        self.assertEqual(format_elapsed(125.5), "2分5.5秒")

    def test_just_below_one_hour(self):
        self.assertEqual(format_elapsed(3599), "59分59.0秒")

    # --- 第四档：≥ 1 小时 → 时分秒 ---
    def test_exactly_one_hour(self):
        self.assertEqual(format_elapsed(3600), "1时0分0秒")

    def test_hours_minutes_seconds(self):
        self.assertEqual(format_elapsed(3661), "1时1分1秒")

    def test_large_duration(self):
        self.assertEqual(format_elapsed(7325), "2时2分5秒")

    # --- 契约性质 ---
    def test_returns_string_for_all_inputs(self):
        for v in (0, 0.001, 1, 60, 3600, 86400):
            self.assertIsInstance(format_elapsed(v), str)

    def test_no_negative_unit_values(self):
        """结果中不出现负号（耗时不可能为负）"""
        for v in (0, 0.5, 1, 60, 3600):
            self.assertNotIn("-", format_elapsed(v))


class TestFormatSize(unittest.TestCase):
    """format_size：五档文件大小格式化"""

    # --- 特例：0 ---
    def test_zero(self):
        """0 走独立分支，返回 '0 B' 而非 '0.0 B'"""
        self.assertEqual(format_size(0), "0 B")

    # --- B 档 ---
    def test_bytes(self):
        self.assertEqual(format_size(512), "512.0 B")

    def test_just_below_1kb(self):
        self.assertEqual(format_size(1023), "1023.0 B")

    # --- KB 档 ---
    def test_exactly_1kb(self):
        self.assertEqual(format_size(1024), "1.0 KB")

    def test_fractional_kb(self):
        self.assertEqual(format_size(1536), "1.5 KB")

    def test_just_below_1mb(self):
        self.assertEqual(format_size(1024 * 1024 - 1), "1024.0 KB")

    # --- MB 档 ---
    def test_exactly_1mb(self):
        self.assertEqual(format_size(1024 * 1024), "1.0 MB")

    def test_fractional_mb(self):
        self.assertEqual(format_size(1024 * 1024 * 2.5), "2.5 MB")

    # --- GB 档（循环上限，不再向上进位）---
    def test_exactly_1gb(self):
        self.assertEqual(format_size(1024 ** 3), "1.0 GB")

    def test_beyond_1gb_stays_in_gb(self):
        """GB 是单位表上限，5GB 仍显示为 GB（不会变成 TB 或溢出）"""
        self.assertEqual(format_size(1024 ** 3 * 5), "5.0 GB")

    def test_very_large_value(self):
        """超大值（1TB）不崩溃、不产生科学计数法以外的异常格式"""
        result = format_size(1024 ** 4)
        self.assertTrue(result.endswith("GB"), result)
        self.assertEqual(result, "1024.0 GB")

    # --- 负数（防御性）---
    def test_negative_bytes(self):
        """负大小不应崩溃（循环用 abs() 判断，输出保留负号）"""
        result = format_size(-2048)
        self.assertEqual(result, "-2.0 KB")

    # --- 契约性质 ---
    def test_unit_suffix_always_valid(self):
        for v in (0, 1, 1024, 1024 ** 2, 1024 ** 3, 1024 ** 4):
            self.assertTrue(
                format_size(v).endswith((" B", " KB", " MB", " GB")),
                format_size(v),
            )

    def test_returns_string(self):
        for v in (0, 1, 1024, 1024 ** 3):
            self.assertIsInstance(format_size(v), str)


if __name__ == "__main__":
    unittest.main(verbosity=2)
