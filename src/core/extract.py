# -*- coding: utf-8 -*-
"""CSV 提取 — 按关键字筛选行 (F08)"""
import os
import re
import csv
from pathlib import Path
from .encoding import EncodingDetector

WRITE_BUFFER = 8 * 1024 * 1024


class CsvExtractor:
    """CSV 关键字提取核心逻辑"""

    @staticmethod
    def extract_by_keyword(src_path, keywords, output_path=None,
                           match_mode="contains", search_columns=None,
                           case_sensitive=False, output_matched=True,
                           output_unmatched=False, progress_callback=None):
        """
        F08 · 从 CSV 中筛选包含指定关键字的行。

        - keywords: 关键字列表（多个关键字为 OR 关系）
        - match_mode: "contains" / "equals" / "startswith" / "endswith" / "regex"
        - search_columns: None=所有列 / 列名列表 / 列索引列表
        - case_sensitive: 是否区分大小写
        - output_matched: 输出匹配行
        - output_unmatched: 输出不匹配行
        - 返回 dict: ok, msg, matched, unmatched, total_lines, matched_count
        """
        if not keywords:
            return {"ok": False, "msg": "请提供至少一个关键字"}

        if not output_matched and not output_unmatched:
            output_matched = True  # 默认至少输出匹配行

        read_enc = EncodingDetector.get_read_encoding(src_path)
        parent = os.path.dirname(src_path)
        stem = Path(src_path).stem

        # 默认输出路径
        if output_path is None:
            output_path = os.path.join(parent, f"{stem}_提取结果.csv")

        unmatched_path = None
        if output_unmatched:
            unmatched_path = os.path.join(parent, f"{stem}_未匹配.csv")

        # 预处理关键字
        if match_mode == "regex":
            flags = 0 if case_sensitive else re.IGNORECASE
            kw_list = [re.compile(k, flags) for k in keywords]
        elif not case_sensitive:
            kw_list = [k.lower() for k in keywords]
        else:
            kw_list = list(keywords)

        def match_value(val):
            if match_mode == "regex":
                for pat in kw_list:
                    if pat.search(val):
                        return True
                return False
            if not case_sensitive:
                val = val.lower()
            for kw in kw_list:
                if match_mode == "contains":
                    if kw in val:
                        return True
                elif match_mode == "equals":
                    if kw == val:
                        return True
                elif match_mode == "startswith":
                    if val.startswith(kw):
                        return True
                elif match_mode == "endswith":
                    if val.endswith(kw):
                        return True
            return False

        try:
            # 先统计总行数用于进度计算
            from .split import CsvSplitter
            total = CsvSplitter.count_lines(src_path)
            if total == 0:
                return {"ok": False, "msg": "文件为空"}

            total_lines = 0
            matched_count = 0
            out_matched = None
            out_unmatched = None

            try:
                with open(src_path, "r", encoding=read_enc, errors="replace", newline="") as f:
                    reader = csv.reader(f)
                    try:
                        header = next(reader)
                    except StopIteration:
                        return {"ok": False, "msg": "文件为空"}

                    # 确定搜索列索引
                    search_indices = None
                    if search_columns is not None:
                        search_indices = []
                        for sc in search_columns:
                            if isinstance(sc, int):
                                search_indices.append(sc)
                            else:
                                for i, h in enumerate(header):
                                    if h.strip() == sc.strip():
                                        search_indices.append(i)
                                        break
                        if not search_indices:
                            return {"ok": False,
                                    "msg": f"找不到指定列: {search_columns}"}

                    if output_matched:
                        out_matched = open(output_path, "w", encoding="utf-8-sig",
                                           newline="", buffering=WRITE_BUFFER)
                        mw = csv.writer(out_matched)
                        mw.writerow(header)
                    if output_unmatched and unmatched_path:
                        out_unmatched = open(unmatched_path, "w", encoding="utf-8-sig",
                                             newline="", buffering=WRITE_BUFFER)
                        uw = csv.writer(out_unmatched)
                        uw.writerow(header)

                    for row in reader:
                        total_lines += 1
                        # 确定要搜索的列
                        if search_indices:
                            vals = [row[i] if i < len(row) else "" for i in search_indices]
                        else:
                            vals = row

                        is_match = any(match_value(v) for v in vals)

                        if is_match:
                            matched_count += 1
                            if out_matched:
                                mw.writerow(row)
                        else:
                            if out_unmatched:
                                uw.writerow(row)

                        if progress_callback and total > 0 and total_lines % 10000 == 0:
                            progress_callback(total_lines / total)
            finally:
                # 确保文件句柄在异常时也被关闭
                if out_matched:
                    out_matched.close()
                if out_unmatched:
                    out_unmatched.close()

            if progress_callback:
                progress_callback(1.0)

            parts = [output_path] if output_matched else []
            if output_unmatched and unmatched_path:
                parts.append(unmatched_path)

            return {
                "ok": True,
                "msg": f"提取完成: 共 {total_lines} 行, 匹配 {matched_count} 行",
                "matched": output_path if output_matched else None,
                "unmatched": unmatched_path if output_unmatched else None,
                "total_lines": total_lines,
                "matched_count": matched_count,
                "parts": parts,
            }
        except OSError as ex:
            return {"ok": False, "msg": str(ex)}
