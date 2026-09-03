#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
牛牛文档工具 v1.0.0 — WebView 版（方案C 100% 还原）

用 pywebview 嵌入方案C设计稿 HTML 作为真实运行 UI，
通过 JS<->Python bridge 调用 src/core/ 业务逻辑。
渲染引擎 = 浏览器内核（EdgeWebView2/CEF），与设计稿零差异。
"""
import os
import sys
import json
import time
import contextlib

# 确保能导入 core 模块
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SRC_DIR)
sys.path.insert(0, os.path.join(SRC_DIR, "core"))

# v2.3.0：9 个 exec_* 业务功能已拆至 core/api_business.py（BusinessApiMixin），
# 本模块仅保留窗口控制、文件管理、进度与状态回调，故只依赖 FileConverter 与 format_elapsed。
from core.convert import FileConverter
from core.utils import format_elapsed
from core.api_business import BusinessApiMixin

try:
    import webview
    HAVE_WEBVIEW = True
except ImportError:
    HAVE_WEBVIEW = False

try:
    import tkinter as tk
    from tkinter import filedialog
    HAVE_TK = True
except ImportError:
    HAVE_TK = False

# 仅作为 read_version() 读取 VERSION 文件失败时的回退值（P-M4 漂移点）。
# 窗口标题与前端版本号均取自 read_version()（见 Api.version 与 main()），不使用本常量拼标题。
# ⚠️ 发版时须与根目录 VERSION 文件同步；门禁项 7（版本号扫描）会在不一致时告警。
VERSION = "1.0.1"


def read_version():
    """从 VERSION 文件读取版本号。
    PyInstaller 单文件模式下 VERSION 被 --add-data 打包到 sys._MEIPASS 根目录，
    开发模式下 VERSION 在项目根目录（src 的上一级）。"""
    # 候选路径：PyInstaller 解包目录、开发模式项目根目录
    candidates = []
    with contextlib.suppress(AttributeError):
        candidates.append(os.path.join(sys._MEIPASS, "VERSION"))
    candidates.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "VERSION"))
    for vf in candidates:
        try:
            with open(vf, "r", encoding="utf-8") as f:
                ver = f.read().strip()
                if ver:
                    return ver
        except OSError:
            continue
    return VERSION


class Api(BusinessApiMixin):
    """JS <-> Python bridge：前端通过 window.pyapi.xxx() 调用"""

    def __init__(self):
        self.file_list = []
        self.is_busy = False
        self._window = None
        self.version = read_version()
        # 执行完成后是否自动打开输出文件夹（由前端"完成后打开文件夹"复选框控制）
        self._open_folder_after_done = False
        # 窗口最大化状态（frameless 模式下无原生最大化按钮，需自行跟踪）
        self._is_maximized = False

    def set_window(self, window):
        self._window = window

    # ================================================================
    # 工具方法
    # ================================================================
    def _log(self, msg):
        """输出日志到 stderr"""
        print(f"[pyapi] {msg}", file=sys.stderr)

    def _result(self, ok=True, msg="", **extra):
        """构造统一返回结构"""
        d = {"ok": ok, "msg": msg}
        d.update(extra)
        return d

    def _get_file_info(self, path):
        """分析文件信息"""
        try:
            info = FileConverter.analyze(path)
            return info
        except Exception as ex:
            return {"path": path, "name": os.path.basename(path),
                    "size_str": "?", "encoding": "unknown", "has_bom": False,
                    "need": True, "preview": "", "size": 0}

    # ================================================================
    # 文件操作
    # ================================================================
    # v2.2.0: pywebview 的 JS bridge 在后台线程执行 Python 方法（util.py:335），
    # 而 create_file_dialog 的 ShowDialog 需要 UI 线程，跨线程调用会静默失败。
    # 因此回退到 tkinter.filedialog，它创建独立的 Tk 对话框窗口，不依赖 WinForms UI 线程。
    def select_files(self, file_types="CSV/TXT"):
        """打开文件选择对话框（v2.2.0: 使用 tkinter 对话框，解决跨线程 WinForms 问题）"""
        try:
            if not HAVE_TK:
                return self._result(False, "tkinter 不可用，无法打开文件对话框")
            root = tk.Tk()
            root.withdraw()  # 隐藏主窗口
            root.attributes('-topmost', True)  # 对话框置顶
            if file_types == "Excel":
                filetypes = [("Excel 文件", "*.xlsx *.xls"), ("所有文件", "*.*")]
            else:
                filetypes = [("CSV/TXT 文件", "*.csv *.txt"), ("所有文件", "*.*")]
            paths = filedialog.askopenfilenames(parent=root, filetypes=filetypes)
            root.destroy()
        except Exception as ex:
            self._log(f"文件对话框失败: {ex}")
            with contextlib.suppress(Exception):
                root.destroy()
            return self._result(False, f"文件对话框失败: {ex}")
        if not paths:
            return self._result(True, "取消选择", files=[])
        added = []
        for p in paths:
            if any(f["path"] == p for f in self.file_list):
                continue
            info = self._get_file_info(p)
            self.file_list.append(info)
            added.append(info)
        return self._result(True, f"已添加 {len(added)} 个文件", files=added,
                            file_list=list(self.file_list))

    def select_dir(self):
        """选择输出目录（v2.2.0: 使用 tkinter 对话框）"""
        try:
            if not HAVE_TK:
                return self._result(False, "tkinter 不可用")
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            d = filedialog.askdirectory(parent=root)
            root.destroy()
        except Exception as ex:
            self._log(f"目录对话框失败: {ex}")
            with contextlib.suppress(Exception):
                root.destroy()
            return self._result(False, f"目录对话框失败: {ex}")
        if d:
            return self._result(True, "已选择目录", dir=d)
        return self._result(True, "取消选择", dir="")

    def add_files(self, paths_json):
        """通过路径添加文件（拖拽时调用）"""
        try:
            paths = json.loads(paths_json) if isinstance(paths_json, str) else paths_json
        except (json.JSONDecodeError, TypeError):
            paths = []
        added = []
        for p in paths:
            # #2修复：跳过非字符串值（拖拽可能传 null）
            if not isinstance(p, str):
                continue
            p = p.strip()
            if not p or not os.path.isfile(p):
                continue
            if any(f["path"] == p for f in self.file_list):
                continue
            info = self._get_file_info(p)
            self.file_list.append(info)
            added.append(info)
        return self._result(True, f"已添加 {len(added)} 个文件", files=added,
                            file_list=list(self.file_list))

    def _on_drop_files(self, event):
        """pywebview DOM drop 事件回调：获取完整文件路径并添加到列表。
        WebView2 (Chromium) 的 File 对象没有 .path 属性（Electron 私有），
        必须通过 pywebview DOM 事件系统（postMessageWithAdditionalObjects）获取。"""
        try:
            files = event.get('dataTransfer', {}).get('files', [])
            paths = []
            for f in files:
                fp = f.get('pywebviewFullPath') or f.get('path', '')
                if fp:
                    paths.append(fp)
            if paths:
                res = self.add_files(paths)
                if self._window:
                    self._window.evaluate_js(
                        f"if(window._pyapiDropUpdate)window._pyapiDropUpdate({json.dumps(res)})")
        except Exception as ex:
            self._log(f"拖拽文件处理失败: {ex}")

    def register_drop_handler(self):
        """为当前 dropzone 元素注册 pywebview DOM drop 事件（每次 UI 重建后调用）。
        v2.2.0: selectFn 切换功能面板时 dropzone 被重建，须重新绑定。
        由 JS 端 selectFn 末尾调用。"""
        if not self._window:
            return self._result(True, "")
        try:
            elements = self._window.dom.get_elements('#dropzone')
            if elements:
                self._drop_element = elements[0]
                self._drop_element.on('drop', self._on_drop_files)
        except Exception as ex:
            self._log(f"注册拖拽事件失败: {ex}")
        return self._result(True, "")

    def remove_file(self, index):
        """移除文件列表中的指定文件"""
        try:
            idx = int(index)
        except (ValueError, TypeError):
            idx = -1
        if 0 <= idx < len(self.file_list):
            del self.file_list[idx]
        return self._result(True, "已移除", file_list=list(self.file_list))

    def clear_files(self):
        """清空文件列表"""
        self.file_list.clear()
        return self._result(True, "已清空", file_list=[])

    def get_file_list(self):
        """获取当前文件列表"""
        return self._result(True, "", file_list=list(self.file_list))

    # ================================================================
    # 进度回调
    # ================================================================
    def _make_progress_cb(self, total, action_name, file_name):
        """创建进度回调函数，通过 JS 更新 UI（#19修复：加节流，距上次<100ms跳过）"""
        state = {"last": 0.0}
        def cb(ratio):
            if not self._window:
                return
            now = time.perf_counter()
            if now - state["last"] < 0.1 and ratio < 1.0:
                return
            state["last"] = now
            pct = int(ratio * 100)
            overall = ratio * 100
            js = (f"if(window.onProgress)window.onProgress({overall:.1f},"
                  f"{json.dumps(action_name)},{json.dumps(file_name)},{pct})")
            try:
                self._window.evaluate_js(js)
            except Exception as ex:
                self._log(f"进度回调失败: {ex}")
        return cb

    def _set_status(self, text):
        """通过 JS 更新状态栏"""
        if self._window:
            try:
                self._window.evaluate_js(
                    f"if(window.onStatus)window.onStatus({json.dumps(text)})")
            except Exception as ex:
                self._log(f"状态更新失败: {ex}")

    def _set_busy(self, busy):
        """设置忙碌状态"""
        self.is_busy = busy
        if self._window:
            try:
                self._window.evaluate_js(
                    f"if(window.onBusy)window.onBusy({str(busy).lower()})")
            except Exception as ex:
                self._log(f"忙碌状态更新失败: {ex}")

    def _on_done(self, results, action_name, elapsed):
        """完成回调"""
        ok_count = sum(1 for r in results if r.get("ok"))
        fail_count = len(results) - ok_count
        total_parts = sum(len(r.get("parts", [])) for r in results if r.get("ok"))
        total_matched = sum(r.get("matched_count", 0) for r in results if r.get("ok"))
        time_str = format_elapsed(elapsed)

        if action_name == "提取":
            msg = (f"完成: {action_name} {ok_count}/{len(results)} 个文件, "
                   f"共匹配 {total_matched} 行  → 耗时 {time_str}")
        elif total_parts > 0:
            msg = (f"完成: {action_name} {ok_count}/{len(results)} 个文件, "
                   f"共生成 {total_parts} 个文件  → 耗时 {time_str}")
        else:
            msg = f"完成: {action_name} {ok_count}/{len(results)} 个文件  → 耗时 {time_str}"

        self._set_status(msg)
        self._set_busy(False)

        # 打开文件夹（#22修复：多目录去重逐个打开）
        if getattr(self, '_open_folder_after_done', False):
            opened = set()
            for r in results:
                if r.get("ok"):
                    # v2.4.2: 拆成清晰的多步赋值，避免单行 or 表达式在 parts 为空时
                    # 取到 [None] 默认值但实际不生效的可读性陷阱
                    out = r.get("output")
                    if not out:
                        parts = r.get("parts") or []
                        if parts:
                            out = parts[0]
                    if not out:
                        out = r.get("matched")
                    if out:
                        folder = os.path.dirname(out)
                        if folder and folder not in opened and os.path.isdir(folder):
                            opened.add(folder)
                            try:
                                os.startfile(folder)
                            except OSError as ex:
                                self._log(f"打开文件夹失败: {ex}")

        # 通知前端
        if self._window:
            title = f"{action_name}完成"
            if fail_count > 0:
                detail = f"{msg}\n失败: {fail_count}"
            else:
                detail = msg
            try:
                js = (f"if(window.onDone)window.onDone({json.dumps(title)},"
                      f"{json.dumps(detail)},{ok_count},{fail_count})")
                self._window.evaluate_js(js)
            except Exception as ex:
                self._log(f"完成回调失败: {ex}")


    # ================================================================
    # 版本与系统信息
    # ================================================================
    def get_version(self):
        return self._result(True, "", version=self.version)

    def minimize_window(self):
        """最小化窗口（frameless 模式下由 HTML 标题栏 btnMin 调用）"""
        if self._window:
            try:
                self._window.minimize()
            except Exception as ex:
                self._log(f"最小化失败: {ex}")
        return self._result(True, "")

    def toggle_maximize(self):
        """最大化 / 还原切换（frameless 模式下由 HTML 标题栏 btnMax 调用）。
        v2.1.8：改用 Win32 IsZoomed 实时判定，替代 _is_maximized 软件标记——
        用户可能通过 Win+方向键 等系统途径改变窗口状态，标记会失步导致按钮失灵。"""
        if self._window:
            try:
                import ctypes as _ctypes
                hwnd = int(self._window.native.Handle.ToInt64())  # IntPtr 须 ToInt64
                if _ctypes.windll.user32.IsZoomed(hwnd):
                    self._window.restore()
                else:
                    self._window.maximize()
            except Exception as ex:
                self._log(f"最大化切换失败: {ex}")
        return self._result(True, "")

    def close_window(self):
        """关闭窗口"""
        if self._window:
            try:
                self._window.destroy()
            except Exception as ex:
                self._log(f"关闭窗口失败: {ex}")
        return self._result(True, "")

    def resize_step(self, direction, dx=0, dy=0):
        """frameless 边缘缩放（软件模拟，与 pywebview 拖拽同构）。
        JS 每次 mousemove 发来物理像素增量，本方法 SetWindowPos 逐步调整窗口。

        v2.2.0 教训：原方案 SendMessage(WM_NCLBUTTONDOWN, HT*) 依赖原生模态缩放
        循环，但 mousedown 发生在 WebView2 内部，Chromium 捕获鼠标使模态循环收不到
        WM_MOUSEMOVE/WM_LBUTTONUP，循环空转、窗口不跟手。改为无模态循环的逐帧
        SetWindowPos（pywebview 拖拽已验证的同构路径）。

        边界处理：
        - 最大化/最小化时忽略；
        - 增量不做方向裁剪——向内拖（收缩窗口）是合法操作，只受最小尺寸钳制；
        - 最小尺寸用 self._window.min_size（逻辑像素）× DPI 缩放换算为物理像素钳制；
        - left/top 边缘同时调整位置与尺寸（对边固定），right/bottom 只改尺寸。"""
        if not self._window:
            return self._result(False, "")
        try:
            import ctypes
            import ctypes.wintypes
            u32 = ctypes.windll.user32
            # argtypes 显式声明：句柄/坐标按平台整型宽传递，防 64 位截断隐患
            u32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            u32.IsZoomed.argtypes = [ctypes.c_void_p]
            u32.IsIconic.argtypes = [ctypes.c_void_p]
            u32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                         ctypes.c_int, ctypes.c_int,
                                         ctypes.c_int, ctypes.c_int, ctypes.c_uint]
            hwnd = int(self._window.native.Handle.ToInt64())
            if u32.IsZoomed(hwnd) or u32.IsIconic(hwnd):
                return self._result(True, "")
            valid = {"left", "right", "top", "bottom",
                     "topleft", "topright", "bottomleft", "bottomright"}
            if direction not in valid:
                return self._result(False, "未知方向")
            dx, dy = int(dx), int(dy)
            if not (dx or dy):
                return self._result(True, "")

            class _RECT(ctypes.Structure):
                _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                            ("r", ctypes.c_long), ("b", ctypes.c_long)]
            rc = _RECT()
            if not u32.GetWindowRect(hwnd, ctypes.byref(rc)):
                return self._result(False, "")
            # 最小尺寸：pywebview 存的是逻辑像素，GetWindowRect/SetWindowPos 是物理像素
            try:
                minw, minh = self._window.min_size
            except Exception:
                minw, minh = (820, 600)
            try:
                dpi = u32.GetDpiForWindow(hwnd)
            except Exception:
                dpi = 96
            scale = (dpi or 96) / 96.0
            minw = max(1, int(minw * scale))
            minh = max(1, int(minh * scale))

            l, t, r, b = rc.l, rc.t, rc.r, rc.b
            if "left" in direction:
                l += dx
                if r - l < minw:
                    l = r - minw
            elif "right" in direction:
                r += dx
                if r - l < minw:
                    r = l + minw
            if "top" in direction:
                t += dy
                if b - t < minh:
                    t = b - minh
            elif "bottom" in direction:
                b += dy
                if b - t < minh:
                    b = t + minh
            SWP_NOZORDER, SWP_NOACTIVATE = 0x0004, 0x0010
            u32.SetWindowPos(hwnd, 0, l, t, r - l, b - t, SWP_NOZORDER | SWP_NOACTIVATE)
        except Exception as ex:
            self._log(f"缩放失败: {ex}")
        return self._result(True, "")

    def move_step(self, dx=0, dy=0):
        """frameless 窗口拖动（软件模拟，v2.2.2 起接管 pywebview drag-region 职责）。
        JS 每次 mousemove 发来屏幕坐标物理像素增量，SetWindowPos 只改位置不改尺寸。

        v2.2.1 教训：pywebview 自带拖拽（drag-region JS：起点记 clientX、增量发
        screenX-clientX）与自建边缘缩放并存时两套状态机互相干扰——缩放改变窗口
        位置后拖拽行为异常（顶部边缘抖动 / resize 后偶发无法拖动）。现拖动与缩放
        统一由前端一个状态机驱动，本方法与 resize_step 同构，仅改位置。
        最大化/最小化时忽略。"""
        if not self._window:
            return self._result(False, "")
        try:
            import ctypes
            import ctypes.wintypes
            u32 = ctypes.windll.user32
            u32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            u32.IsZoomed.argtypes = [ctypes.c_void_p]
            u32.IsIconic.argtypes = [ctypes.c_void_p]
            u32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                         ctypes.c_int, ctypes.c_int,
                                         ctypes.c_int, ctypes.c_int, ctypes.c_uint]
            hwnd = int(self._window.native.Handle.ToInt64())
            if u32.IsZoomed(hwnd) or u32.IsIconic(hwnd):
                return self._result(True, "")
            dx, dy = int(dx), int(dy)
            if not (dx or dy):
                return self._result(True, "")
            class _RECT(ctypes.Structure):
                _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                            ("r", ctypes.c_long), ("b", ctypes.c_long)]
            rc = _RECT()
            if not u32.GetWindowRect(hwnd, ctypes.byref(rc)):
                return self._result(False, "")
            SWP_NOSIZE, SWP_NOZORDER, SWP_NOACTIVATE = 0x0001, 0x0004, 0x0010
            u32.SetWindowPos(hwnd, 0, rc.l + dx, rc.t + dy, 0, 0,
                             SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
        except Exception as ex:
            self._log(f"拖动失败: {ex}")
        return self._result(True, "")


def get_html_path():
    """获取运行版 HTML 路径"""
    # PyInstaller 打包后从 _MEIPASS 读取
    try:
        base = sys._MEIPASS
    except AttributeError:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "app.html")


