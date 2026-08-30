# -*- coding: utf-8 -*-
"""编码转换 — CSV/TXT -> UTF-8-BOM，流式读写 O(1) 内存"""
import os
import shutil
import tempfile
from .encoding import EncodingDetector

READ_CHUNK = 8 * 1024 * 1024  # 8 MB


class FileConverter:
    """编码转换核心逻辑"""

    @staticmethod
    def convert(src_path, dst_path, progress_callback=None):
        """
        将源文件转换为 UTF-8-BOM 编码。
        - 已有 BOM: 直接二进制复制
        - UTF-8 无 BOM: 头部添加 BOM 后复制
        - GBK 系列: 文本级转码为 UTF-8-SIG
        - 未知: 返回失败
        """
        encoding, has_bom = EncodingDetector.detect(src_path)
        try:
            file_size = os.path.getsize(src_path)
        except OSError:
            file_size = 1

        if has_bom:
            copied = 0
            with open(src_path, "rb") as src, open(dst_path, "wb") as dst:
                while True:
                    chunk = src.read(READ_CHUNK)
                    if not chunk:
                        break
                    dst.write(chunk)
                    copied += len(chunk)
                    if progress_callback and file_size > 0:
                        progress_callback(copied / file_size)
            return {"ok": True, "msg": "已有 BOM，已直接复制"}

        if encoding == "utf-8":
            copied = 0
            with open(src_path, "rb") as src, open(dst_path, "wb") as dst:
                dst.write(b"\xef\xbb\xbf")
                while True:
                    chunk = src.read(READ_CHUNK)
                    if not chunk:
                        break
                    dst.write(chunk)
                    copied += len(chunk)
                    if progress_callback and file_size > 0:
                        progress_callback(copied / file_size)
            return {"ok": True, "msg": "已添加 UTF-8 BOM"}

        if encoding in ("gbk", "gb18030", "gb2312"):
            # v2.4.2: 修复进度计算——文本模式 src.tell() 返回值与字节大小不在同一单位
            # （文本模式 tell() 返回的是不透明的 cookie 或字符偏移，不是已读字节数），
            # 导致 pos/file_size 可能 >1 或严重偏小。改为累加已写字节数作为分子。
            written_bytes = 0
            with open(src_path, "r", encoding=encoding, errors="replace") as src, \
                 open(dst_path, "w", encoding="utf-8-sig", newline="") as dst:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)
                    written_bytes += len(chunk.encode("utf-8"))
                    if progress_callback and file_size > 0:
                        progress_callback(min(written_bytes / file_size, 1.0))
            return {"ok": True, "msg": f"已从 {encoding.upper()} 转为 UTF-8+BOM"}
        return {"ok": False, "msg": f"未知编码: {encoding}"}

    @staticmethod
    def analyze(filepath):
        """分析文件编码和大小，返回文件信息字典"""
        encoding, has_bom = EncodingDetector.detect(filepath)
        try:
            size_bytes = os.path.getsize(filepath)
        except OSError:
            size_bytes = 0
        preview = ""
        try:
            enc = encoding if encoding != "unknown" else "utf-8"
            with open(filepath, "r", encoding=enc, errors="replace") as f:
                preview = f.readline().strip()[:60]
        except Exception:
            preview = ""
        name = os.path.basename(filepath)
        need_convert = not has_bom
        return {
            "path": filepath, "name": name,
            "size": size_bytes, "size_str": FileConverter._format_size(size_bytes),
            "encoding": encoding, "has_bom": has_bom,
            "preview": preview, "need": need_convert,
        }

    @staticmethod
    def _format_size(size_bytes):
        if size_bytes == 0:
            return "0 B"
        units = ["B", "KB", "MB", "GB"]
        u = "B"
        for u in units:
            if abs(size_bytes) < 1024 or u == "GB":
                break
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} {u}"

    @staticmethod
    def safe_overwrite(src_tmp, dst):
        """安全覆盖：临时文件 -> 目标文件"""
        try:
            shutil.move(src_tmp, dst)
            return True
        except OSError:
            return False

    @staticmethod
    def make_temp(dst_dir, suffix):
        """创建临时文件"""
        try:
            fd, tmp_path = tempfile.mkstemp(suffix=suffix, dir=dst_dir)
            os.close(fd)
            return tmp_path
        except OSError:
            return None
