import tkinter as tk
import requests
import json
import threading
import time
import os
import sys
from datetime import datetime, timezone, timedelta

# 北京时区 UTC+8
TZ_BEIJING = timezone(timedelta(hours=8))

def now_beijing():
    """返回当前北京时间"""
    return datetime.now(tz=TZ_BEIJING)

BG     = '#000000'  # 纯黑，灵动岛经典底色
BG2    = '#0d0d0d'  # 极深灰卡片
BG3    = '#1a1e24'  # 稍微亮一点的深灰
ACCENT = '#1f6feb'
GREEN  = '#3fb950'
YELLOW = '#d29922'
RED    = '#f85149'
WHITE  = '#f0f6fc'  # 更亮更柔和的白
GRAY   = '#8b949e'
BORDER = '#30363d'
CYAN   = '#58a6ff'
PURPLE = '#bc8cff'

def _get_config_dir():
    """返回配置文件所在目录：打包成 exe 时用 exe 所在目录，直接运行 .py 时用脚本所在目录。"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后，sys.executable 是 exe 本身的路径
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(_get_config_dir(), 'config.json')


def enable_window_effects(hwnd):
    try:
        import ctypes
        # 1. 启用 Windows 11 原生圆角
        # DWMWA_WINDOW_CORNER_PREFERENCE = 33
        # DWMWCP_ROUND = 2 (圆角)
        dwm = ctypes.windll.dwmapi
        corner_preference = ctypes.c_int(2)
        dwm.DwmSetWindowAttribute(
            hwnd,
            33,
            ctypes.byref(corner_preference),
            ctypes.sizeof(corner_preference)
        )
    except Exception:
        pass

    try:
        import ctypes
        # 2. 启用窗口阴影
        class MARGINS(ctypes.Structure):
            _fields_ = [
                ("cxLeftWidth", ctypes.c_int),
                ("cxRightWidth", ctypes.c_int),
                ("cyTopHeight", ctypes.c_int),
                ("cyBottomHeight", ctypes.c_int)
            ]
        dwm = ctypes.windll.dwmapi
        margins = MARGINS(-1, -1, -1, -1)
        dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
    except Exception:
        pass


def load_config():
    d = {'api_key': '', 'refresh_sec': 60, 'x': None, 'y': None, 'alpha': 0.93}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding='utf-8') as f:
                d.update(json.load(f))
        except Exception:
            pass
    return d


def save_config(cfg):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


class Dashboard:
    def __init__(self):
        self.cfg = load_config()
        self.root = tk.Tk()
        self._setup_window()
        self._build_ui()
        self._schedule_refresh()
        self.root.mainloop()

    # ── Window ──────────────────────────────────────────────────────────────

    def _setup_window(self):
        self.root.overrideredirect(True)
        self._pinned = self.cfg.get('pinned', True)
        self.root.attributes('-topmost', self._pinned)
        self.root.attributes('-alpha', self.cfg.get('alpha', 0.95))
        self.root.configure(bg=BG)

        # 灵动岛状态变量
        # 'island' = 灵动岛胶囊状态, 'expanded' = 展开看板状态
        self._island_state = self.cfg.get('island_state', 'expanded')
        self._cny_mode = self.cfg.get('cny_mode', False)
        
        # 尺寸定义
        self._W_island = 270
        self._H_island = 36
        self._W_expanded = 370
        self._H_expanded = 185

        # 动画状态
        self._animating = False

        # 初始尺寸
        W = self._W_expanded if self._island_state == 'expanded' else self._W_island
        H = self._H_expanded if self._island_state == 'expanded' else self._H_island

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = self.cfg['x'] if self.cfg['x'] is not None else sw - W - 20
        y = self.cfg['y'] if self.cfg['y'] is not None else 60
        self.root.geometry(f'{W}x{H}+{max(0,x)}+{max(0,y)}')

        # 启用 Windows 11 圆角和阴影
        self.root.update_idletasks()
        enable_window_effects(self.root.winfo_id())

        self._dx = self._dy = 0
        self.root.bind('<Button-1>',        self._drag_start)
        self.root.bind('<B1-Motion>',       self._drag_move)
        self.root.bind('<ButtonRelease-1>', self._drag_end)
        self.root.bind('<Button-3>',        self._ctx_menu)

    def _drag_start(self, e):
        # 记录鼠标点击时相对于窗口左上角的偏移量（只记一次，全程不变）
        self._off_x = e.x_root - self.root.winfo_x()
        self._off_y = e.y_root - self.root.winfo_y()
        # 缓存屏幕和窗口尺寸，避免在 _drag_move 里反复查询
        self._sw = self.root.winfo_screenwidth()
        self._sh = self.root.winfo_screenheight()
        self._ww = self.root.winfo_width()
        self._wh = self.root.winfo_height()

    def _drag_move(self, e):
        # 直接用鼠标屏幕绝对坐标减去偏移量，无需任何 winfo 查询，最流畅
        new_x = e.x_root - self._off_x
        new_y = e.y_root - self._off_y
        # 边界限制（使用缓存值，零开销）
        new_x = max(-self._ww + 40, min(self._sw - 40, new_x))
        new_y = max(0, min(self._sh - self._wh, new_y))
        self.root.geometry(f'+{new_x}+{new_y}')
    def _drag_end(self, e):
        # 自动贴边吸附逻辑
        W  = self.root.winfo_width()
        H  = self.root.winfo_height()
        x  = self.root.winfo_x()
        y  = self.root.winfo_y()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()

        snap_threshold = 40  # 贴边吸附阈值（像素）

        # 检查左侧贴边
        if x < snap_threshold:
            self._animate_snap(0, y)
        # 检查右侧贴边
        elif sw - (x + W) < snap_threshold:
            self._animate_snap(sw - W, y)
        # 检查顶部贴边
        elif y < snap_threshold:
            self._animate_snap(x, 0)
        else:
            self.cfg['x'], self.cfg['y'] = x, y
            save_config(self.cfg)

    def _animate_snap(self, target_x, target_y):
        # 平滑吸附动画
        curr_x = self.root.winfo_x()
        curr_y = self.root.winfo_y()
        W = self.root.winfo_width()
        H = self.root.winfo_height()
        
        step_x = (target_x - curr_x) // 2
        step_y = (target_y - curr_y) // 2
        
        if abs(step_x) >= 1 or abs(step_y) >= 1:
            new_x = curr_x + step_x
            new_y = curr_y + step_y
            self.root.geometry(f'{W}x{H}+{new_x}+{new_y}')
            self.root.after(10, lambda: self._animate_snap(target_x, target_y))
        else:
            self.root.geometry(f'{W}x{H}+{target_x}+{target_y}')
            self.cfg['x'], self.cfg['y'] = target_x, target_y
            save_config(self.cfg)

    # ── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── 1. 灵动岛胶囊视图 (Island Frame) ──
        self._island_frame = tk.Frame(self.root, bg=BG, cursor='hand2')
        
        # 灵动岛内部容器，去掉浅色边框，直接使用纯黑背景，呈现极致纯粹的黑色胶囊质感
        island_capsule = tk.Frame(self._island_frame, bg=BG2, highlightthickness=0)
        island_capsule.pack(fill='both', expand=True, padx=2, pady=2)
        
        # 灵动岛左侧：Logo（兼任状态指示点，绿色=已连接，黄色=刷新中，红色=错误）
        self._island_logo = tk.Label(island_capsule, text='⚡', bg=BG2, fg=CYAN, font=('Segoe UI', 10, 'bold'))
        self._island_logo.pack(side='left', padx=(12, 2))
        
        # 灵动岛中间：并排显示余额和今日消费，保留各自的颜色，字体调大一点点，空格减少
        island_vals_frame = tk.Frame(island_capsule, bg=BG2)
        island_vals_frame.pack(side='left', expand=True)
        
        self._island_bal_lbl = tk.Label(island_vals_frame, text='余额:——', bg=BG2, fg=GRAY, font=('Consolas', 9, 'bold'))
        self._island_bal_lbl.pack(side='left')
        
        self._island_sep = tk.Label(island_vals_frame, text='|', bg=BG2, fg=BORDER, font=('Consolas', 9))
        self._island_sep.pack(side='left', padx=4)
        
        self._island_daily_lbl = tk.Label(island_vals_frame, text='今日:——', bg=BG2, fg=GRAY, font=('Consolas', 9, 'bold'))
        self._island_daily_lbl.pack(side='left')
        
        # 灵动岛右侧：展开箭头（极简单个字符，节省空间）
        self._island_arrow = tk.Label(island_capsule, text='›', bg=BG2, fg=GRAY, font=('Segoe UI', 11, 'bold'))
        self._island_arrow.pack(side='right', padx=(2, 12))

        # 绑定灵动岛交互事件
        for widget in [self._island_frame, island_capsule, self._island_logo, island_vals_frame, 
                       self._island_bal_lbl, self._island_sep, self._island_daily_lbl, self._island_arrow]:
            widget.bind('<Button-1>', lambda _: self._toggle_island_state())
            widget.bind('<Enter>', lambda _: self._on_island_hover(True, island_capsule))
            widget.bind('<Leave>', lambda _: self._on_island_hover(False, island_capsule))

        # ── 2. 展开看板视图 (Expanded Frame) ──
        self._expanded_frame = tk.Frame(self.root, bg=BG)

        # ── title bar ──
        bar = tk.Frame(self._expanded_frame, bg=BG2, height=32, highlightthickness=1, highlightbackground=BORDER)
        bar.pack(fill='x', padx=2, pady=(2, 0))
        bar.pack_propagate(False)

        # 双击标题栏收起为灵动岛
        bar.bind('<Double-Button-1>', lambda _: self._toggle_island_state())

        tk.Label(bar, text=' ⚡ OpenRouter',
                 bg=BG2, fg=WHITE, font=('Segoe UI', 10, 'bold')
                 ).pack(side='left', pady=3)

        self._dot    = tk.Label(bar, text='●', bg=BG2, fg=GRAY, font=('Segoe UI', 7))
        self._status = tk.Label(bar, text='...', bg=BG2, fg=WHITE, font=('Segoe UI', 7))
        self._dot.pack(side='left', padx=(6, 1))
        self._status.pack(side='left')

        # CNY/USD toggle — left side so it's always visible when collapsed
        cny_fg = YELLOW if self._cny_mode else GRAY
        self._cny_btn = tk.Label(bar, text='¥', bg=BG2, fg=cny_fg,
                                  font=('Segoe UI', 8, 'bold'), cursor='hand2', padx=4)
        self._cny_btn.pack(side='left', padx=(4, 0))
        self._cny_btn.bind('<Button-1>', lambda _: self._toggle_cny())
        self._cny_btn.bind('<Enter>',    lambda _: self._cny_btn.config(fg=WHITE))
        self._cny_btn.bind('<Leave>',    lambda _: self._cny_btn.config(
                                             fg=YELLOW if self._cny_mode else GRAY))

        self._col2_cells = []

        # ✕ 最右侧 — 先 pack 保证在最右边
        close_btn = tk.Label(bar, text='✕', bg=BG2, fg=WHITE,
                             font=('Segoe UI', 9), cursor='hand2', padx=5)
        close_btn.pack(side='right', padx=(0, 2))
        close_btn.bind('<Button-1>', lambda _: self._quit())
        close_btn.bind('<Enter>',    lambda _: close_btn.config(fg=RED))
        close_btn.bind('<Leave>',    lambda _: close_btn.config(fg=WHITE))

        # 收起为灵动岛按钮
        self._shrink_btn = tk.Label(bar, text='▲', bg=BG2, fg=GRAY,
                                  font=('Segoe UI', 8), cursor='hand2', padx=4)
        self._shrink_btn.pack(side='right', padx=(0, 0))
        self._shrink_btn.bind('<Button-1>', lambda _: self._toggle_island_state())
        self._shrink_btn.bind('<Enter>',    lambda _: self._shrink_btn.config(fg=WHITE))
        self._shrink_btn.bind('<Leave>',    lambda _: self._shrink_btn.config(fg=GRAY))

        # pin button
        self._pin_lbl = tk.Label(bar, text='📌', bg=BG2,
                                  fg=WHITE if self._pinned else GRAY,
                                  font=('Segoe UI', 8), cursor='hand2', padx=4)
        self._pin_lbl.pack(side='right', padx=(0, 0))
        self._pin_lbl.bind('<Button-1>', lambda _: self._toggle_pin())
        self._pin_lbl.bind('<Enter>',    lambda _: self._pin_lbl.config(fg=WHITE))
        self._pin_lbl.bind('<Leave>',    lambda _: self._pin_lbl.config(
                                             fg=WHITE if self._pinned else GRAY))

        for txt, cmd, hv, fs in [('⚙', self._open_settings,  WHITE, 9),
                                   ('↻', self._trigger_refresh, WHITE, 12)]:
            lb = tk.Label(bar, text=txt, bg=BG2, fg=WHITE,
                          font=('Segoe UI', fs), cursor='hand2', padx=4)
            lb.pack(side='right')
            lb.bind('<Button-1>', lambda _, c=cmd: c())
            lb.bind('<Enter>',    lambda _, l=lb, c=hv: l.config(fg=c))
            lb.bind('<Leave>',    lambda _, l=lb: l.config(fg=WHITE))

        # ── metric grid (2 rows × 3 cols) ──
        grid = tk.Frame(self._expanded_frame, bg=BG, padx=2, pady=2)
        grid.pack(fill='both', expand=True)
        grid.columnconfigure((0, 1, 2), weight=1, uniform='col')

        # (key, label, row, col, accent_color)
        specs = [
            ('balance', '账户余额', 0, 0, GREEN),
            ('daily',   '今日消费', 0, 1, RED),
            ('total',   '累计消费', 0, 2, PURPLE),
            ('monthly', '本月消费', 1, 0, CYAN),
        ]
        self._vals = {}
        for key, label, row, col, acolor in specs:
            # wrap 容器，使用 highlightthickness=1 配合 BORDER 颜色，在 Windows 11 圆角下呈现出极其精致的圆角卡片质感
            wrap = tk.Frame(grid, bg=acolor, highlightthickness=1, highlightbackground=BORDER)
            wrap.grid(row=row, column=col, padx=2, pady=2, sticky='nsew')
            cell = tk.Frame(wrap, bg=BG2, padx=7, pady=4)
            cell.pack(fill='both', expand=True, padx=(3, 0))  # 左侧留出 3px 的彩色指示条，上下不顶格，更显圆润
            tk.Label(cell, text=label, bg=BG2, fg=GRAY,
                     font=('Segoe UI', 8), anchor='w').pack(anchor='w')
            v = tk.Label(cell, text='——', bg=BG2, fg=WHITE,
                         font=('Consolas', 13, 'bold'), anchor='w')
            v.pack(anchor='w')
            self._vals[key] = v
            if col == 2:
                self._col2_cells.append(wrap)
            if key == 'monthly':
                self._monthly_pct = tk.Label(cell, text='', bg=BG2, fg=GRAY,
                                             font=('Segoe UI', 7), anchor='w')
                self._monthly_pct.pack(anchor='w')
                bar_bg = tk.Frame(cell, bg=BG3, height=3)
                bar_bg.pack(fill='x', pady=(2, 0))
                bar_bg.pack_propagate(False)
                self._monthly_bar = tk.Frame(bar_bg, bg=CYAN, height=3)
                self._monthly_bar.place(x=0, y=0, relheight=1.0, relwidth=0)

        # top3 卡片占 (1,1)
        top3_wrap = tk.Frame(grid, bg=PURPLE, highlightthickness=1, highlightbackground=BORDER)
        top3_wrap.grid(row=1, column=1, padx=2, pady=2, sticky='nsew')
        top3_cell = tk.Frame(top3_wrap, bg=BG2, padx=6, pady=2)
        top3_cell.pack(fill='both', expand=True, padx=(3, 0))
        top3_cell.columnconfigure(1, weight=1)
        self._top3_title = tk.Label(top3_cell, text='本月模型 TOP 3', bg=BG2, fg=GRAY,
                                     font=('Segoe UI', 7), anchor='w')
        self._top3_title.grid(row=0, column=0, columnspan=3, sticky='w', pady=(0, 0))
        self._top3_lbls = []
        medals = ['①', '②', '③']
        for i in range(3):
            tk.Label(top3_cell, text=medals[i], bg=BG2, fg=GRAY,
                     font=('Segoe UI', 7)).grid(row=i + 1, column=0, sticky='w', pady=0)
            name_lbl = tk.Label(top3_cell, text='——', bg=BG2, fg=GRAY,
                                font=('Segoe UI', 7), anchor='w')
            name_lbl.grid(row=i + 1, column=1, sticky='w', padx=(2, 0), pady=0)
            cost_lbl = tk.Label(top3_cell, text='', bg=BG2, fg=GRAY,
                                font=('Consolas', 7), anchor='e')
            cost_lbl.grid(row=i + 1, column=2, sticky='e', pady=0)
            self._top3_lbls.append((name_lbl, cost_lbl))

        # 充值按钮占 (1,2)
        wrap2 = tk.Frame(grid, bg=ACCENT, highlightthickness=1, highlightbackground=BORDER)
        wrap2.grid(row=1, column=2, padx=2, pady=2, sticky='nsew')
        topup_cell = tk.Frame(wrap2, bg=BG2, padx=7, pady=4)
        topup_cell.pack(fill='both', expand=True, padx=(3, 0))
        tk.Label(topup_cell, text='充值', bg=BG2, fg=GRAY,
                 font=('Segoe UI', 8)).pack(anchor='w')
        topup_btn = tk.Label(topup_cell, text='+ 前往充值', bg=ACCENT, fg=WHITE,
                             font=('Segoe UI', 8, 'bold'), cursor='hand2',
                             padx=6, pady=1, relief='flat')
        topup_btn.pack(anchor='w')
        topup_btn.bind('<Button-1>', lambda _: self._open_topup())
        topup_btn.bind('<Enter>',    lambda _: topup_btn.config(bg='#388bfd'))
        topup_btn.bind('<Leave>',    lambda _: topup_btn.config(bg=ACCENT))

        detail_btn = tk.Label(topup_cell, text='📊 本月明细', bg=BG3, fg=CYAN,
                              font=('Segoe UI', 8), cursor='hand2',
                              padx=6, pady=1, relief='flat')
        detail_btn.pack(anchor='w', pady=(3, 0))
        detail_btn.bind('<Button-1>', lambda _: self._open_daily_popup())
        detail_btn.bind('<Enter>',    lambda _: detail_btn.config(fg=WHITE))
        detail_btn.bind('<Leave>',    lambda _: detail_btn.config(fg=CYAN))

        self._col2_cells.append(wrap2)

        self._grid = grid
        grid.rowconfigure((0, 1), weight=1, uniform='row')

        # footer
        footer = tk.Frame(self._expanded_frame, bg=BG3, height=1)
        footer.pack(fill='x')
        self._time_lbl = tk.Label(self._expanded_frame, text='', bg=BG, fg=GRAY,
                                   font=('Segoe UI', 7))
        self._time_lbl.pack(side='bottom', pady=(0, 3))

        # 根据初始状态展示对应的 Frame
        if self._island_state == 'island':
            self._island_frame.pack(fill='both', expand=True, padx=2, pady=2)
        else:
            self._expanded_frame.pack(fill='both', expand=True, padx=2, pady=2)

        if not self.cfg.get('api_key'):
            self.root.after(200, self._open_settings)

    # ── Currency ─────────────────────────────────────────────────────────────

    def _toggle_cny(self):
        self._cny_mode = not self._cny_mode
        self._cny_btn.config(fg=YELLOW if self._cny_mode else GRAY)
        self.cfg['cny_mode'] = self._cny_mode
        save_config(self.cfg)
        if hasattr(self, '_last_data'):
            self._update_ui(self._last_data)

    def _fmt(self, usd):
        """Format a USD float according to current currency mode."""
        rate = float(self.cfg.get('cny_rate', 7))
        if self._cny_mode:
            return f'¥{usd * rate:.2f}'
        return f'${usd:.2f}'

    def _fmt2(self, usd):
        """Format with 2 decimal places (for balance / limit)."""
        rate = float(self.cfg.get('cny_rate', 7))
        if self._cny_mode:
            return f'¥{usd * rate:.2f}'
        return f'${usd:.2f}'

    # ── Island Animation & Hover Effects ──────────────────────────────────────

    def _on_island_hover(self, entering, capsule):
        if self._island_state != 'island' or self._animating:
            return
        if entering:
            # 悬停时：胶囊背景变亮，产生灵动岛的呼吸感，不改变物理宽度以彻底杜绝抖动 Bug
            capsule.config(bg=BG3)
            for w in [self._island_logo, self._island_bal_lbl, self._island_sep, self._island_daily_lbl, self._island_arrow]:
                w.config(bg=BG3)
            self._island_arrow.config(fg=WHITE)
        else:
            # 移开时：恢复原状
            capsule.config(bg=BG2)
            for w in [self._island_logo, self._island_bal_lbl, self._island_sep, self._island_daily_lbl, self._island_arrow]:
                w.config(bg=BG2)
            self._island_arrow.config(fg=GRAY)

    def _toggle_island_state(self):
        if self._animating:
            return
        
        if self._island_state == 'expanded':
            self._island_state = 'island'
            target_w, target_h = self._W_island, self._H_island
            # 收缩时：先隐藏大面板，避免挤压
            self._expanded_frame.pack_forget()
            self._island_frame.pack(fill='both', expand=True, padx=2, pady=2)
        else:
            self._island_state = 'expanded'
            target_w, target_h = self._W_expanded, self._H_expanded
            # 展开时：先隐藏灵动岛，动画结束后再显示大面板
            self._island_frame.pack_forget()

        self.cfg['island_state'] = self._island_state
        save_config(self.cfg)
        
        self._animate_geometry(target_w, target_h)

    def _animate_geometry(self, target_w, target_h):
        self._animating = True
        start_w = self.root.winfo_width()
        start_h = self.root.winfo_height()
        x = self.root.winfo_x()
        y = self.root.winfo_y()

        steps = 12  # 动画帧数
        delay = 12  # 每帧延迟(ms)

        def step_anim(current_step):
            if current_step > steps:
                # 动画结束
                self.root.geometry(f'{target_w}x{target_h}+{x}+{y}')
                if self._island_state == 'expanded':
                    self._expanded_frame.pack(fill='both', expand=True, padx=2, pady=2)
                self._animating = False
                return

            # Ease Out Cubic 缓动公式
            t = current_step / steps
            factor = 1 - (1 - t) ** 3
            
            w = int(start_w + (target_w - start_w) * factor)
            h = int(start_h + (target_h - start_h) * factor)
            
            self.root.geometry(f'{w}x{h}+{x}+{y}')
            self.root.after(delay, lambda: step_anim(current_step + 1))

        step_anim(1)

    # ── Settings ─────────────────────────────────────────────────────────────

    def _open_settings(self):
        dlg = tk.Toplevel(self.root)
        dlg.title('设置')
        dlg.configure(bg=BG2)
        dlg.resizable(False, True)
        dlg.attributes('-topmost', True)
        dlg.grab_set()
        dlg.geometry(f'320x420+{self.root.winfo_x()+20}+{self.root.winfo_y()+32}')

        # ── 统一字体常量 ──
        LBL_FONT  = ('Segoe UI', 8)      # 所有标签
        HINT_FONT = ('Segoe UI', 8)      # 提示文字（与标签统一）
        ENT_FONT  = ('Consolas', 9)      # 所有输入框

        def _entry(parent, var, show='*'):
            """统一样式的单行输入框，带显示/隐藏 Key 复选框行"""
            e = tk.Entry(parent, textvariable=var, show=show, bg=BG3, fg=WHITE,
                         insertbackground=WHITE, relief='flat', font=ENT_FONT,
                         bd=0, highlightthickness=1,
                         highlightcolor=ACCENT, highlightbackground=BORDER)
            e.pack(fill='x', padx=14, ipady=5)
            sv = tk.BooleanVar()
            tk.Checkbutton(parent, text='显示 Key', variable=sv,
                           command=lambda: e.config(show='' if sv.get() else '*'),
                           bg=BG2, fg=GRAY, selectcolor=BG3,
                           activebackground=BG2, font=LBL_FONT
                           ).pack(anchor='w', padx=14)

        # ── 主 API Key ──
        tk.Label(dlg, text='API Key（主，用于查询账户和余额）', bg=BG2, fg=GRAY,
                 font=LBL_FONT).pack(anchor='w', padx=14, pady=(10, 2))
        kv = tk.StringVar(value=self.cfg.get('api_key', ''))
        _entry(dlg, kv)

        # ── 其他 API Key（多行，每行一个，用 Entry 列表模拟以支持隐藏）──
        tk.Label(dlg, text='其他 API Key（一行一个，今日消费求和用）', bg=BG2, fg=GRAY,
                 font=LBL_FONT).pack(anchor='w', padx=14, pady=(8, 2))

        extra_keys_saved = self.cfg.get('extra_keys', [])
        extra_rows = max(3, len(extra_keys_saved))  # 至少显示 3 行
        extra_vars = []
        extra_frame = tk.Frame(dlg, bg=BG2)
        extra_frame.pack(fill='x', padx=14)

        def _add_extra_row(val=''):
            ev = tk.StringVar(value=val)
            extra_vars.append(ev)
            row_f = tk.Frame(extra_frame, bg=BG2)
            row_f.pack(fill='x', pady=(0, 2))
            ee = tk.Entry(row_f, textvariable=ev, show='*', bg=BG3, fg=WHITE,
                          insertbackground=WHITE, relief='flat', font=ENT_FONT,
                          bd=0, highlightthickness=1,
                          highlightcolor=ACCENT, highlightbackground=BORDER)
            ee.pack(side='left', fill='x', expand=True, ipady=4)
            eye_var = tk.BooleanVar()
            tk.Checkbutton(row_f, text='👁', variable=eye_var,
                           command=lambda: ee.config(show='' if eye_var.get() else '*'),
                           bg=BG2, fg=GRAY, selectcolor=BG3,
                           activebackground=BG2, font=LBL_FONT
                           ).pack(side='left', padx=(4, 0))

        for k in extra_keys_saved:
            _add_extra_row(k)
        for _ in range(max(0, 3 - len(extra_keys_saved))):
            _add_extra_row('')

        add_btn = tk.Label(dlg, text='＋ 添加一行', bg=BG2, fg=CYAN,
                           font=LBL_FONT, cursor='hand2')
        add_btn.pack(anchor='w', padx=14)
        add_btn.bind('<Button-1>', lambda _: _add_extra_row())
        tk.Label(dlg, text='每行一个 Key，留空则忽略', bg=BG2, fg=GRAY,
                 font=HINT_FONT).pack(anchor='w', padx=14, pady=(0, 2))

        # ── 管理 Key ──
        tk.Label(dlg, text='管理 Key（可选，用于模型 TOP 3 和本月明细）', bg=BG2, fg=GRAY,
                 font=LBL_FONT).pack(anchor='w', padx=14, pady=(8, 2))
        mv = tk.StringVar(value=self.cfg.get('mgmt_key', ''))
        _entry(dlg, mv)

        row = tk.Frame(dlg, bg=BG2)
        row.pack(fill='x', padx=14, pady=(8, 0))

        col1 = tk.Frame(row, bg=BG2)
        col1.pack(side='left', fill='x', expand=True, padx=(0, 6))
        tk.Label(col1, text='刷新间隔（秒）', bg=BG2, fg=GRAY,
                 font=LBL_FONT).pack(anchor='w', pady=(0, 2))
        rv = tk.StringVar(value=str(self.cfg.get('refresh_sec', 60)))
        tk.Entry(col1, textvariable=rv, bg=BG3, fg=WHITE, insertbackground=WHITE,
                 relief='flat', font=ENT_FONT, width=8, bd=0,
                 highlightthickness=1, highlightcolor=ACCENT,
                 highlightbackground=BORDER).pack(anchor='w', ipady=4)

        col2 = tk.Frame(row, bg=BG2)
        col2.pack(side='left', fill='x', expand=True)
        tk.Label(col2, text='人民币汇率（¥/$）', bg=BG2, fg=GRAY,
                 font=LBL_FONT).pack(anchor='w', pady=(0, 2))
        xv = tk.StringVar(value=str(self.cfg.get('cny_rate', 7)))
        tk.Entry(col2, textvariable=xv, bg=BG3, fg=WHITE, insertbackground=WHITE,
                 relief='flat', font=ENT_FONT, width=8, bd=0,
                 highlightthickness=1, highlightcolor=ACCENT,
                 highlightbackground=BORDER).pack(anchor='w', ipady=4)

        def _save():
            self.cfg['api_key']  = kv.get().strip()
            self.cfg['mgmt_key'] = mv.get().strip()
            # 从各行 Entry 的 StringVar 读取额外 key
            self.cfg['extra_keys'] = [v.get().strip() for v in extra_vars if v.get().strip()]
            try: self.cfg['refresh_sec'] = max(10, int(rv.get().strip()))
            except ValueError: pass
            try:
                rate = float(xv.get().strip())
                if rate > 0:
                    self.cfg['cny_rate'] = rate
            except ValueError: pass
            save_config(self.cfg)
            dlg.destroy()
            self._trigger_refresh()

        tk.Button(dlg, text='保存', bg=ACCENT, fg=WHITE, relief='flat',
                  font=('Segoe UI', 9, 'bold'), cursor='hand2',
                  command=_save).pack(fill='x', padx=14, pady=10, ipady=4)

    def _open_daily_popup(self):
        bd = getattr(self, '_daily_breakdown', {})
        no_mgmt = not self.cfg.get('mgmt_key', '').strip()

        dlg = tk.Toplevel(self.root)
        dlg.title('本月每日用量')
        dlg.configure(bg=BG2)
        dlg.resizable(False, False)
        dlg.attributes('-topmost', True)
        dlg.grab_set()
        dlg.geometry(f'380x320+{self.root.winfo_x()-10}+{self.root.winfo_y()+32}')

        # header
        hdr = tk.Frame(dlg, bg=ACCENT, height=28)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)
        tk.Label(hdr, text='📊 本月每日用量',
                 bg=ACCENT, fg=WHITE, font=('Segoe UI', 10, 'bold')).pack(side='left', padx=10)
        tk.Label(hdr, text='✕', bg=ACCENT, fg=WHITE,
                 font=('Segoe UI', 9), cursor='hand2', padx=8
                 ).pack(side='right').bind('<Button-1>', lambda _: dlg.destroy())

        if no_mgmt:
            msg = '请在设置中填写「管理 Key」后刷新数据'
            tk.Label(dlg, text=msg, bg=BG2, fg=GRAY,
                     font=('Segoe UI', 9)).pack(expand=True)
            return

        # 有管理 Key 但尚无数据：显示加载提示并触发一次刷新
        if not bd:
            loading_lbl = tk.Label(dlg, text='⏳ 正在加载数据，请稍候...', bg=BG2, fg=GRAY,
                                   font=('Segoe UI', 9))
            loading_lbl.pack(expand=True)

            def _poll_data(retries=0):
                """每 500ms 检测一次数据是否到位，最多等 20 次（10 秒）"""
                if not dlg.winfo_exists():
                    return
                new_bd = getattr(self, '_daily_breakdown', {})
                if new_bd:
                    # 数据到位，重建弹窗内容
                    dlg.destroy()
                    self._open_daily_popup()
                elif retries < 20:
                    dlg.after(500, lambda: _poll_data(retries + 1))
                else:
                    loading_lbl.config(text='暂无本月活动数据\n（activity 接口有审计延迟，\n当天消费通常第二天才出现）',
                                       fg=YELLOW)

            # 触发一次后台刷新
            if not hasattr(self, '_job'):
                self._trigger_refresh()
            _poll_data()
            return

        rate = float(self.cfg.get('cny_rate', 7))

        # column headers
        col_frame = tk.Frame(dlg, bg=BG3, padx=8, pady=4)
        col_frame.pack(fill='x')
        for txt, w, anchor in [('日期', 90, 'w'), ('Token 用量', 110, 'e'),
                                ('费用', 80, 'e'), ('占比', 60, 'e')]:
            tk.Label(col_frame, text=txt, bg=BG3, fg=GRAY,
                     font=('Segoe UI', 8, 'bold'),
                     width=w // 8, anchor=anchor).pack(side='left')

        # scrollable rows
        outer = tk.Frame(dlg, bg=BG2)
        outer.pack(fill='both', expand=True, padx=2)
        canvas = tk.Canvas(outer, bg=BG2, highlightthickness=0)
        sb = tk.Scrollbar(outer, orient='vertical', command=canvas.yview,
                          bg=BG3, troughcolor=BG2, width=8)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        inner = tk.Frame(canvas, bg=BG2)
        canvas.create_window((0, 0), window=inner, anchor='nw')
        inner.bind('<Configure>', lambda e: canvas.configure(
            scrollregion=canvas.bbox('all')))
        canvas.bind('<MouseWheel>', lambda e: canvas.yview_scroll(
            int(-1 * (e.delta / 120)), 'units'))

        days = sorted(bd.keys(), reverse=True)
        total_cost = sum(v['cost'] for v in bd.values()) or 1

        for i, day in enumerate(days):
            row_bg = BG3 if i % 2 == 0 else BG2
            row = tk.Frame(inner, bg=row_bg, padx=8, pady=3)
            row.pack(fill='x')

            cost   = bd[day]['cost']
            tokens = bd[day]['tokens']
            pct    = cost / total_cost * 100
            cost_str = f'¥{cost * rate:.2f}' if self._cny_mode else f'${cost:.2f}'
            tok_str  = f'{tokens:,}' if tokens else '—'
            bar_pct  = pct / 100

            # date
            tk.Label(row, text=day, bg=row_bg, fg=WHITE,
                     font=('Consolas', 8), width=11, anchor='w').pack(side='left')
            # tokens
            tk.Label(row, text=tok_str, bg=row_bg, fg=GRAY,
                     font=('Consolas', 8), width=13, anchor='e').pack(side='left')
            # cost
            cost_color = RED if cost > 1 else YELLOW if cost > 0.1 else WHITE
            tk.Label(row, text=cost_str, bg=row_bg, fg=cost_color,
                     font=('Consolas', 8), width=10, anchor='e').pack(side='left')
            # mini bar + pct
            bar_wrap = tk.Frame(row, bg=row_bg)
            bar_wrap.pack(side='left', fill='x', expand=True, padx=(6, 0))
            bar_track = tk.Frame(bar_wrap, bg=BG3, height=6)
            bar_track.pack(fill='x', pady=(4, 0))
            bar_track.update_idletasks()
            fill_color = RED if pct > 30 else YELLOW if pct > 10 else CYAN
            tk.Frame(bar_track, bg=fill_color, height=6,
                     width=max(2, int(bar_pct * 100))).place(x=0, y=0, relheight=1.0,
                                                              relwidth=bar_pct)
            tk.Label(row, text=f'{pct:.1f}%', bg=row_bg, fg=GRAY,
                     font=('Segoe UI', 7), width=5, anchor='e').pack(side='right')

        # footer summary
        total_tok = sum(v['tokens'] for v in bd.values())
        total_cost_real = sum(v['cost'] for v in bd.values())
        cost_total_str = f'¥{total_cost_real * rate:.2f}' if self._cny_mode \
            else f'${total_cost_real:.2f}'
        foot = tk.Frame(dlg, bg=BG3, padx=8, pady=4)
        foot.pack(fill='x')
        tk.Label(foot, text=f'本月合计：{total_tok:,} tokens  /  {cost_total_str}',
                 bg=BG3, fg=WHITE, font=('Segoe UI', 8)).pack(side='left')

    def _open_topup(self):
        import webbrowser
        webbrowser.open('https://openrouter.ai/settings/credits')

    def _toggle_pin(self):
        self._pinned = not self._pinned
        self.root.attributes('-topmost', self._pinned)
        self._pin_lbl.config(fg=WHITE if self._pinned else GRAY)
        self.cfg['pinned'] = self._pinned
        save_config(self.cfg)

    def _ctx_menu(self, e):
        m = tk.Menu(self.root, tearoff=0, bg=BG2, fg=WHITE,
                    activebackground=ACCENT, activeforeground=WHITE, bd=0)
        pin_label = '📌  取消置顶' if self._pinned else '📌  置顶显示'
        m.add_command(label=pin_label,          command=self._toggle_pin)
        m.add_command(label='⚙  设置 API Key', command=self._open_settings)
        m.add_command(label='↻  立即刷新',      command=self._trigger_refresh)
        m.add_separator()
        m.add_command(label='✕  退出',           command=self._quit)
        try:    m.tk_popup(e.x_root, e.y_root)
        finally: m.grab_release()

    # ── Data ─────────────────────────────────────────────────────────────────

    def _fetch(self):
        key = self.cfg.get('api_key', '').strip()
        if not key:
            return {'error': 'no_key'}
        headers = {'Authorization': f'Bearer {key}'}
        last_err = None
        for attempt in range(3):
            try:
                r = requests.get('https://openrouter.ai/api/v1/auth/key',
                                 headers=headers, timeout=10)
                last_err = None
                break
            except Exception as e:
                last_err = e
                if attempt < 2:
                    time.sleep(2)
        if last_err:
            return {'error': str(last_err)}

        if r.status_code == 401:
            return {'error': '401'}
        if r.status_code != 200:
            return {'error': f'HTTP {r.status_code}'}

        d = r.json().get('data', {})

        # ── 1. credits 接口：余额 + 历史总消费（账号级别，任意 key 查结果相同）──
        balance = None
        global_total_usage = 0.0
        for attempt in range(3):
            try:
                rc = requests.get('https://openrouter.ai/api/v1/credits',
                                  headers=headers, timeout=8)
                if rc.status_code == 200:
                    cd = rc.json().get('data', {})
                    granted = float(cd.get('total_credits', 0) or 0)
                    used    = float(cd.get('total_usage',   0) or 0)
                    balance = granted - used
                    global_total_usage = used
                break
            except Exception:
                if attempt < 2:
                    time.sleep(2)

        # ── 2. 今日消费：对所有配置的 key 查询 usage_daily 并求和 ──
        # usage_daily 由 OpenRouter 官方按 UTC 0点实时重置，无延迟，最准确
        all_keys = [key] + [k for k in self.cfg.get('extra_keys', []) if k]
        all_daily  = 0.0
        all_monthly = 0.0
        for k in all_keys:
            for attempt in range(2):
                try:
                    rk = requests.get('https://openrouter.ai/api/v1/auth/key',
                                      headers={'Authorization': f'Bearer {k}'},
                                      timeout=8)
                    if rk.status_code == 200:
                        kd = rk.json().get('data', {})
                        all_daily   += float(kd.get('usage_daily',   0) or 0)
                        all_monthly += float(kd.get('usage_monthly', 0) or 0)
                    break
                except Exception:
                    if attempt < 1:
                        time.sleep(1)

        # model top3 + daily breakdown — requires management key
        top3 = []
        top3_latest = ''
        daily_breakdown = {}
        # activity 接口有审计延迟（当天消费往往第二天才出现），仅用于本月明细和 TOP3，不用于今日消费
        mgmt_key = self.cfg.get('mgmt_key', '').strip()
        if mgmt_key:
            now_utc = datetime.now(tz=timezone.utc)
            month_prefix = now_utc.strftime('%Y-%m')
            date_min = now_utc.strftime('%Y-%m-01')
            for attempt in range(3):
                try:
                    rg = requests.get(
                        'https://openrouter.ai/api/v1/activity',
                        headers={'Authorization': f'Bearer {mgmt_key}'},
                        params={'date_min': date_min, 'limit': 1000},
                        timeout=10,
                    )
                    if rg.status_code == 200:
                        model_cost: dict = {}
                        daily_breakdown: dict = {}
                        latest_date = ''
                        for g in rg.json().get('data', []):
                            gdate = g.get('date', '')
                            if not gdate.startswith(month_prefix):
                                continue
                            day = gdate[:10]
                            if day > latest_date:
                                latest_date = day
                            model = g.get('model', '')
                            cost  = float(g.get('usage', 0) or 0)
                            tok_in  = int(g.get('tokens_prompt',     0) or
                                         g.get('native_tokens_prompt', 0) or 0)
                            tok_out = int(g.get('tokens_completion',     0) or
                                         g.get('native_tokens_completion', 0) or 0)
                            if model:
                                model_cost[model] = model_cost.get(model, 0) + cost
                            if day not in daily_breakdown:
                                daily_breakdown[day] = {'cost': 0.0, 'tokens': 0}
                            daily_breakdown[day]['cost']   += cost
                            daily_breakdown[day]['tokens'] += tok_in + tok_out
                        top3 = sorted(model_cost.items(), key=lambda x: x[1], reverse=True)[:3]
                        top3_latest = latest_date
                    break
                except Exception:
                    if attempt < 2:
                        time.sleep(2)

        return {
            'ok':                     True,
            'limit':                  d.get('limit'),
            'limit_rem':              d.get('limit_remaining'),
            'balance':                balance,
            'label':                  d.get('label', ''),
            'top3':                   top3,
            'top3_latest_date':       top3_latest,
            'daily_breakdown':        daily_breakdown,
            'all_daily':              all_daily,             # 所有 key 的 usage_daily 求和，实时今日消费
            'all_monthly':            all_monthly,           # 所有 key 的 usage_monthly 求和
            'global_total_usage':     global_total_usage,    # credits 接口账户历史总消费
        }

    # ── UI update ─────────────────────────────────────────────────────────────

    def _update_ui(self, data):
        now = now_beijing().strftime('%H:%M:%S')
        self._last_data = data

        if data.get('error') == 'no_key':
            self._dot.config(fg=YELLOW); self._status.config(text='未设置 Key', fg=YELLOW)
            self._island_logo.config(fg=YELLOW)
            self._island_bal_lbl.config(text='未设置 Key', fg=YELLOW)
            self._island_sep.pack_forget()
            self._island_daily_lbl.pack_forget()
            return
        if data.get('error') == '401':
            self._dot.config(fg=RED);    self._status.config(text='Key 无效', fg=RED)
            self._island_logo.config(fg=RED)
            self._island_bal_lbl.config(text='Key 无效', fg=RED)
            self._island_sep.pack_forget()
            self._island_daily_lbl.pack_forget()
            self._time_lbl.config(text=f'更新: {now}'); return
        if data.get('error'):
            self._dot.config(fg=RED);    self._status.config(text='网络错误', fg=RED)
            self._island_logo.config(fg=RED)
            self._island_bal_lbl.config(text='网络错误', fg=RED)
            self._island_sep.pack_forget()
            self._island_daily_lbl.pack_forget()
            self._time_lbl.config(text=f'更新: {now}'); return

        self._daily_breakdown = data.get('daily_breakdown', {})
        self._dot.config(fg=GREEN)
        self._status.config(text='已连接', fg=GREEN)
        self._island_logo.config(fg=GREEN)

        # 恢复分割线和今日消费的显示
        self._island_sep.pack(side='left', padx=3)
        self._island_daily_lbl.pack(side='left')

        # 今日消费：所有 key 的 usage_daily 求和（OpenRouter 官方实时，UTC 0点重置）
        daily = data.get('all_daily', 0.0)

        # 本月消费：有 activity 数据时用全账号明细，否则用所有 key 的 usage_monthly 求和
        if self._daily_breakdown:
            monthly = sum(v['cost'] for v in self._daily_breakdown.values())
        else:
            monthly = data.get('all_monthly', 0.0)

        # daily — always red
        self._vals['daily'].config(
            text=self._fmt(daily),
            fg=RED if daily > 0 else GRAY)

        # balance
        bal = data.get('balance')
        if bal is not None:
            bal_color = RED if bal < 1 else YELLOW if bal < 5 else GREEN
            bal_text = self._fmt2(bal) + (' !' if bal < 1 else '')
            self._vals['balance'].config(text=bal_text, fg=bal_color)
            bal_str = self._fmt2(bal)
        else:
            self._vals['balance'].config(text='——', fg=GRAY)
            bal_color = GRAY
            bal_str = '——'

        # 灵动岛显示：首先是账户余额信息，然后再是今日消费。保留各自的颜色，字体调小，空格减少
        self._island_bal_lbl.config(text=f'余额:{bal_str}', fg=bal_color)
        self._island_daily_lbl.config(text=f'今日:{self._fmt(daily)}', fg=RED if daily > 0 else GRAY)

        # monthly
        self._vals['monthly'].config(text=self._fmt(monthly), fg=WHITE)
        limit     = data.get('limit')
        limit_rem = data.get('limit_rem')
        if limit and limit > 0 and limit_rem is not None:
            used = limit - limit_rem
            pct  = used / limit * 100
            pct_color = RED if pct >= 90 else YELLOW if pct >= 70 else CYAN
            self._monthly_pct.config(
                text=f'{pct:.1f}%  限额 {self._fmt2(limit)}', fg=pct_color)
            self._monthly_bar.config(bg=pct_color)
            self._monthly_bar.place(relwidth=min(pct / 100, 1.0))
        else:
            self._monthly_pct.config(text='无额度限制', fg=GRAY)
            self._monthly_bar.place(relwidth=0)

        # 累计消费：使用 credits 接口的 total_usage（该 key 的历史总消费）
        total = data.get('global_total_usage') or data.get('usage', 0)
        self._vals['total'].config(
            text=self._fmt(total),
            fg=RED if total > 20 else YELLOW if total > 5 else WHITE)

        top3 = data.get('top3', [])
        latest_date = data.get('top3_latest_date', '')
        title = f'本月模型 TOP 3  截至{latest_date}' if latest_date else '本月模型 TOP 3'
        self._top3_title.config(text=title)
        rate = float(self.cfg.get('cny_rate', 7))
        no_mgmt = not self.cfg.get('mgmt_key', '').strip()
        for i, (name_lbl, cost_lbl) in enumerate(self._top3_lbls):
            if i == 0 and no_mgmt:
                name_lbl.config(text='需在设置中填写管理 Key', fg=GRAY)
                cost_lbl.config(text='', fg=GRAY)
            elif i < len(top3):
                model, cost = top3[i]
                short = model.split('/')[-1].removeprefix('claude-')[:28]
                cost_str = f'¥{cost * rate:.2f}' if self._cny_mode else f'${cost:.2f}'
                name_lbl.config(text=short, fg=WHITE)
                cost_lbl.config(text=cost_str, fg=CYAN)
            else:
                name_lbl.config(text='——' if not no_mgmt else '', fg=GRAY)
                cost_lbl.config(text='', fg=GRAY)

        self._time_lbl.config(text=f'↻ {now}   右键更多选项')

    # ── Refresh ───────────────────────────────────────────────────────────────

    def _trigger_refresh(self):
        if hasattr(self, '_job'):
            self.root.after_cancel(self._job)
        self._dot.config(fg=YELLOW)
        self._status.config(text='刷新中...')
        if hasattr(self, '_island_logo'):
            self._island_logo.config(fg=YELLOW)
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        data = self._fetch()
        self.root.after(0, lambda: self._on_fetch_done(data))

    def _on_fetch_done(self, data):
        self._update_ui(data)
        ms = max(10, self.cfg.get('refresh_sec', 60)) * 1000
        self._job = self.root.after(ms, self._trigger_refresh)

    def _schedule_refresh(self):
        self._trigger_refresh()

    def _quit(self):
        if hasattr(self, '_job'):
            self.root.after_cancel(self._job)
        self.root.destroy()


if __name__ == '__main__':
    Dashboard()
