import tkinter as tk
import requests
import json
import threading
import time
import os
from datetime import datetime

BG     = '#0d1117'
BG2    = '#161b22'
BG3    = '#21262d'
ACCENT = '#1f6feb'
GREEN  = '#3fb950'
YELLOW = '#d29922'
RED    = '#f85149'
WHITE  = '#e6edf3'
GRAY   = '#8b949e'
BORDER = '#30363d'
CYAN   = '#58a6ff'
PURPLE = '#bc8cff'

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')


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
        self.root.attributes('-alpha', self.cfg.get('alpha', 0.93))
        self.root.configure(bg=BG)

        self._col_expanded = self.cfg.get('col_expanded', True)
        self._cny_mode = self.cfg.get('cny_mode', False)
        self._W_full = 370
        self._W_slim = 248
        self._H = 175
        W = self._W_full if self._col_expanded else self._W_slim
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = self.cfg['x'] if self.cfg['x'] is not None else sw - W - 20
        y = self.cfg['y'] if self.cfg['y'] is not None else 60
        self.root.geometry(f'{W}x{self._H}+{max(0,x)}+{max(0,y)}')

        self._dx = self._dy = 0
        self.root.bind('<Button-1>',        self._drag_start)
        self.root.bind('<B1-Motion>',       self._drag_move)
        self.root.bind('<ButtonRelease-1>', self._drag_end)
        self.root.bind('<Button-3>',        self._ctx_menu)

    def _drag_start(self, e): self._dx, self._dy = e.x, e.y
    def _drag_move(self, e):
        self.root.geometry(f'+{self.root.winfo_x()+e.x-self._dx}+{self.root.winfo_y()+e.y-self._dy}')
    def _drag_end(self, e):
        self.cfg['x'], self.cfg['y'] = self.root.winfo_x(), self.root.winfo_y()
        save_config(self.cfg)

    # ── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── title bar ──
        bar = tk.Frame(self.root, bg=ACCENT, height=28)
        bar.pack(fill='x')
        bar.pack_propagate(False)

        tk.Label(bar, text=' ⚡ OpenRouter',
                 bg=ACCENT, fg=WHITE, font=('Segoe UI', 11, 'bold')
                 ).pack(side='left', pady=3)

        self._dot    = tk.Label(bar, text='●', bg=ACCENT, fg=GRAY, font=('Segoe UI', 7))
        self._status = tk.Label(bar, text='...', bg=ACCENT, fg=WHITE, font=('Segoe UI', 7))
        self._dot.pack(side='left', padx=(6, 1))
        self._status.pack(side='left')

        # CNY/USD toggle — left side so it's always visible when collapsed
        cny_fg = YELLOW if self._cny_mode else GRAY
        self._cny_btn = tk.Label(bar, text='¥', bg=ACCENT, fg=cny_fg,
                                  font=('Segoe UI', 8, 'bold'), cursor='hand2', padx=4)
        self._cny_btn.pack(side='left', padx=(4, 0))
        self._cny_btn.bind('<Button-1>', lambda _: self._toggle_cny())
        self._cny_btn.bind('<Enter>',    lambda _: self._cny_btn.config(fg=WHITE))
        self._cny_btn.bind('<Leave>',    lambda _: self._cny_btn.config(
                                             fg=YELLOW if self._cny_mode else GRAY))

        self._col2_cells = []

        # ✕ 最右侧 — 先 pack 保证在最右边
        close_btn = tk.Label(bar, text='✕', bg=ACCENT, fg=WHITE,
                             font=('Segoe UI', 9), cursor='hand2', padx=5)
        close_btn.pack(side='right', padx=(0, 2))
        close_btn.bind('<Button-1>', lambda _: self._quit())
        close_btn.bind('<Enter>',    lambda _: close_btn.config(fg=RED))
        close_btn.bind('<Leave>',    lambda _: close_btn.config(fg=WHITE))

        # col toggle
        arrow = '›' if not self._col_expanded else '‹'
        self._col_btn = tk.Label(bar, text=arrow, bg=ACCENT, fg=WHITE,
                                  font=('Segoe UI', 11, 'bold'), cursor='hand2', padx=4)
        self._col_btn.pack(side='right', padx=(0, 0))
        self._col_btn.bind('<Button-1>', lambda _: self._toggle_col())
        self._col_btn.bind('<Enter>',    lambda _: self._col_btn.config(fg=YELLOW))
        self._col_btn.bind('<Leave>',    lambda _: self._col_btn.config(fg=WHITE))

        # pin button
        self._pin_lbl = tk.Label(bar, text='📌', bg=ACCENT,
                                  fg=WHITE if self._pinned else GRAY,
                                  font=('Segoe UI', 8), cursor='hand2', padx=4)
        self._pin_lbl.pack(side='right', padx=(0, 0))
        self._pin_lbl.bind('<Button-1>', lambda _: self._toggle_pin())
        self._pin_lbl.bind('<Enter>',    lambda _: self._pin_lbl.config(fg=WHITE))
        self._pin_lbl.bind('<Leave>',    lambda _: self._pin_lbl.config(
                                             fg=WHITE if self._pinned else GRAY))

        for txt, cmd, hv, fs in [('⚙', self._open_settings,  WHITE, 9),
                                   ('↻', self._trigger_refresh, WHITE, 12)]:
            lb = tk.Label(bar, text=txt, bg=ACCENT, fg=WHITE,
                          font=('Segoe UI', fs), cursor='hand2', padx=4)
            lb.pack(side='right')
            lb.bind('<Button-1>', lambda _, c=cmd: c())
            lb.bind('<Enter>',    lambda _, l=lb, c=hv: l.config(fg=c))
            lb.bind('<Leave>',    lambda _, l=lb: l.config(fg=WHITE))

        # ── metric grid (2 rows × 3 cols) ──
        grid = tk.Frame(self.root, bg=BG, padx=5, pady=5)
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
            wrap = tk.Frame(grid, bg=acolor)
            wrap.grid(row=row, column=col, padx=3, pady=3, sticky='nsew')
            cell = tk.Frame(wrap, bg=BG2, padx=7, pady=4)
            cell.pack(fill='both', expand=True, padx=(2, 0))
            tk.Label(cell, text=label, bg=BG2, fg=GRAY,
                     font=('Segoe UI', 8), anchor='w').pack(anchor='w')
            v = tk.Label(cell, text='——', bg=BG2, fg=WHITE,
                         font=('Consolas', 13, 'bold'), anchor='w')
            v.pack(anchor='w')
            self._vals[key] = v
            if col == 2:
                self._col2_cells.append(wrap)

        # top3 卡片占 (1,1)
        top3_wrap = tk.Frame(grid, bg=PURPLE)
        top3_wrap.grid(row=1, column=1, padx=3, pady=3, sticky='nsew')
        top3_cell = tk.Frame(top3_wrap, bg=BG2, padx=6, pady=3)
        top3_cell.pack(fill='both', expand=True, padx=(2, 0))
        top3_cell.columnconfigure(1, weight=1)
        self._top3_title = tk.Label(top3_cell, text='本月模型 TOP 3', bg=BG2, fg=GRAY,
                                     font=('Segoe UI', 7), anchor='w')
        self._top3_title.grid(row=0, column=0, columnspan=3, sticky='w', pady=(0, 1))
        self._top3_lbls = []
        medals = ['①', '②', '③']
        for i in range(3):
            tk.Label(top3_cell, text=medals[i], bg=BG2, fg=GRAY,
                     font=('Segoe UI', 7)).grid(row=i + 1, column=0, sticky='w')
            name_lbl = tk.Label(top3_cell, text='——', bg=BG2, fg=GRAY,
                                font=('Segoe UI', 7), anchor='w')
            name_lbl.grid(row=i + 1, column=1, sticky='w', padx=(2, 0))
            cost_lbl = tk.Label(top3_cell, text='', bg=BG2, fg=GRAY,
                                font=('Consolas', 7), anchor='e')
            cost_lbl.grid(row=i + 1, column=2, sticky='e')
            self._top3_lbls.append((name_lbl, cost_lbl))

        # 充值按钮占 (1,2)
        wrap2 = tk.Frame(grid, bg=ACCENT)
        wrap2.grid(row=1, column=2, padx=3, pady=3, sticky='nsew')
        topup_cell = tk.Frame(wrap2, bg=BG2, padx=7, pady=4)
        topup_cell.pack(fill='both', expand=True, padx=(2, 0))
        tk.Label(topup_cell, text='充值', bg=BG2, fg=GRAY,
                 font=('Segoe UI', 8)).pack(anchor='w')
        topup_btn = tk.Label(topup_cell, text='+ 前往充值', bg=ACCENT, fg=WHITE,
                             font=('Segoe UI', 8, 'bold'), cursor='hand2',
                             padx=6, pady=1, relief='flat')
        topup_btn.pack(anchor='w')
        topup_btn.bind('<Button-1>', lambda _: self._open_topup())
        topup_btn.bind('<Enter>',    lambda _: topup_btn.config(bg='#388bfd'))
        topup_btn.bind('<Leave>',    lambda _: topup_btn.config(bg=ACCENT))
        self._col2_cells.append(wrap2)

        self._grid = grid
        grid.rowconfigure((0, 1), weight=1, uniform='row')

        # apply initial collapsed state
        if not self._col_expanded:
            self._apply_col_state(animate=False)

        # footer
        footer = tk.Frame(self.root, bg=BG3, height=1)
        footer.pack(fill='x')
        self._time_lbl = tk.Label(self.root, text='', bg=BG, fg=GRAY,
                                   font=('Segoe UI', 7))
        self._time_lbl.pack(side='bottom', pady=(0, 3))

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
        return f'${usd:.4f}'

    def _fmt2(self, usd):
        """Format with 2 decimal places (for balance / limit)."""
        rate = float(self.cfg.get('cny_rate', 7))
        if self._cny_mode:
            return f'¥{usd * rate:.2f}'
        return f'${usd:.2f}'

    # ── Column toggle ────────────────────────────────────────────────────────

    def _toggle_col(self):
        self._col_expanded = not self._col_expanded
        self._apply_col_state(animate=True)
        self.cfg['col_expanded'] = self._col_expanded
        save_config(self.cfg)

    def _apply_col_state(self, animate=False):
        if self._col_expanded:
            self._grid.columnconfigure(2, weight=1, uniform='col', minsize=0)
            for cell in self._col2_cells:
                cell.grid()
            W = self._W_full
            self._col_btn.config(text='‹')
        else:
            for cell in self._col2_cells:
                cell.grid_remove()
            self._grid.columnconfigure(2, weight=0, uniform='', minsize=0)
            W = self._W_slim
            self._col_btn.config(text='›')
        x, y = self.root.winfo_x(), self.root.winfo_y()
        self.root.geometry(f'{W}x{self._H}+{x}+{y}')

    # ── Settings ─────────────────────────────────────────────────────────────

    def _open_settings(self):
        dlg = tk.Toplevel(self.root)
        dlg.title('设置')
        dlg.configure(bg=BG2)
        dlg.resizable(False, False)
        dlg.attributes('-topmost', True)
        dlg.grab_set()
        dlg.geometry(f'320x300+{self.root.winfo_x()+20}+{self.root.winfo_y()+32}')

        tk.Label(dlg, text='API Key', bg=BG2, fg=GRAY,
                 font=('Segoe UI', 8)).pack(anchor='w', padx=14, pady=(10,2))
        kv = tk.StringVar(value=self.cfg.get('api_key', ''))
        ke = tk.Entry(dlg, textvariable=kv, show='*', bg=BG3, fg=WHITE,
                      insertbackground=WHITE, relief='flat', font=('Consolas', 9),
                      bd=0, highlightthickness=1,
                      highlightcolor=ACCENT, highlightbackground=BORDER)
        ke.pack(fill='x', padx=14, ipady=5)

        sv = tk.BooleanVar()
        tk.Checkbutton(dlg, text='显示 Key', variable=sv,
                       command=lambda: ke.config(show='' if sv.get() else '*'),
                       bg=BG2, fg=GRAY, selectcolor=BG3,
                       activebackground=BG2, font=('Segoe UI', 8)
                       ).pack(anchor='w', padx=14)

        tk.Label(dlg, text='管理 Key（可选，用于模型 TOP 3）', bg=BG2, fg=GRAY,
                 font=('Segoe UI', 8)).pack(anchor='w', padx=14, pady=(6, 2))
        mv = tk.StringVar(value=self.cfg.get('mgmt_key', ''))
        tk.Entry(dlg, textvariable=mv, show='*', bg=BG3, fg=WHITE,
                 insertbackground=WHITE, relief='flat', font=('Consolas', 9),
                 bd=0, highlightthickness=1,
                 highlightcolor=ACCENT, highlightbackground=BORDER
                 ).pack(fill='x', padx=14, ipady=5)

        row = tk.Frame(dlg, bg=BG2)
        row.pack(fill='x', padx=14, pady=(6, 0))

        col1 = tk.Frame(row, bg=BG2)
        col1.pack(side='left', fill='x', expand=True, padx=(0, 6))
        tk.Label(col1, text='刷新间隔（秒）', bg=BG2, fg=GRAY,
                 font=('Segoe UI', 8)).pack(anchor='w', pady=(0, 2))
        rv = tk.StringVar(value=str(self.cfg.get('refresh_sec', 60)))
        tk.Entry(col1, textvariable=rv, bg=BG3, fg=WHITE, insertbackground=WHITE,
                 relief='flat', font=('Consolas', 9), width=8, bd=0,
                 highlightthickness=1, highlightcolor=ACCENT,
                 highlightbackground=BORDER).pack(anchor='w', ipady=4)

        col2 = tk.Frame(row, bg=BG2)
        col2.pack(side='left', fill='x', expand=True)
        tk.Label(col2, text='人民币汇率（¥/$）', bg=BG2, fg=GRAY,
                 font=('Segoe UI', 8)).pack(anchor='w', pady=(0, 2))
        xv = tk.StringVar(value=str(self.cfg.get('cny_rate', 7)))
        tk.Entry(col2, textvariable=xv, bg=BG3, fg=WHITE, insertbackground=WHITE,
                 relief='flat', font=('Consolas', 9), width=8, bd=0,
                 highlightthickness=1, highlightcolor=ACCENT,
                 highlightbackground=BORDER).pack(anchor='w', ipady=4)

        def _save():
            self.cfg['api_key']  = kv.get().strip()
            self.cfg['mgmt_key'] = mv.get().strip()
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

        # credits balance
        balance = None
        for attempt in range(3):
            try:
                rc = requests.get('https://openrouter.ai/api/v1/credits',
                                  headers=headers, timeout=8)
                if rc.status_code == 200:
                    cd = rc.json().get('data', {})
                    granted = float(cd.get('total_credits', 0) or 0)
                    used    = float(cd.get('total_usage',   0) or 0)
                    balance = granted - used
                break
            except Exception:
                if attempt < 2:
                    time.sleep(2)

        # model top3 — requires management key
        top3 = []
        top3_latest = ''
        mgmt_key = self.cfg.get('mgmt_key', '').strip()
        if mgmt_key:
            date_min = datetime.now().strftime('%Y-%m-01')
            for attempt in range(3):
                try:
                    rg = requests.get(
                        'https://openrouter.ai/api/v1/activity',
                        headers={'Authorization': f'Bearer {mgmt_key}'},
                        params={'date_min': date_min, 'limit': 1000},
                        timeout=10,
                    )
                    if rg.status_code == 200:
                        month_prefix = datetime.now().strftime('%Y-%m')
                        model_cost: dict = {}
                        latest_date = ''
                        for g in rg.json().get('data', []):
                            gdate = g.get('date', '')
                            if not gdate.startswith(month_prefix):
                                continue
                            if gdate[:10] > latest_date:
                                latest_date = gdate[:10]
                            model = g.get('model', '')
                            cost  = float(g.get('usage', 0) or 0)
                            if model:
                                model_cost[model] = model_cost.get(model, 0) + cost
                        top3 = sorted(model_cost.items(), key=lambda x: x[1], reverse=True)[:3]
                        top3_latest = latest_date
                    break
                except Exception:
                    if attempt < 2:
                        time.sleep(2)

        return {
            'ok':            True,
            'usage':         float(d.get('usage',           0) or 0),
            'usage_daily':   float(d.get('usage_daily',     0) or 0),
            'usage_monthly': float(d.get('usage_monthly',   0) or 0),
            'limit':         d.get('limit'),
            'limit_rem':     d.get('limit_remaining'),
            'balance':       balance,
            'label':         d.get('label', ''),
            'top3':              top3,
            'top3_latest_date':  top3_latest,
        }

    # ── UI update ─────────────────────────────────────────────────────────────

    def _update_ui(self, data):
        now = datetime.now().strftime('%H:%M:%S')
        self._last_data = data

        if data.get('error') == 'no_key':
            self._dot.config(fg=YELLOW); self._status.config(text='未设置 Key', fg=YELLOW)
            return
        if data.get('error') == '401':
            self._dot.config(fg=RED);    self._status.config(text='Key 无效', fg=RED)
            self._time_lbl.config(text=f'更新: {now}'); return
        if data.get('error'):
            self._dot.config(fg=RED);    self._status.config(text='网络错误', fg=RED)
            self._time_lbl.config(text=f'更新: {now}'); return

        self._dot.config(fg=GREEN)
        self._status.config(text='已连接', fg=GREEN)

        # balance
        bal = data.get('balance')
        if bal is not None:
            bal_color = RED if bal < 1 else YELLOW if bal < 5 else GREEN
            bal_text = self._fmt2(bal) + (' !' if bal < 1 else '')
            self._vals['balance'].config(text=bal_text, fg=bal_color)
        else:
            self._vals['balance'].config(text='——', fg=GRAY)

        # daily — always red
        daily = data['usage_daily']
        self._vals['daily'].config(
            text=self._fmt(daily),
            fg=RED if daily > 0 else GRAY)

        # monthly
        self._vals['monthly'].config(text=self._fmt(data['usage_monthly']), fg=WHITE)

        # total cumulative
        total = data['usage']
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
                cost_str = f'¥{cost * rate:.3f}' if self._cny_mode else f'${cost:.4f}'
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
