#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CSV 分割功能单元测试 — 测试 core/split.py 的 CsvSplitter。"""
import os
import sys
import tempfile
import unittest

try:
    _src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
    sys.path.insert(0, _src)
    from core.split import CsvSplitter, MAX_SPLIT_ROWS
    from core.merge import CsvMerger
    from core.extract import CsvExtractor
    from core.encoding import EncodingDetector
    HAVE_CORE = True
except Exception:
    HAVE_CORE = False


def make_csv(path, rows, encoding="utf-8", header="a,b,c"):
    with open(path, "w", encoding=encoding, newline="") as f:
        f.write(header + "\n")
        for i in range(rows):
            f.write(f"{i},x,y\n")


@unittest.skipUnless(HAVE_CORE, "需要可导入 core 模块的环境")
class TestSplitByRows(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="split_test_")

    def tearDown(self):
        for f in os.listdir(self.tmp):
            try:
                os.remove(os.path.join(self.tmp, f))
            except OSError:
                pass
        try:
            os.rmdir(self.tmp)
        except OSError:
            pass

    def test_small_file_skipped(self):
        p = os.path.join(self.tmp, "small.csv")
        make_csv(p, 100)
        res = CsvSplitter.split_by_rows(p)
        self.assertTrue(res["ok"])
        self.assertTrue(res["skipped"])
        self.assertEqual(res["parts"], [])

    def test_split_count_and_header(self):
        # 2501 行数据 + 1 表头 = 2502 物理行；每片 ≤1000 行(含表头) → 3 片
        p = os.path.join(self.tmp, "big.csv")
        make_csv(p, 2501)
        res = CsvSplitter.split_by_rows(p, max_rows=1000)
        self.assertTrue(res["ok"])
        self.assertFalse(res["skipped"])
        parts = res["parts"]
        self.assertEqual(len(parts), 3)
        sizes = []
        for part in parts:
            with open(part, "r", encoding="utf-8-sig") as f:
                lines = f.read().splitlines()
            sizes.append(len(lines))
            self.assertEqual(lines[0], "a,b,c")  # 每片含表头
            self.assertLessEqual(len(lines), 1000)
        # 末片 = 1000 + 1000 + 504（表头 + 503 数据）
        self.assertEqual(sizes, [1000, 1000, 504])

    def test_filename_zero_padding(self):
        # 13 片 → 零填充宽度为 2，保证字典序即顺序
        p = os.path.join(self.tmp, "huge.csv")
        make_csv(p, 12001)  # 12002 行 → 13 片
        res = CsvSplitter.split_by_rows(p, max_rows=1000)
        names = [os.path.basename(x) for x in res["parts"]]
        self.assertEqual(len(names), 13)
        self.assertEqual(names[0], "huge_part01.csv")
        self.assertEqual(names[-1], "huge_part13.csv")
        self.assertEqual(names, sorted(names))

    def test_gbk_to_utf8sig(self):
        p = os.path.join(self.tmp, "gbk.csv")
        make_csv(p, 1500, encoding="gbk", header="列一,列二")
        res = CsvSplitter.split_by_rows(p, max_rows=1000)
        self.assertEqual(len(res["parts"]), 2)
        with open(res["parts"][0], "r", encoding="utf-8-sig") as f:
            first = f.readline().rstrip("\n")
        self.assertEqual(first, "列一,列二")


@unittest.skipUnless(HAVE_CORE, "需要可导入 core 模块的环境")
class TestSplitByDate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="split_date_test_")

    def tearDown(self):
        for f in os.listdir(self.tmp):
            try:
                os.remove(os.path.join(self.tmp, f))
            except OSError:
                pass
        try:
            os.rmdir(self.tmp)
        except OSError:
            pass

    def test_split_by_day(self):
        p = os.path.join(self.tmp, "dates.csv")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write("id,日期,value\n")
            f.write("1,2026-01-15,100\n")
            f.write("2,2026-01-15,200\n")
            f.write("3,2026-02-20,300\n")
            f.write("4,2026-03-10,400\n")
        res = CsvSplitter.split_by_date(p, date_column="日期", granularity="day")
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["parts"]), 3)

    def test_split_by_month(self):
        p = os.path.join(self.tmp, "months.csv")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write("id,日期,value\n")
            f.write("1,2026-01-15,100\n")
            f.write("2,2026-01-20,200\n")
            f.write("3,2026-02-01,300\n")
        res = CsvSplitter.split_by_date(p, date_column="日期", granularity="month")
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["parts"]), 2)

    def test_auto_detect_date_column(self):
        p = os.path.join(self.tmp, "auto.csv")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write("id,date,value\n")
            f.write("1,2026-01-15,100\n")
            f.write("2,2026-02-20,200\n")
        res = CsvSplitter.split_by_date(p, date_column=None, granularity="day")
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["parts"]), 2)


