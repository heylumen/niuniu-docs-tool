# -*- coding: utf-8 -*-
"""编码检测引擎 — 复用 v1.x 的 EncodingDetector 逻辑"""
import os
import contextlib

READ_CHUNK = 8 * 1024 * 1024  # 8 MB


class EncodingDetector:
    """自动检测 CSV/TXT 文件编码"""

    @staticmethod
    def detect(filepath):
        """
        返回 (encoding_str, has_bom_bool)
        优先级: BOM -> UTF-8 -> GB18030/GBK/GB2312 -> unknown

        v2.1.9: 增强为全文件校验（分块 decode 累进），避免前 64KB 合法 UTF-8
        但尾部混 GBK 的拼接文件被误判（#9）。
        """
        try:
            file_size = os.path.getsize(filepath)
        except (OSError, IOError):
            return "unknown", False

        try:
            with open(filepath, "rb") as f:
                # BOM 检测
                head = f.read(3)
                if head[:3] == b"\xef\xbb\xbf":
                    return "utf-8-sig", True

                # 全文件 UTF-8 校验
                f.seek(0)
                is_utf8 = True
                while True:
                    chunk = f.read(READ_CHUNK)
                    if not chunk:
                        break
                    try:
                        chunk.decode("utf-8")
                    except (UnicodeDecodeError, ValueError):
                        is_utf8 = False
                        break
                if is_utf8:
                    return "utf-8", False

                # 全文件 GB18030 校验（gb18030 是 gbk/gb2312 的超集，
                # 原逐个校验最多 3 轮全文件扫描，合并为 1 轮即可判定）
                f.seek(0)
                is_gb = True
                while True:
                    chunk = f.read(READ_CHUNK)
                    if not chunk:
                        break
                    try:
                        chunk.decode("gb18030")
                    except (UnicodeDecodeError, ValueError):
                        is_gb = False
                        break
                if is_gb:
                    return "gb18030", False

                return "unknown", False
        except (OSError, IOError):
            return "unknown", False

    @staticmethod
    def get_read_encoding(filepath):
        """返回用于读取文件的编码名（未知编码回退 utf-8）"""
        enc, _ = EncodingDetector.detect(filepath)
        if enc in ("utf-8", "utf-8-sig", "gb18030", "gbk", "gb2312"):
            return enc
        return "utf-8"
