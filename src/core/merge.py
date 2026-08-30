# -*- coding: utf-8 -*-
"""CSV 合并 — 删表头(F02) / 行尾加文件名_慢(F03) / 拷贝方式_快(F04)"""
import os
import csv
from pathlib import Path
from .encoding import EncodingDetector

WRITE_BUFFER = 8 * 1024 * 1024


class CsvMerger:
    """CSV 合并核心逻辑"""

    @staticmethod
    def merge_fast(file_paths, output_path, skip_headers=True, progress_callback=None):
        """
        F04 · 多 CSV 合并（拷贝方式_快）
        纯 UTF-8 / UTF-8-BOM 文件走二进制快路径；非 UTF-8 文件走文本转码流。
        - skip_headers=True: 只保留第一个文件的表头，其余文件跳过第一行
        - skip_headers=False: 保留所有文件内容（含表头）
        - 输出 UTF-8-SIG
        """
        if not file_paths:
            return {"ok": False, "msg": "没有文件", "output": None}

        total_size = sum(os.path.getsize(p) for p in file_paths if os.path.exists(p))
        processed = 0

        try:
            with open(output_path, "wb") as out:
                # 写 BOM
                out.write(b"\xef\xbb\xbf")
                processed += 3

                for idx, fp in enumerate(file_paths):
                    if not os.path.exists(fp):
                        continue
                    read_enc = EncodingDetector.get_read_encoding(fp)

                    if read_enc in ("utf-8", "utf-8-sig"):
                        # 纯 UTF-8 文件：二进制快路径
                        with open(fp, "rb") as src:
                            if skip_headers and idx > 0:
                                src.readline()
                            else:
                                bom = src.read(3)
                                if bom != b"\xef\xbb\xbf":
                                    out.write(bom)
                                    processed += 3
                            while True:
                                chunk = src.read(8 * 1024 * 1024)
                                if not chunk:
                                    break
                                out.write(chunk)
                                processed += len(chunk)
                                if progress_callback and total_size > 0:
                                    progress_callback(processed / total_size)
                    else:
                        # 非 UTF-8 文件：文本转码流
                        with open(fp, "r", encoding=read_enc, errors="replace", newline="") as src:
                            if skip_headers and idx > 0:
                                src.readline()
                            while True:
                                chunk = src.read(1024 * 1024)
                                if not chunk:
                                    break
                                data = chunk.encode("utf-8")
                                out.write(data)
                                processed += len(data)
                                if progress_callback and total_size > 0:
                                    progress_callback(processed / total_size)

            if progress_callback:
                progress_callback(1.0)

            return {
                "ok": True,
                "msg": f"已合并 {len(file_paths)} 个文件",
                "output": output_path,
            }
        except OSError as ex:
            return {"ok": False, "msg": str(ex), "output": None}

    @staticmethod
    def merge_remove_headers(file_paths, output_path, progress_callback=None):
        """
        F02 · 多 CSV 合并（删除文件头标注行）
        只保留第一个文件的表头，其余文件表头删除。
        - 使用 csv.writer 保证 CSV 转义正确
        - 输出 UTF-8-SIG
        """
        if not file_paths:
            return {"ok": False, "msg": "没有文件", "output": None}

        total_size = sum(os.path.getsize(p) for p in file_paths if os.path.exists(p))
        processed = 0

        try:
            with open(output_path, "w", encoding="utf-8-sig", newline="",
                      buffering=WRITE_BUFFER) as out:
                writer = csv.writer(out)
                for idx, fp in enumerate(file_paths):
                    if not os.path.exists(fp):
                        continue
                    read_enc = EncodingDetector.get_read_encoding(fp)
                    with open(fp, "r", encoding=read_enc, errors="replace", newline="") as src:
                        reader = csv.reader(src)
                        try:
                            header = next(reader)
                        except StopIteration:
                            continue
                        if idx == 0:
                            writer.writerow(header)
                        # 写数据行
                        for row in reader:
                            writer.writerow(row)
                    processed += os.path.getsize(fp)
                    if progress_callback and total_size > 0:
                        progress_callback(processed / total_size)

            if progress_callback:
                progress_callback(1.0)

            return {
                "ok": True,
                "msg": f"已合并 {len(file_paths)} 个文件（删除重复表头）",
                "output": output_path,
            }
        except OSError as ex:
            return {"ok": False, "msg": str(ex), "output": None}

    @staticmethod
    def merge_with_filename(file_paths, output_path, col_name="来源文件",
                            progress_callback=None):
        """
        F03 · 多 CSV 合并（行尾增加文件名_慢）
        合并 CSV，并在每一行末尾追加「来源文件名」列。
        - 使用 csv.writer 保证 CSV 转义正确（文件名含逗号也安全）
        - 输出 UTF-8-SIG
        """
        if not file_paths:
            return {"ok": False, "msg": "没有文件", "output": None}

        total_size = sum(os.path.getsize(p) for p in file_paths if os.path.exists(p))
        processed = 0

        try:
            with open(output_path, "w", encoding="utf-8-sig", newline="",
                      buffering=WRITE_BUFFER) as out:
                writer = csv.writer(out)
                for idx, fp in enumerate(file_paths):
                    if not os.path.exists(fp):
                        continue
                    read_enc = EncodingDetector.get_read_encoding(fp)
                    fname = os.path.basename(fp)
                    with open(fp, "r", encoding=read_enc, errors="replace", newline="") as src:
                        reader = csv.reader(src)
                        try:
                            header = next(reader)
                        except StopIteration:
                            continue
                        if idx == 0:
                            writer.writerow(header + [col_name])
                        for row in reader:
                            writer.writerow(row + [fname])
                    processed += os.path.getsize(fp)
                    if progress_callback and total_size > 0:
                        progress_callback(min(processed / total_size, 1.0))

            if progress_callback:
                progress_callback(1.0)

            return {
                "ok": True,
                "msg": f"已合并 {len(file_paths)} 个文件（含来源文件名列）",
                "output": output_path,
            }
        except OSError as ex:
            return {"ok": False, "msg": str(ex), "output": None}
