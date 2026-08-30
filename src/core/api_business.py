#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
牛牛文档工具 — 业务逻辑 Mixin（9 个 exec_* 功能及其 worker）

v2.3.0 拆分说明（原 app_webview.py 1169 行 > 800 行打包链阈值）：
  本模块承载 9 个业务功能（编码转换 / 按行拆分 / 按日期拆分 / CSV 合并 /
  工作簿合并 / 工作表合并 / 关键字提取 / 工作簿拆分 / 超宽表拆分）及其
  后台 worker 线程；窗口控制、文件管理、进度与状态回调留在 app_webview.py。

为什么用 Mixin 而不是独立类：
  pywebview 的 js_api 通过 dir(obj) 收集可暴露方法（webview/util.py:190），
  dir() 包含继承成员，因此 Api(BusinessApiMixin) 组合后，本模块的 public
  方法（exec_*）仍会被正常暴露给 JS，前端调用方式零改动。
  已实测验证：继承的 Mixin 方法被暴露、私有方法（_ 开头）被正确过滤。

依赖约定（Mixin 由宿主类 Api 提供以下成员）：
  属性：file_list / is_busy / _open_folder_after_done
  方法：_log / _result / _set_busy / _make_progress_cb / _on_done
"""
import os
import sys
import json
import time
import shutil
import tempfile
import threading
from pathlib import Path

# 确保能导入 core 模块（开发模式与 PyInstaller 解包模式均可用）
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from core.encoding import EncodingDetector
from core.convert import FileConverter
from core.split import CsvSplitter
from core.merge import CsvMerger
from core.extract import CsvExtractor
from core.sheet import ExcelWorker, HAVE_OPENPYXL


class BusinessApiMixin:
    """业务功能 Mixin：由 app_webview.Api 继承，不单独实例化。"""

    # ================================================================
    # 功能 1: 编码转换
    # ================================================================
    def exec_convert(self, params_json):
        """执行编码转换"""
        if self.is_busy:
            return self._result(False, "正在处理中，请等待完成")
        try:
            params = json.loads(params_json) if isinstance(params_json, str) else params_json
        except (json.JSONDecodeError, TypeError):
            params = {}

        target_enc = params.get("encoding", "auto")
        copy_mode = params.get("copy_mode", True)
        out_dir = params.get("out_dir", "").strip()
        self._open_folder_after_done = params.get("open_folder", False)

        if not self.file_list:
            return self._result(False, "请先添加文件")

        self._set_busy(True)
        threading.Thread(target=self._convert_worker,
                         args=(list(self.file_list), target_enc, copy_mode, out_dir),
                         daemon=True).start()
        return self._result(True, "开始转换")

    def _convert_worker(self, files, target_enc, copy_mode, out_dir):
        start_time = time.perf_counter()
        results = []
        total = len(files)

        for i, finfo in enumerate(files):
            src = finfo["path"]
            suffix = Path(src).suffix
            if copy_mode:
                parent = out_dir if out_dir else os.path.dirname(src)
                stem = Path(src).stem
                dst = os.path.join(parent, f"{stem}_已转换{suffix}")
            else:
                dst_dir = os.path.dirname(src)
                try:
                    fd, tmp_path = tempfile.mkstemp(suffix=suffix, dir=dst_dir)
                    os.close(fd)
                except OSError:
                    tmp_path = src + ".tmp"
                dst = tmp_path

            callback = lambda r, fi=i, fn=finfo["name"]: self._make_progress_cb(
                total, "转换", fn)(r / total + fi / total)

            try:
                if target_enc in ("auto", "utf-8-bom"):
                    result = FileConverter.convert(src, dst, callback)
                elif target_enc == "utf-8":
                    result = self._convert_to_encoding(src, dst, "utf-8", callback)
                elif target_enc == "gbk":
                    result = self._convert_to_encoding(src, dst, "gbk", callback)
                else:
                    result = FileConverter.convert(src, dst, callback)

                result["file"] = finfo
                result["dst"] = dst

                if result["ok"] and not copy_mode:
                    try:
                        shutil.move(dst, src)
                        result["dst"] = src
                    except OSError as ex:
                        self._log(f"文件移动失败: {ex}")
                results.append(result)
            except Exception as ex:
                results.append({"ok": False, "msg": str(ex), "file": finfo, "dst": dst})

        elapsed = time.perf_counter() - start_time
        self._on_done(results, "转换", elapsed)

    def _convert_to_encoding(self, src, dst, target_encoding, progress_callback=None):
        """将文件转换为指定编码"""
        read_enc = EncodingDetector.get_read_encoding(src)
        try:
            file_size = os.path.getsize(src)
        except OSError:
            file_size = 1

        if read_enc == target_encoding or (read_enc == "utf-8-sig" and target_encoding == "utf-8"):
            try:
                shutil.copy2(src, dst)
                if progress_callback:
                    progress_callback(1.0)
                return {"ok": True, "msg": f"已是 {target_encoding.upper()} 编码"}
            except OSError as ex:
                return {"ok": False, "msg": str(ex)}

        try:
            with open(src, "r", encoding=read_enc, errors="replace") as fin, \
                 open(dst, "w", encoding=target_encoding, errors="replace", newline="") as fout:
                read_bytes = 0
                while True:
                    chunk = fin.read(1024 * 1024)
                    if not chunk:
                        break
                    fout.write(chunk)
                    read_bytes += len(chunk.encode(read_enc, errors="replace"))
                    if progress_callback and file_size > 0:
                        progress_callback(min(read_bytes / file_size, 1.0))
            if progress_callback:
                progress_callback(1.0)
            return {"ok": True, "msg": f"已转为 {target_encoding.upper()}"}
        except OSError as ex:
            return {"ok": False, "msg": str(ex)}

    # ================================================================
    # 功能 2: 按行数分割
    # ================================================================
    def exec_split_rows(self, params_json):
        if self.is_busy:
            return self._result(False, "正在处理中")
        try:
            params = json.loads(params_json) if isinstance(params_json, str) else params_json
        except (json.JSONDecodeError, TypeError):
            params = {}
        # #13修复：int() 无糊底
        try:
            max_rows = int(params.get("max_rows", "1000000"))
        except (ValueError, TypeError):
            max_rows = 1000000
        out_dir = params.get("out_dir", "").strip()
        target_enc = params.get("encoding", "utf-8")
        self._open_folder_after_done = params.get("open_folder", False)
        if not self.file_list:
            return self._result(False, "请先添加文件")
        self._set_busy(True)
        threading.Thread(target=self._split_rows_worker,
                         args=(list(self.file_list), max_rows, out_dir, target_enc),
                         daemon=True).start()
        return self._result(True, "开始分割")

    def _split_rows_worker(self, files, max_rows, out_dir, target_enc):
        start_time = time.perf_counter()
        results = []
        total = len(files)
        for i, finfo in enumerate(files):
            src = finfo["path"]
            work_src = src
            if out_dir:
                src_name = os.path.basename(src)
                work_src = os.path.join(out_dir, src_name)
                if not os.path.exists(work_src):
                    try:
                        shutil.copy2(src, work_src)
                    except OSError:
                        work_src = src
            cb = lambda r, fi=i, fn=finfo["name"]: self._make_progress_cb(total, "分割", fn)(
                (fi + r) / total)
            try:
                res = CsvSplitter.split_by_rows(work_src, max_rows=max_rows, progress_callback=cb)
                if res.get("ok") and target_enc == "gbk" and res.get("parts"):
                    for part_path in res["parts"]:
                        self._convert_file_encoding(part_path, "gbk")
            except Exception as ex:
                res = {"ok": False, "msg": str(ex), "parts": [], "file": finfo}
            res["file"] = finfo
            results.append(res)
        elapsed = time.perf_counter() - start_time
        self._on_done(results, "分割", elapsed)

    # ================================================================
    # 功能 3: 按日期分割
    # ================================================================
    def exec_split_date(self, params_json):
        if self.is_busy:
            return self._result(False, "正在处理中")
        try:
            params = json.loads(params_json) if isinstance(params_json, str) else params_json
        except (json.JSONDecodeError, TypeError):
            params = {}
        date_col = params.get("date_col", "").strip() or None
        granularity = params.get("granularity", "day")
        out_dir = params.get("out_dir", "").strip()
        target_enc = params.get("encoding", "utf-8")
        self._open_folder_after_done = params.get("open_folder", False)
        if not self.file_list:
            return self._result(False, "请先添加文件")
        self._set_busy(True)
        threading.Thread(target=self._split_date_worker,
                         args=(list(self.file_list), date_col, granularity, out_dir, target_enc),
                         daemon=True).start()
        return self._result(True, "开始分割")

    def _split_date_worker(self, files, date_col, granularity, out_dir, target_enc):
        start_time = time.perf_counter()
        results = []
        total = len(files)
        for i, finfo in enumerate(files):
            src = finfo["path"]
            work_src = src
            if out_dir:
                src_name = os.path.basename(src)
                work_src = os.path.join(out_dir, src_name)
                if not os.path.exists(work_src):
                    try:
                        shutil.copy2(src, work_src)
                    except OSError:
                        work_src = src
            cb = lambda r, fi=i, fn=finfo["name"]: self._make_progress_cb(total, "分割", fn)(
                (fi + r) / total)
            try:
                res = CsvSplitter.split_by_date(work_src, date_column=date_col,
                                                granularity=granularity, progress_callback=cb)
                if res.get("ok") and target_enc == "gbk" and res.get("parts"):
                    for part_path in res["parts"]:
                        self._convert_file_encoding(part_path, "gbk")
            except Exception as ex:
                res = {"ok": False, "msg": str(ex), "parts": [], "file": finfo}
            res["file"] = finfo
            results.append(res)
        elapsed = time.perf_counter() - start_time
        self._on_done(results, "分割", elapsed)

    # ================================================================
    # 功能 4: CSV 合并
    # ================================================================
    def exec_csv_merge(self, params_json):
        if self.is_busy:
            return self._result(False, "正在处理中")
        try:
            params = json.loads(params_json) if isinstance(params_json, str) else params_json
        except (json.JSONDecodeError, TypeError):
            params = {}
        mode = params.get("mode", "fast")
        output_name = params.get("output_name", "合并结果.csv").strip()
        if not output_name:
            output_name = "合并结果.csv"
        out_dir = params.get("out_dir", "").strip()
        sort_mode = params.get("sort", "name")
        self._open_folder_after_done = params.get("open_folder", False)

        csv_files = [f for f in self.file_list
                     if Path(f["path"]).suffix.lower() in (".csv", ".txt")]
        if len(csv_files) < 2:
            return self._result(False, "合并至少需要 2 个 CSV/TXT 文件")
        self._set_busy(True)
        threading.Thread(target=self._csv_merge_worker,
                         args=(csv_files, mode, output_name, out_dir, sort_mode),
                         daemon=True).start()
        return self._result(True, "开始合并")

    def _csv_merge_worker(self, files, mode, output_name, out_dir, sort_mode):
        start_time = time.perf_counter()
        paths = [f["path"] for f in files]
        first_file = paths[0]
        parent = out_dir if out_dir else os.path.dirname(first_file)
        output_path = os.path.join(parent, output_name)

        if sort_mode == "name":
            paths.sort(key=lambda p: os.path.basename(p).lower())
        elif sort_mode == "mtime":
            paths.sort(key=lambda p: os.path.getmtime(p))

        cb = lambda r: self._make_progress_cb(1, "合并", files[0]["name"])(r)
        try:
            if mode == "fast":
                res = CsvMerger.merge_fast(paths, output_path, skip_headers=True, progress_callback=cb)
            elif mode == "remove":
                res = CsvMerger.merge_remove_headers(paths, output_path, progress_callback=cb)
            else:
                res = CsvMerger.merge_with_filename(paths, output_path, col_name="来源文件", progress_callback=cb)
        except Exception as ex:
            res = {"ok": False, "msg": str(ex), "output": None}

        elapsed = time.perf_counter() - start_time
        self._on_done([res], "合并", elapsed)

    # ================================================================
    # 功能 5: 多工作簿合并
    # ================================================================
    def exec_wb_merge(self, params_json):
        if self.is_busy:
            return self._result(False, "正在处理中")
        if not HAVE_OPENPYXL:
            return self._result(False, "缺少 openpyxl 库，无法处理 Excel 文件")
        try:
            params = json.loads(params_json) if isinstance(params_json, str) else params_json
        except (json.JSONDecodeError, TypeError):
            params = {}
        mode = params.get("mode", "sheet_name")
        output_name = params.get("output_name", "合并工作簿.xlsx").strip()
        if not output_name:
            output_name = "合并工作簿.xlsx"
        out_dir = params.get("out_dir", "").strip()
        self._open_folder_after_done = params.get("open_folder", False)

        xlsx_files = [f for f in self.file_list
                      if Path(f["path"]).suffix.lower() in (".xlsx", ".xls")]
        if len(xlsx_files) < 2:
            return self._result(False, "多工作簿合并至少需要 2 个 Excel 文件")
        self._set_busy(True)
        threading.Thread(target=self._wb_merge_worker,
                         args=(xlsx_files, mode, output_name, out_dir),
                         daemon=True).start()
        return self._result(True, "开始合并")

    def _wb_merge_worker(self, files, mode, output_name, out_dir):
        start_time = time.perf_counter()
        first_src = files[0]["path"]
        parent = out_dir if out_dir else os.path.dirname(first_src)
        output_path = os.path.join(parent, output_name)
        paths = [f["path"] for f in files]
        all_sheets = (mode != "filename")
        cb = lambda r: self._make_progress_cb(1, "合并", files[0]["name"])(r)
        try:
            res = ExcelWorker.merge_workbooks(paths, output_path,
                                               all_sheets=all_sheets, progress_callback=cb)
        except Exception as ex:
            res = {"ok": False, "msg": str(ex), "output": None}
        elapsed = time.perf_counter() - start_time
        self._on_done([res], "合并", elapsed)

    # ================================================================
    # 功能 6: 单簿内表合并
    # ================================================================
    def exec_sheet_merge(self, params_json):
        if self.is_busy:
            return self._result(False, "正在处理中")
        if not HAVE_OPENPYXL:
            return self._result(False, "缺少 openpyxl 库")
        try:
            params = json.loads(params_json) if isinstance(params_json, str) else params_json
        except (json.JSONDecodeError, TypeError):
            params = {}
        header_strategy = params.get("header_strategy", "first")
        out_dir = params.get("out_dir", "").strip()
        add_source = (header_strategy == "each")
        self._open_folder_after_done = params.get("open_folder", False)

        xlsx_files = [f for f in self.file_list
                      if Path(f["path"]).suffix.lower() in (".xlsx", ".xls")]
        if not xlsx_files:
            return self._result(False, "请添加 .xlsx Excel 文件")
        self._set_busy(True)
        threading.Thread(target=self._sheet_merge_worker,
                         args=(xlsx_files, add_source, out_dir),
                         daemon=True).start()
        return self._result(True, "开始合并")

    def _sheet_merge_worker(self, files, add_source, out_dir):
        start_time = time.perf_counter()
        total = len(files)
        results = []
        for i, finfo in enumerate(files):
            src = finfo["path"]
            parent = out_dir if out_dir else os.path.dirname(src)
            stem = Path(src).stem
            output_path = os.path.join(parent, f"{stem}_合并.xlsx")
            cb = lambda r, fn=finfo["name"]: self._make_progress_cb(total, "处理", fn)(
                (i + r) / total)
            try:
                res = ExcelWorker.merge_sheets_in_workbook(
                    src, output_path=output_path,
                    add_source_column=add_source, progress_callback=cb)
            except Exception as ex:
                res = {"ok": False, "msg": str(ex), "output": None}
            res["file"] = finfo
            results.append(res)
        elapsed = time.perf_counter() - start_time
        self._on_done(results, "合并", elapsed)

    # ================================================================
    # 功能 7: 关键字提取
    # ================================================================
    def exec_keyword(self, params_json):
        if self.is_busy:
            return self._result(False, "正在处理中")
        try:
            params = json.loads(params_json) if isinstance(params_json, str) else params_json
        except (json.JSONDecodeError, TypeError):
            params = {}
        kw_str = params.get("keyword", "").strip()
        if not kw_str:
            return self._result(False, "请输入关键字")
        keywords = [k.strip() for k in kw_str.split(",") if k.strip()]
        match_mode = params.get("match_mode", "contains")
        col_name = params.get("col_name", "").strip()
        out_dir = params.get("out_dir", "").strip()
        search_columns = None
        if col_name:
            search_columns = [col_name]
        self._open_folder_after_done = params.get("open_folder", False)

        csv_files = [f for f in self.file_list
                     if Path(f["path"]).suffix.lower() in (".csv", ".txt")]
        if not csv_files:
            return self._result(False, "请添加 CSV/TXT 文件")
        self._set_busy(True)
        threading.Thread(target=self._keyword_worker,
                         args=(csv_files, keywords, match_mode, search_columns, out_dir),
                         daemon=True).start()
        return self._result(True, "开始提取")

    def _keyword_worker(self, files, keywords, match_mode, search_columns, out_dir):
        start_time = time.perf_counter()
        total = len(files)
        results = []
        for i, finfo in enumerate(files):
            src = finfo["path"]
            parent = out_dir if out_dir else os.path.dirname(src)
            stem = Path(src).stem
            output_path = os.path.join(parent, f"{stem}_提取结果.csv")
            cb = lambda r, fn=finfo["name"]: self._make_progress_cb(total, "提取", fn)(
                (i + r) / total)
            try:
                res = CsvExtractor.extract_by_keyword(
                    src, keywords, output_path=output_path,
                    match_mode=match_mode, search_columns=search_columns,
                    progress_callback=cb)
            except Exception as ex:
                res = {"ok": False, "msg": str(ex)}
            res["file"] = finfo
            results.append(res)
        elapsed = time.perf_counter() - start_time
        self._on_done(results, "提取", elapsed)

    # ================================================================
    # 功能 8: 工作簿拆分为 CSV
    # ================================================================
    def exec_wb_split(self, params_json):
        if self.is_busy:
            return self._result(False, "正在处理中")
        if not HAVE_OPENPYXL:
            return self._result(False, "缺少 openpyxl 库")
        try:
            params = json.loads(params_json) if isinstance(params_json, str) else params_json
        except (json.JSONDecodeError, TypeError):
            params = {}
        out_dir = params.get("out_dir", "").strip()
        target_enc = params.get("encoding", "utf-8")
        self._open_folder_after_done = params.get("open_folder", False)

        xlsx_files = [f for f in self.file_list
                      if Path(f["path"]).suffix.lower() in (".xlsx", ".xls")]
        if not xlsx_files:
            return self._result(False, "请添加 .xlsx Excel 文件")
        self._set_busy(True)
        threading.Thread(target=self._wb_split_worker,
                         args=(xlsx_files, out_dir, target_enc),
                         daemon=True).start()
        return self._result(True, "开始拆分")

    def _wb_split_worker(self, files, out_dir, target_enc):
        start_time = time.perf_counter()
        total = len(files)
        results = []
        for i, finfo in enumerate(files):
            src = finfo["path"]
            work_src = src
            if out_dir:
                src_name = os.path.basename(src)
                work_src = os.path.join(out_dir, src_name)
                if not os.path.exists(work_src):
                    try:
                        shutil.copy2(src, work_src)
                    except OSError:
                        work_src = src
            cb = lambda r, fn=finfo["name"]: self._make_progress_cb(total, "拆分", fn)(
                (i + r) / total)
            try:
                res = ExcelWorker.workbook_to_csvs(work_src, progress_callback=cb)
                if res.get("ok") and target_enc == "gbk" and res.get("parts"):
                    for part_path in res["parts"]:
                        self._convert_file_encoding(part_path, "gbk")
            except Exception as ex:
                res = {"ok": False, "msg": str(ex), "parts": []}
            res["file"] = finfo
            results.append(res)
        elapsed = time.perf_counter() - start_time
        self._on_done(results, "拆分", elapsed)

    # ================================================================
    # 功能 9: 超宽列拆分
    # ================================================================
    def exec_wide_split(self, params_json):
        if self.is_busy:
            return self._result(False, "正在处理中")
        if not HAVE_OPENPYXL:
            return self._result(False, "缺少 openpyxl 库")
        try:
            params = json.loads(params_json) if isinstance(params_json, str) else params_json
        except (json.JSONDecodeError, TypeError):
            params = {}
        # #13修复：int() 无糊底
        try:
            cols = int(params.get("cols", "50"))
        except (ValueError, TypeError):
            cols = 50
        if cols < 1:
            cols = 50
        out_dir = params.get("out_dir", "").strip()
        self._open_folder_after_done = params.get("open_folder", False)

        xlsx_files = [f for f in self.file_list
                      if Path(f["path"]).suffix.lower() in (".xlsx", ".xls")]
        if not xlsx_files:
            return self._result(False, "请添加 .xlsx Excel 文件")
        self._set_busy(True)
        threading.Thread(target=self._wide_split_worker,
                         args=(xlsx_files, cols, out_dir),
                         daemon=True).start()
        return self._result(True, "开始拆分")

    def _wide_split_worker(self, files, cols, out_dir):
        start_time = time.perf_counter()
        total = len(files)
        results = []
        for i, finfo in enumerate(files):
            src = finfo["path"]
            work_src = src
            if out_dir:
                src_name = os.path.basename(src)
                work_src = os.path.join(out_dir, src_name)
                if not os.path.exists(work_src):
                    try:
                        shutil.copy2(src, work_src)
                    except OSError:
                        work_src = src
            cb = lambda r, fn=finfo["name"]: self._make_progress_cb(total, "拆分", fn)(
                (i + r) / total)
            try:
                res = ExcelWorker.split_wide_worksheet(work_src, threshold=cols, progress_callback=cb)
            except Exception as ex:
                res = {"ok": False, "msg": str(ex), "output": None}
            res["file"] = finfo
            results.append(res)
        elapsed = time.perf_counter() - start_time
        self._on_done(results, "拆分", elapsed)

    # ================================================================
    # 通用编码转换（原地）
    # ================================================================
    def _convert_file_encoding(self, filepath, target_encoding):
        """将文件原地转换为目标编码"""
        read_enc = EncodingDetector.get_read_encoding(filepath)
        if read_enc == target_encoding:
            return
        try:
            tmp_path = filepath + ".tmp_enc"
            with open(filepath, "r", encoding=read_enc, errors="replace") as fin, \
                 open(tmp_path, "w", encoding=target_encoding, errors="replace", newline="") as fout:
                while True:
                    chunk = fin.read(1024 * 1024)
                    if not chunk:
                        break
                    fout.write(chunk)
            shutil.move(tmp_path, filepath)
        except OSError as ex:
            self._log(f"编码转换失败: {ex}")
            try:
                os.remove(tmp_path)
            except OSError as ex:
                self._log(f"临时文件删除失败: {ex}")