@unittest.skipUnless(HAVE_CORE, "需要可导入 core 模块的环境")
class TestCsvMerger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="merge_test_")

    def tearDown(self):
        for f in os.listdir(self.tmp):
            try:
                os.remove(os.path.join(self.tmp, f))
            except OSError:
                pass
        try:
            os.rmdir(self.tmp)
        except OSError:
            pass

    def test_merge_fast(self):
        f1 = os.path.join(self.tmp, "f1.csv")
        f2 = os.path.join(self.tmp, "f2.csv")
        make_csv(f1, 10, header="a,b,c")
        make_csv(f2, 10, header="a,b,c")
        out = os.path.join(self.tmp, "merged.csv")
        res = CsvMerger.merge_fast([f1, f2], out, skip_headers=True)
        self.assertTrue(res["ok"])
        with open(out, "r", encoding="utf-8-sig") as f:
            lines = f.read().splitlines()
        # 表头 + 10行 + 10行 = 21 行
        self.assertEqual(len(lines), 21)
        self.assertEqual(lines[0], "a,b,c")

    def test_merge_with_filename(self):
        f1 = os.path.join(self.tmp, "f1.csv")
        f2 = os.path.join(self.tmp, "f2.csv")
        make_csv(f1, 5, header="a,b,c")
        make_csv(f2, 5, header="a,b,c")
        out = os.path.join(self.tmp, "merged.csv")
        res = CsvMerger.merge_with_filename([f1, f2], out, col_name="来源文件")
        self.assertTrue(res["ok"])
        with open(out, "r", encoding="utf-8-sig") as f:
            lines = f.read().splitlines()
        # 表头(含来源文件列) + 5+5 = 11 行
        self.assertEqual(len(lines), 11)
        self.assertEqual(lines[0], "a,b,c,来源文件")
        # 检查最后一列含文件名
        self.assertIn("f1.csv", lines[1])
        self.assertIn("f2.csv", lines[6])


@unittest.skipUnless(HAVE_CORE, "需要可导入 core 模块的环境")
class TestCsvExtractor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="extract_test_")

    def tearDown(self):
        for f in os.listdir(self.tmp):
            try:
                os.remove(os.path.join(self.tmp, f))
            except OSError:
                pass
        try:
            os.rmdir(self.tmp)
        except OSError:
            pass

    def test_extract_contains(self):
        p = os.path.join(self.tmp, "data.csv")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write("id,name,city\n")
            f.write("1,张三,北京\n")
            f.write("2,李四,上海\n")
            f.write("3,王五,北京\n")
        out = os.path.join(self.tmp, "result.csv")
        res = CsvExtractor.extract_by_keyword(
            p, ["北京"], out, match_mode="contains")
        self.assertTrue(res["ok"])
        self.assertEqual(res["matched_count"], 2)
        with open(out, "r", encoding="utf-8-sig") as f:
            lines = f.read().splitlines()
        self.assertEqual(len(lines), 3)  # 表头 + 2 行
        self.assertEqual(lines[1], "1,张三,北京")
        self.assertEqual(lines[2], "3,王五,北京")

    def test_extract_multiple_keywords(self):
        p = os.path.join(self.tmp, "data2.csv")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write("id,name\n")
            f.write("1,apple\n")
            f.write("2,banana\n")
            f.write("3,cherry\n")
        out = os.path.join(self.tmp, "result2.csv")
        res = CsvExtractor.extract_by_keyword(
            p, ["apple", "cherry"], out, match_mode="contains")
        self.assertTrue(res["ok"])
        self.assertEqual(res["matched_count"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
