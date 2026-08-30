# -*- coding: utf-8 -*-
"""通用工具函数"""


def format_elapsed(seconds):
    """将秒数格式化为人类可读的耗时字符串"""
    if seconds < 1:
        return f"{seconds * 1000:.0f} 毫秒"
    elif seconds < 60:
        return f"{seconds:.2f} 秒"
    elif seconds < 3600:
        m = int(seconds // 60)
        s = seconds % 60
        return f"{m}分{s:.1f}秒"
    else:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h}时{m}分{s:.0f}秒"


def format_size(size_bytes):
    """格式化文件大小"""
    if size_bytes == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB"]
    u = "B"
    for u in units:
        if abs(size_bytes) < 1024 or u == "GB":
            break
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} {u}"
