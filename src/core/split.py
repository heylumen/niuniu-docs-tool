# -*- coding: utf-8 -*-
"""CSV 分割 — 按行数 / 按日期"""
import os
import csv
import re
import contextlib
from pathlib import Path
from .encoding import EncodingDetector

READ_CHUNK = 8 * 1024 * 1024
WRITE_BUFFER = 8 * 1024 * 1024
MAX_SPLIT_ROWS = 1_000_000


class CsvSplitter:
    """CSV 分割核心逻辑"""

    @staticmethod
    def count_lines(filepath):
        """统计文件物理行数（二进制流式，大缓冲区 chunk.count）"""
        try:
            count = 0
            with open(filepath, "rb") as f:
                while True:
                    chunk = f.read(READ_CHUNK)
                    if not chunk:
                        break
                    count += chunk.count(b"\n")
            with open(filepath, "rb") as f:
                f.seek(0, 2)
                if f.tell() > 0:
                    f.seek(f.tell() - 1)
                    last = f.read(1)
                    if last and last != b"\n":
                        count += 1
            return count
        except OSError:
            return 0

    @staticmethod
    def split_by_rows(src_path, max_rows=MAX_SPLIT_ROWS, progress_callback=None):
        """
        将行数超过 max_rows 的 CSV 按每 max_rows 行拆分为独立文件。
        - 每片均写入表头，保证可独立用 Excel 打开
        - 文件名格式: <原名>_partNN.<后缀>
        - 输出 UTF-8-SIG
        """
        read_enc = EncodingDetector.get_read_encoding(src_path)

        try:
            total = CsvSplitter.count_lines(src_path)
        except OSError:
            return {"ok": False, "msg": "无法读取文件", "parts": []}

        if total <= max_rows:
            return {
                "ok": True, "skipped": True,
                "msg": f"行数 {total} ≤ {max_rows}，无需分割",
                "parts": [], "total": total,
            }

        per_part = max_rows - 1
        data_lines = total - 1
        total_parts = (data_lines + per_part - 1) // per_part
        if total_parts < 1:
            total_parts = 1
        width = len(str(total_parts))

        parent = os.path.dirname(src_path)
        stem = Path(src_path).stem
        suffix = Path(src_path).suffix

        parts = []
        out = None
        part_idx = 0
        written = 0
        try:
            with open(src_path, "r", encoding=read_enc, errors="replace", newline="") as f:
                header = f.readline()
                for ln, line in enumerate(f, start=2):
                    if part_idx == 0 or written >= max_rows:
                        if out is not None:
                            out.close()
                        part_idx += 1
                        part_name = f"{stem}_part{part_idx:0{width}d}{suffix}"
                        part_path = os.path.join(parent, part_name)
                        out = open(part_path, "w", encoding="utf-8-sig", newline="",
                                   buffering=WRITE_BUFFER)
                        out.write(header)
                        written = 1
                        parts.append(part_path)
                    out.write(line)
                    written += 1
                    if progress_callback and total > 0 and (ln % 10000 == 0 or ln == total or ln == 2):
                        progress_callback(ln / total)
            if out is not None:
                out.close()
        except OSError as ex:
            if out is not None:
                # 清理阶段：关闭失败不影响主流程。用 suppress 明确表达"有意忽略"，
                # 避免写成 except ... pass（会被门禁判为吞异常，且注释易与代码不符）。
                with contextlib.suppress(OSError):
                    out.close()
            return {"ok": False, "msg": str(ex), "parts": parts, "total": total}

        if progress_callback:
            progress_callback(1.0)

        return {
            "ok": True, "skipped": False,
            "msg": f"已分割为 {total_parts} 个文件",
            "parts": parts, "total": total, "total_parts": total_parts,
        }

    @staticmethod
    def split_by_date(src_path, date_column=None, granularity="day",
                      progress_callback=None):
        """
        按 CSV 中某一日期列的值，把数据拆成多个 CSV。

        - date_column: 列名(表头)或列索引(0-based)；None 时自动检测含"日期/date/time"的列
        - granularity: "day" / "month" / "year"
        - 输出文件名: <原名>_<日期键>.csv，UTF-8-SIG
        - 每片含表头
        """
        read_enc = EncodingDetector.get_read_encoding(src_path)
        parent = os.path.dirname(src_path)
        stem = Path(src_path).stem

        # 日期解析正则（v2.1.9: 加 ^$ 锥定避免 11 位手机号/订单号误判）
        date_patterns = [
            # YYYY-MM-DD / YYYY/MM/DD（整字段匹配）
            re.compile(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$"),
            # YYYYMMDD（整字段匹配，8 位数字）
            re.compile(r"^(\d{4})(\d{2})(\d{2})$"),
            # DD/MM/YYYY 或 MM/DD/YYYY（整字段匹配，二义性默认不启用）
            # re.compile(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$"),
        ]

        def parse_date(val):
            """从字符串中提取日期，返回 (year, month, day) 或 None"""
            val = str(val).strip()
            if not val:
                return None
            for pat in date_patterns:
                m = pat.match(val)
                if m:
                    groups = m.groups()
                    y, mo, d = int(groups[0]), int(groups[1]), int(groups[2])
                    if 1900 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31:
                        return (y, mo, d)
            return None

        def date_key(parsed, gran):
            y, mo, d = parsed
            if gran == "year":
                return f"{y:04d}"
            elif gran == "month":
                return f"{y:04d}-{mo:02d}"
            else:
                return f"{y:04d}-{mo:02d}-{d:02d}"

        # 先统计总行数用于进度计算（v2.4.2: 修复进度分母用循环中递增的 total_lines
        # 导致进度恒≥1.0被钳到0.99、进度条卡99%的问题）
        try:
            total = CsvSplitter.count_lines(src_path)
        except OSError:
            total = 0

        try:
            # 第一遍：读取表头 + 确定日期列索引
            with open(src_path, "r", encoding=read_enc, errors="replace", newline="") as f:
                reader = csv.reader(f)
                try:
                    header = next(reader)
                except StopIteration:
                    return {"ok": False, "msg": "文件为空", "parts": []}

                date_col_idx = None
                if date_column is not None:
                    if isinstance(date_column, int):
                        date_col_idx = date_column
                    else:
                        for i, h in enumerate(header):
                            if h.strip() == date_column.strip():
                                date_col_idx = i
                                break
                        if date_col_idx is None:
                            return {"ok": False,
                                    "msg": f"找不到列「{date_column}」",
                                    "parts": []}
                else:
                    # 自动检测
                    candidates = []
                    for i, h in enumerate(header):
                        hl = h.strip().lower()
                        if any(k in hl for k in ("日期", "date", "time", "时间")):
                            candidates.append(i)
                    if not candidates:
                        # 尝试扫描前 100 行找一个含日期的列
                        sample_rows = []
                        for _ in range(100):
                            try:
                                sample_rows.append(next(reader))
                            except StopIteration:
                                break
                        for ci in range(len(header)):
                            found = False
                            for row in sample_rows:
                                if ci < len(row) and parse_date(row[ci]):
                                    found = True
                                    break
                            if found:
                                candidates.append(ci)
                                break
                        if not candidates:
                            return {"ok": False,
                                    "msg": "无法自动检测日期列，请指定列名",
                                    "parts": []}
                    date_col_idx = candidates[0]

            # 第二遍：重开文件流式分割（#11修复：不依赖 seek+next 跳表头）
            file_handles = {}
            parts = []
            total_lines = 0
            try:
                with open(src_path, "r", encoding=read_enc, errors="replace", newline="") as f2:
                    reader = csv.reader(f2)
                    try:
                        header = next(reader)
                    except StopIteration:
                        return {"ok": False, "msg": "文件为空", "parts": []}

                    for ln, row in enumerate(reader, start=2):
                        total_lines += 1
                        date_val = row[date_col_idx] if date_col_idx < len(row) else ""
                        parsed = parse_date(date_val)
                        if parsed:
                            key = date_key(parsed, granularity)
                        else:
                            key = "未知日期"

                        if key not in file_handles:
                            out_name = f"{stem}_{key}.csv"
                            out_path = os.path.join(parent, out_name)
                            oh = open(out_path, "w", encoding="utf-8-sig", newline="",
                                      buffering=WRITE_BUFFER)
                            w = csv.writer(oh)
                            w.writerow(header)
                            file_handles[key] = (oh, w)
                            parts.append(out_path)

                        file_handles[key][1].writerow(row)

                        # v2.4.2: 进度分母用预统计的 total（行数），不再用循环中递增的 total_lines
                        if progress_callback and total > 0 and ln % 10000 == 0:
                            progress_callback(min(ln / total, 0.99))

                if progress_callback:
                    progress_callback(1.0)
            finally:
                # v2.4.2: 文件句柄关闭移入 finally，防异常时泄漏
                for oh, _w in file_handles.values():
                    with contextlib.suppress(OSError):
                        oh.close()

            if not parts:
                return {"ok": False, "msg": "未生成任何分片文件", "parts": []}

            return {
                "ok": True, "skipped": False,
                "msg": f"按日期分割为 {len(parts)} 个文件",
                "parts": parts, "total": total_lines,
                "total_parts": len(parts),
            }
        except OSError as ex:
            return {"ok": False, "msg": str(ex), "parts": []}
