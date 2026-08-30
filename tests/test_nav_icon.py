#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导航图标 path_data 解析冒烟测试

验证 NAV_GROUPS 中所有图标的 path_data 能被 _draw_nav_icon 的
词法切分器正确解析，不抛 ValueError / IndexError。
"""
import os
import re
import sys
import unittest

_src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
sys.path.insert(0, _src)


def parse_icon_path(path_data):
    """
    复刻 doc_converter.py 中 _draw_nav_icon 的解析逻辑（不依赖 Tk Canvas）。
    如果解析通过返回 True，否则抛异常。
    """
    tokens = re.findall(r"[a-zA-Z]+|[-+]?(?:\d+\.\d+|\.\d+|\d+)", path_data)
    n = len(tokens)
    cx = cy = 0.0
    i = 0
    while i < n:
        cmd = tokens[i]
        i += 1
        if cmd == "rect":
            if i + 4 >= n:
                raise ValueError(f"rect 参数不足: 需要 5 个, 剩余 {n - i}")
            x = float(tokens[i]); y = float(tokens[i + 1])
            w = float(tokens[i + 2]); h = float(tokens[i + 3])
            r = float(tokens[i + 4])
            i += 5
        elif cmd == "circle":
            if i + 2 >= n:
                raise ValueError(f"circle 参数不足: 需要 3 个, 剩余 {n - i}")
            ccx = float(tokens[i]); ccy = float(tokens[i + 1]); cr = float(tokens[i + 2])
            i += 3
        elif cmd in ("M", "m", "L", "l"):
            first = True
            while i + 1 < n and not tokens[i][0].isalpha():
                ax = float(tokens[i]); ay = float(tokens[i + 1]); i += 2
                nx = ax if cmd.isupper() else cx + ax
                ny = ay if cmd.isupper() else cy + ay
                cx, cy = nx, ny
                first = False
        elif cmd in ("H", "h"):
            while i < n and not tokens[i][0].isalpha():
                d = float(tokens[i]); i += 1
                cx = (cx + d) if cmd == "h" else d
        elif cmd in ("V", "v"):
            while i < n and not tokens[i][0].isalpha():
                d = float(tokens[i]); i += 1
                cy = (cy + d) if cmd == "v" else d
        elif cmd.lower() == "z":
            pass
        else:
            while i < n and not tokens[i][0].isalpha():
                i += 1
    return True


class TestNavIconParsing(unittest.TestCase):
    """测试所有 NAV_GROUPS 图标 path_data 的可解析性"""

    def _get_nav_groups(self):
        """从 doc_converter 模块导入 NAV_GROUPS"""
        try:
            from doc_converter import NAV_GROUPS
            return NAV_GROUPS
        except Exception:
            # 如果导入失败（如缺少 tkinterdnd2），直接从源码提取
            try:
                # 尝试无 GUI 依赖的方式
                import importlib
                spec = importlib.util.spec_from_file_location(
                    "doc_converter", os.path.join(_src, "doc_converter.py"))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod.NAV_GROUPS
            except Exception:
                return None

    def test_all_icons_parseable(self):
        """所有 9 个导航图标的 path_data 必须可被解析器无异常解析"""
        groups = self._get_nav_groups()
        if groups is None:
            self.skipTest("无法导入 doc_converter 模块（可能缺少 tkinterdnd2）")
        total = 0
        for grp_name, items in groups:
            for fid, name, fmt, desc, icon_path in items:
                with self.subTest(func=fid, icon=icon_path):
                    try:
                        result = parse_icon_path(icon_path)
                        self.assertTrue(result)
                        total += 1
                    except (ValueError, IndexError) as e:
                        self.fail(f"图标解析失败 [{fid}]: {icon_path} → {e}")
        self.assertGreaterEqual(total, 7, "应至少有 7 个导航图标")

    def test_rect_icon_parseable(self):
        """含 rect 命令的图标（如按日期分割）必须正确解析"""
        path = "rect 2.5,3,11,10,1.5 M2.5 6h11 M5 2v2 M11 2v2"
        self.assertTrue(parse_icon_path(path))

    def test_circle_icon_parseable(self):
        """含 circle 命令的图标（如关键字提取）必须正确解析"""
        path = "circle 7,7,4 M10 10l3.5 3.5"
        self.assertTrue(parse_icon_path(path))

    def test_multi_rect_icon_parseable(self):
        """多个 rect 命令的图标（如多工作簿合并）必须正确解析"""
        path = "rect 2.5,3,5,7,1 rect 8.5,6,5,7,1 M5.5 10l5-1"
        self.assertTrue(parse_icon_path(path))

    def test_empty_path(self):
        """空 path_data 应安全返回（不抛异常）"""
        self.assertTrue(parse_icon_path(""))

    def test_malformed_path_raises(self):
        """rect 参数不足时必须抛 ValueError"""
        with self.assertRaises(ValueError):
            parse_icon_path("rect 1,2,3")


if __name__ == "__main__":
    unittest.main(verbosity=2)