def centered_position(width, height):
    """计算窗口居中坐标（v2.2.3）。

    背景：未向 create_window 传 x/y 时，WinForms 使用 FormStartPosition.
    WindowsDefaultLocation（系统级联定位），窗口会落在屏幕左上角附近。

    实现：返回主屏「工作区」（排除任务栏）的居中坐标，单位与 create_window 的
    width/height 一致（WinForms 逻辑像素），故天然适配不同分辨率与 DPI 缩放：
      ① 优先用 WinForms Screen.PrimaryScreen.WorkingArea（单位一致，最稳）；
      ② 回退 ctypes SystemParametersInfoW(SPI_GETWORKAREA)，并按系统 DPI 把物理
         像素换算回逻辑像素，避免在 125%/150% 缩放下算出的偏移不正确。
    任一路径失败则返回 (None, None)，交给 pywebview 走默认定位（不阻塞启动）。
    """
    try:
        import clr
        clr.AddReference("System.Windows.Forms")
        from System.Windows.Forms import Screen
        area = Screen.PrimaryScreen.WorkingArea
        return (max(0, (int(area.Width) - width) // 2),
                max(0, (int(area.Height) - height) // 2))
    except Exception as ex:
        # 不静默吞异常（审查标准 D 域）：记录后继续走 ctypes 回退路径
        print(f"[center] WinForms 方案失败，改用 ctypes: {ex}", file=sys.stderr)
    try:
        import ctypes
        u32 = ctypes.windll.user32

        class _RECT(ctypes.Structure):
            _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                        ("r", ctypes.c_long), ("b", ctypes.c_long)]
        rc = _RECT()
        SPI_GETWORKAREA = 0x0030
        if u32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rc), 0):
            # 物理像素 → 逻辑像素（与 width/height 同单位）
            try:
                dpi = u32.GetDpiForSystem()
            except Exception:
                dpi = 96
            scale = (dpi or 96) / 96.0
            work_w = int((rc.r - rc.l) / scale)
            work_h = int((rc.b - rc.t) / scale)
            return max(0, (work_w - width) // 2), max(0, (work_h - height) // 2)
    except Exception as ex:
        # 同理：记录后回退到 pywebview 默认定位，不阻塞启动
        print(f"[center] 居中计算失败，使用默认定位: {ex}", file=sys.stderr)
    return None, None


def main():
    if not HAVE_WEBVIEW:
        print("错误: pywebview 未安装，请运行 pip install pywebview", file=sys.stderr)
        sys.exit(1)

    api = Api()
    html_path = get_html_path()

    # v2.2.3: 启动时窗口居中（不同分辨率/DPI 均自适应）
    win_w, win_h = 1080, 740
    pos_x, pos_y = centered_position(win_w, win_h)

    # 创建窗口
    window = webview.create_window(
        title=f"牛牛文档工具 v{api.version}",
        url=html_path,
        js_api=api,
        width=win_w,
        height=win_h,
        x=pos_x,
        y=pos_y,
        min_size=(820, 600),
        text_select=False,
        resizable=True,
        # frameless=True：隐藏 Windows 原生标题栏，仅保留 app.html 的自绘标题栏，
        # 消除"原生标题栏 + HTML 标题栏"双套并存的视觉错位（方案C设计稿为自绘标题栏）。
        frameless=True,
        # easy_drag=False：关闭 pywebview 默认的"整个窗口可拖拽"（该模式下按钮的
        # mousedown 也会成为拖拽起点，且无移动阈值，会干扰标题栏按钮点击）。
        # 改为仅 .pywebview-drag-region（已加在标题栏 div 上）可拖拽窗口。
        easy_drag=False,
        background_color='#F3F3F3',   # 关键：消除 WebView2 加载前的白色闪烁
        # transparent=False（v2.1.7 定案）：实测 transparent=True 时 HTML 透明区
        # 只显示宿主 WinForms Form 的默认灰底 #F0F0F0（并非桌面），四角呈灰白
        # 直角块；而 TransparencyKey/SetWindowRgn 等真正透桌面的手段会让 WebView2
        # 内容整体变黑（DirectComposition 与分层窗口/区域裁剪不兼容），Win10 亦无
        # DWMWA_WINDOW_RADIUS 圆角 API。故关闭 transparent，改为直角满铺 +
        # frameless 下 pywebview shadow=True 自动启用的 DWM 系统投影。
        transparent=False,
    )
    api.set_window(window)

    # v2.2.0: 窗口加载后注册 DOM drop 事件（首次绑定）
    window.events.loaded += lambda: api.register_drop_handler()

    # 启动 WebView
    webview.start(debug=False)


if __name__ == "__main__":
    main()
