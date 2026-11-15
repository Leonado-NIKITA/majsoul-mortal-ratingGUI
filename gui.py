"""雀魂 rating 跑谱工具 - 桌面图形界面 (tkinter, 无额外依赖)."""

from __future__ import annotations

import argparse
import asyncio
import os
import pathlib
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import mahjong_rating as mr
import store
from version import __version__


app_dir = store.app_dir  # 打包后是 exe 所在目录, 开发时是脚本所在目录


class QueueWriter:
    def __init__(self, q: queue.Queue) -> None:
        self.q = q

    def write(self, s: str) -> int:
        if s:
            self.q.put(s)
        return len(s)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"雀魂 Rating 跑谱工具 v{__version__} (Mortal {mr.MODEL_TAG})")
        ico = pathlib.Path(getattr(sys, "_MEIPASS", "")) / "app.ico" if getattr(sys, "frozen", False) \
            else pathlib.Path(__file__).with_name("installer") / "app.ico"
        if ico.exists():
            try:
                self.iconbitmap(default=str(ico))
            except tk.TclError:
                pass
        self.geometry("1100x720")
        self.minsize(900, 600)

        self.q: queue.Queue = queue.Queue()
        self.thread: threading.Thread | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.task: asyncio.Task | None = None
        self.stopping = False
        self.photo = None
        self.last_png: pathlib.Path | None = None
        self.last_img = None

        self._build()
        self.after(100, self._poll)

    # ---------------- UI ----------------
    def _build(self) -> None:
        form = ttk.LabelFrame(self, text="参数", padding=8)
        form.pack(fill="x", padx=8, pady=6)

        cfg = store.load_settings()
        self.history: list[dict] = [h for h in cfg.get("history") or []
                                    if isinstance(h, dict) and str(h.get("ident") or "").strip()]
        if "history" not in cfg:  # 第一次用新版: 把本地已有数据的玩家放进下拉
            self.history = [{"by": "id", "ident": str(uid), "uid": uid, "nickname": name}
                            for uid, name in store.list_players(store.default_root())][:self.HISTORY_MAX]
        if not cfg.get("ident") and self.history:
            cfg["ident"], cfg["by"] = self.history[0]["ident"], self.history[0].get("by", "id")
        self.by = tk.StringVar(value=cfg.get("by") if cfg.get("by") in ("id", "name") else "id")
        self.ident = tk.StringVar(value=str(cfg.get("ident") or ""))
        self.games = tk.IntVar(value=int(cfg.get("games") or 20))
        self.conc = tk.IntVar(value=int(cfg.get("concurrency") or 3))
        self.tscale = tk.DoubleVar(value=float(cfg.get("timeout_scale") or 1.0))
        self.out = tk.StringVar(value=str(cfg.get("out") or app_dir() / "rating_out"))
        self.fresh = tk.BooleanVar(value=False)  # 清缓存是一次性操作, 不记

        ttk.Radiobutton(form, text="UID", variable=self.by, value="id").grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(form, text="昵称", variable=self.by, value="name").grid(row=0, column=1, sticky="w")
        self.cb_ident = ttk.Combobox(form, textvariable=self.ident, width=30, postcommand=self._fill_history)
        self.cb_ident.grid(row=0, column=2, columnspan=2, sticky="we", padx=4)
        self.cb_ident.bind("<<ComboboxSelected>>", self._pick_history)
        self.cb_ident.bind("<Return>", lambda e: self.start())
        self.cb_ident.bind("<Delete>", self._forget_history)
        self._fill_history()

        ttk.Label(form, text="局数").grid(row=0, column=4, sticky="e")
        ttk.Spinbox(form, from_=1, to=500, textvariable=self.games, width=6).grid(row=0, column=5, padx=4)
        ttk.Label(form, text="并发").grid(row=0, column=6, sticky="e")
        ttk.Spinbox(form, from_=1, to=8, textvariable=self.conc, width=4).grid(row=0, column=7, padx=4)

        ttk.Label(form, text="场次").grid(row=1, column=0, sticky="nw", pady=4)
        mode_box = ttk.Frame(form)
        mode_box.grid(row=1, column=1, columnspan=7, sticky="w", pady=4)
        self.mode_vars: dict[str, tk.BooleanVar] = {}
        saved_modes = set(cfg.get("modes") or ["玉"])
        for i, name in enumerate(mr.MODES):
            v = tk.BooleanVar(value=(name in saved_modes))
            self.mode_vars[name] = v
            ttk.Checkbutton(mode_box, text=name, variable=v).grid(row=i // 6, column=i % 6, sticky="w", padx=4)

        ttk.Label(form, text="输出目录").grid(row=2, column=0, sticky="e")
        ttk.Entry(form, textvariable=self.out).grid(row=2, column=1, columnspan=5, sticky="we", padx=4)
        ttk.Button(form, text="浏览...", command=self._browse).grid(row=2, column=6, columnspan=2)
        ttk.Checkbutton(form, text="清缓存重跑 (--fresh)", variable=self.fresh).grid(
            row=3, column=1, columnspan=3, sticky="w")
        ttk.Label(form, text="超时倍数").grid(row=3, column=4, sticky="e")
        ttk.Spinbox(form, from_=0.5, to=10, increment=0.5, textvariable=self.tscale, width=6,
                    format="%.1f").grid(row=3, column=5, padx=4)
        self.tscale_hint = tk.StringVar()
        ttk.Label(form, textvariable=self.tscale_hint, foreground="#888").grid(
            row=3, column=6, columnspan=2, sticky="w")
        self.tscale.trace_add("write", lambda *_: self._update_tscale_hint())
        self._update_tscale_hint()
        form.columnconfigure(3, weight=1)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8)
        self.btn_run = ttk.Button(bar, text="开始", command=self.start)
        self.btn_run.pack(side="left")
        self.btn_stop = ttk.Button(bar, text="停止", command=self.stop, state="disabled")
        self.btn_stop.pack(side="left", padx=6)
        ttk.Button(bar, text="打开输出目录", command=self._open_out).pack(side="left")
        ttk.Button(bar, text="玩家数据", command=self._open_players).pack(side="left", padx=(6, 0))
        self.btn_img = ttk.Button(bar, text="用系统查看器打开图", command=self._open_png, state="disabled")
        self.btn_img.pack(side="left", padx=6)
        self.status = tk.StringVar(value="就绪")
        ttk.Label(bar, textvariable=self.status).pack(side="right")

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=6)
        self.nb = nb

        log_frame = ttk.Frame(nb)
        self.log = tk.Text(log_frame, wrap="none", font=("Consolas", 10), state="disabled")
        sb = ttk.Scrollbar(log_frame, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log.pack(fill="both", expand=True)
        nb.add(log_frame, text="日志")

        img_frame = ttk.Frame(nb)
        self.canvas = tk.Label(img_frame, text="跑完后在这里显示图表", anchor="center")
        self.canvas.pack(fill="both", expand=True)
        img_frame.bind("<Configure>", lambda e: self._render_image())
        nb.add(img_frame, text="结果图")
        self.img_frame = img_frame

        self._build_diff_tab(nb)

    # ---------------- 差异报告 tab ----------------
    DIFF_COLS = [("sel", "选", 34), ("when", "时间", 118), ("mode", "场次", 64),
                 ("rank", "顺位", 46), ("score", "点数", 64), ("pt", "pt", 50),
                 ("table", "终局四家 (按顺位)", 250), ("rating", "Rating", 60),
                 ("acc", "AI 一致率", 110), ("diff", "差异", 50), ("new", "", 46)]

    def _build_diff_tab(self, nb: ttk.Notebook) -> None:
        tab = ttk.Frame(nb, padding=6)
        nb.add(tab, text="差异报告")
        self.diff_tab = tab
        self.diff_store: store.PlayerStore | None = None
        self.diff_sel: set[str] = set()
        self.diff_players: list[tuple[int, str]] = []

        top = ttk.Frame(tab)
        top.pack(fill="x")
        ttk.Label(top, text="玩家").pack(side="left")
        self.diff_player = tk.StringVar()
        self.cb_player = ttk.Combobox(top, textvariable=self.diff_player, state="readonly", width=30)
        self.cb_player.pack(side="left", padx=4)
        self.cb_player.bind("<<ComboboxSelected>>", lambda e: self._load_library(default=True))
        ttk.Button(top, text="刷新", command=lambda: self._refresh_players(keep=True)).pack(side="left")
        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(top, text="选新增", command=self._sel_new).pack(side="left")
        ttk.Button(top, text="全选", command=self._sel_all).pack(side="left", padx=4)
        ttk.Button(top, text="全不选", command=self._sel_none).pack(side="left")
        ttk.Button(top, text="打开上次报告", command=self._open_diff).pack(side="right")
        self.btn_gen = ttk.Button(top, text="生成并打开报告", command=self._gen_diff)
        self.btn_gen.pack(side="right", padx=6)

        self.diff_info = tk.StringVar(value="")
        ttk.Label(tab, textvariable=self.diff_info, foreground="#555").pack(fill="x", pady=(6, 2))

        box = ttk.Frame(tab)
        box.pack(fill="both", expand=True)
        tv = ttk.Treeview(box, columns=[c for c, _, _ in self.DIFF_COLS], show="headings",
                          selectmode="extended")
        for cid, text, w in self.DIFF_COLS:
            tv.heading(cid, text=text)
            anchor = "w" if cid in ("when", "table", "acc") else "center"
            tv.column(cid, width=w, anchor=anchor, stretch=cid == "table")
        tv.tag_configure("r1", background="#e8f5e9")
        tv.tag_configure("r2", background="#f3f8fd")
        tv.tag_configure("r3", background="#fffbe6")
        tv.tag_configure("r4", background="#fdecea")
        sb = ttk.Scrollbar(box, command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        tv.pack(fill="both", expand=True)
        tv.bind("<Button-1>", self._on_tree_click)
        tv.bind("<space>", lambda e: self._toggle(tv.selection()))
        tv.bind("<Double-1>", lambda e: "break")
        self.tree = tv
        ttk.Label(tab, foreground="#888",
                  text="点「选」列勾选/取消；可框选或 Ctrl/Shift 多选后按空格批量切换。"
                       "默认勾选上次运行新增的对局。").pack(fill="x", pady=(4, 0))
        self._refresh_players()

    def _refresh_players(self, keep: bool = False) -> None:
        cur = self.diff_store.uid if (keep and self.diff_store) else None
        self.diff_players = store.list_players(store.default_root())
        labels = [f"{name or '?'} ({uid})" for uid, name in self.diff_players]
        self.cb_player.configure(values=labels)
        if not labels:
            self.diff_player.set("")
            self.diff_store = None
            self._fill_tree([])
            self.diff_info.set("players/ 里还没有数据, 先跑一次")
            return
        uids = [u for u, _ in self.diff_players]
        idx = uids.index(cur) if cur in uids else 0
        self.cb_player.current(idx)
        self._load_library(default=not keep)

    def _load_library(self, default: bool) -> None:
        i = self.cb_player.current()
        if i < 0 or i >= len(self.diff_players):
            return
        uid = self.diff_players[i][0]
        old_sel = set(self.diff_sel) if (not default and self.diff_store
                                         and self.diff_store.uid == uid) else None
        self.diff_store = store.PlayerStore(store.default_root(), uid)
        self.diff_lib = self.diff_store.library()
        have = {g["uuid"] for g in self.diff_lib}
        if old_sel is None:
            uuids, self.diff_label = self.diff_store.default_selection()
            self.diff_sel = set(uuids)
        else:
            self.diff_sel = old_sel & have
        self._fill_tree(self.diff_lib)

    def _game_row(self, g: dict) -> tuple:
        st = self.diff_store
        uid = st.uid if st else 0
        rec = (st.records.get(g["uuid"]) if st else None) or {}
        players = rec.get("players") or []
        table = ""
        if players:
            order = sorted(range(len(players)),
                           key=lambda i: (-(players[i].get("score") or 0), i))
            table = "  ".join(
                ("▶" if players[i].get("accountId") == uid else "") + str(players[i].get("score", "?"))
                for i in order)
        pt = g.get("pt_delta")
        acc = g.get("accordance")
        acc_s = (f"{g.get('accordance_detail', '')} {acc * 100:.1f}%" if acc is not None else "-")
        new = g["uuid"] in set(st.new_uuids()) if st else False
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(g.get("start_time") or 0))
        return ("☑" if g["uuid"] in self.diff_sel else "☐", when,
                mr.MODE_BY_ID.get(g.get("mode_id"), g.get("mode_id")),
                f"{g.get('rank', '-')}位", g.get("score", "-"),
                "-" if pt is None else f"{pt:+d}", table,
                "-" if g.get("rating") is None else g["rating"], acc_s,
                "-" if g.get("diff_count") is None else g["diff_count"], "新增" if new else "")

    def _fill_tree(self, lib: list[dict]) -> None:
        self.tree.delete(*self.tree.get_children())
        for g in lib:
            self.tree.insert("", "end", iid=g["uuid"], values=self._game_row(g),
                             tags=(f"r{g.get('rank')}",))
        self._update_info()

    def _update_info(self) -> None:
        lib = getattr(self, "diff_lib", [])
        if not self.diff_store:
            return
        sel = [g for g in lib if g["uuid"] in self.diff_sel]
        diffs = sum(g.get("diff_count") or 0 for g in sel)
        n_new = len(set(self.diff_store.new_uuids()) & {g["uuid"] for g in lib})
        self.diff_info.set(f"本地共 {len(lib)} 局有报告（上次运行新增 {n_new} 局）　"
                           f"已选 {len(sel)} 局，差异项 {diffs} 处")
        self.btn_gen.configure(state="normal" if sel else "disabled")

    def _set_sel(self, uuids: set[str]) -> None:
        self.diff_sel = set(uuids)
        for iid in self.tree.get_children():
            self.tree.set(iid, "sel", "☑" if iid in self.diff_sel else "☐")
        self._update_info()

    def _toggle(self, iids) -> None:
        iids = list(iids)
        if not iids:
            return
        on = not all(i in self.diff_sel for i in iids)  # 有没勾的就全勾上, 否则全取消
        sel = set(self.diff_sel)
        sel.update(iids) if on else sel.difference_update(iids)
        self._set_sel(sel)

    def _on_tree_click(self, e):
        if self.tree.identify_region(e.x, e.y) != "cell":
            return None
        if self.tree.identify_column(e.x) != "#1":  # 只有点「选」列才切换, 别处正常选中行
            return None
        iid = self.tree.identify_row(e.y)
        if iid:
            self._toggle([iid])
        return "break"

    def _sel_new(self) -> None:
        if self.diff_store:
            have = {g["uuid"] for g in self.diff_lib}
            self._set_sel(set(self.diff_store.new_uuids()) & have)

    def _sel_all(self) -> None:
        self._set_sel({g["uuid"] for g in getattr(self, "diff_lib", [])})

    def _sel_none(self) -> None:
        self._set_sel(set())

    def _gen_diff(self) -> None:
        """按勾选的对局生成差异报告 (只读本地报告, 不联网)."""
        import io
        from contextlib import redirect_stdout

        import diff_report

        if not self.diff_store or not self.diff_sel:
            return
        uuids = [g["uuid"] for g in self.diff_lib if g["uuid"] in self.diff_sel]
        label = ("上次运行新增" if set(uuids) == set(self.diff_store.new_uuids())
                 else f"手动选择 {len(uuids)} 局")
        buf = io.StringIO()
        self.status.set("正在生成差异报告 ...")
        self.update_idletasks()
        try:
            with redirect_stdout(buf):
                idx = diff_report.build_selection(self.out.get(), self.diff_store, uuids, label)
        except Exception as e:  # noqa: BLE001
            self.status.set("就绪")
            messagebox.showerror("出错", f"生成失败: {e}")
            return
        self._append(buf.getvalue())
        self.status.set("就绪")
        if idx:
            mr.open_file(idx)
        else:
            messagebox.showinfo("提示", buf.getvalue().strip() or "选中的对局没有本地报告")

    # ---------------- 输入记忆 ----------------
    HISTORY_MAX = 30

    @staticmethod
    def _hist_label(h: dict) -> str:
        """下拉里显示的文字: UID 后面带上昵称, 昵称后面带上 UID, 方便认人."""
        ident, by = str(h["ident"]), h.get("by", "id")
        root = store.default_root()
        if by == "id" and ident.isdigit():
            name = h.get("nickname") or store.cached_nickname(root, int(ident))
            return f"{ident}  ({name})" if name else ident
        uid = h.get("uid") or store.lookup_nickname(root, ident)
        return f"{ident}  (UID {uid})" if uid else ident

    def _fill_history(self) -> None:
        self.hist_labels = [self._hist_label(h) for h in self.history]
        self.cb_ident.configure(values=self.hist_labels)

    def _pick_history(self, _e=None) -> None:
        i = self.cb_ident.current()
        if 0 <= i < len(self.history):
            h = self.history[i]
            self.by.set(h.get("by", "id"))
            self.ident.set(h["ident"])  # 去掉显示用的括号部分
            if h.get("modes"):
                for m, v in self.mode_vars.items():
                    v.set(m in h["modes"])
            if h.get("games"):
                self.games.set(int(h["games"]))

    def _forget_history(self, _e=None):
        """下拉框里按 Delete: 从历史里删掉当前这一条 (输入框里的字不动)."""
        cur = self.ident.get().strip()
        before = len(self.history)
        self.history = [h for h in self.history if str(h["ident"]) != cur]
        if len(self.history) != before:
            self._fill_history()
            self._save_settings()
            self.status.set(f"已从历史中删除 {cur}")
            return "break"
        return None

    def _remember(self, by: str, ident: str, modes: list[str], games: int) -> None:
        old = next((x for x in self.history if str(x["ident"]) == ident and x.get("by") == by), {})
        h = {**old, "by": by, "ident": ident, "modes": modes, "games": games, "at": int(time.time())}
        self.history = [h] + [x for x in self.history if x is not old]
        del self.history[self.HISTORY_MAX:]
        self._fill_history()
        self._save_settings()

    def _update_tscale_hint(self) -> None:
        try:
            s = float(self.tscale.get())
        except (tk.TclError, ValueError):
            return
        s = min(max(s, 0.5), 10.0)
        b = mr._BASE_TIMEOUTS
        self.tscale_hint.set(f"验证 {int(b['captcha'] * s)}s / 报告 {int(b['report'] * s)}s")

    def _save_settings(self) -> None:
        def get(var, default):
            try:
                return var.get()
            except (tk.TclError, ValueError):
                return default
        store.save_settings({
            "by": self.by.get(),
            "ident": self.ident.get().strip(),
            "games": get(self.games, 20),
            "concurrency": get(self.conc, 3),
            "timeout_scale": get(self.tscale, 1.0),
            "modes": [m for m, v in self.mode_vars.items() if v.get()],
            "out": self.out.get(),
            "history": self.history,
        })

    def _on_close(self) -> None:
        self._save_settings()
        self.destroy()

    def _browse(self) -> None:
        d = filedialog.askdirectory(initialdir=self.out.get())
        if d:
            self.out.set(d)

    def _open_out(self) -> None:
        p = pathlib.Path(self.out.get())
        p.mkdir(parents=True, exist_ok=True)
        mr.open_file(p)

    def _open_players(self) -> None:
        p = store.default_root()
        p.mkdir(parents=True, exist_ok=True)
        mr.open_file(p)

    def _open_png(self) -> None:
        if self.last_png and self.last_png.exists():
            mr.open_file(self.last_png)

    def _find_diff(self) -> pathlib.Path | None:
        out = pathlib.Path(self.out.get())
        hits = sorted(out.glob("diff_*/index.html"), key=lambda p: p.stat().st_mtime) \
            if out.exists() else []
        return hits[-1] if hits else None

    def _open_diff(self) -> None:
        idx = None
        if self.diff_store:
            p = pathlib.Path(self.out.get()) / f"diff_{self.diff_store.uid}" / "index.html"
            idx = p if p.exists() else None
        idx = idx or self._find_diff()
        if idx:
            mr.open_file(idx)
        else:
            messagebox.showinfo("提示", "还没有差异报告, 勾选对局后点「生成并打开报告」")

    # ---------------- 日志 ----------------
    def _append(self, s: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", s)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _poll(self) -> None:
        chunks = []
        try:
            while True:
                chunks.append(self.q.get_nowait())
        except queue.Empty:
            pass
        for c in chunks:
            if isinstance(c, tuple) and c[0] == "done":
                self._finished(c[1])
            else:
                self._append(c)
        self.after(100, self._poll)

    # ---------------- 运行 ----------------
    def start(self) -> None:
        ident = self.ident.get().strip()
        # 从下拉里选中但没触发选择事件时, 框里可能是「123  (昵称)」这种显示文字
        if ident in getattr(self, "hist_labels", []):
            h = self.history[self.hist_labels.index(ident)]
            ident = str(h["ident"])
            self.by.set(h.get("by", "id"))
            self.ident.set(ident)
        if not ident:
            messagebox.showwarning("提示", "请输入雀魂 UID 或昵称")
            return
        modes = [m for m, v in self.mode_vars.items() if v.get()] or ["玉"]
        try:
            tscale = min(max(float(self.tscale.get()), 0.5), 10.0)
        except (tk.TclError, ValueError):
            tscale = 1.0
        self.tscale.set(tscale)
        args = argparse.Namespace(
            id=ident if self.by.get() == "id" else None,
            name=ident if self.by.get() == "name" else None,
            games=int(self.games.get()),
            mode=modes,
            concurrency=int(self.conc.get()),
            out=self.out.get(),
            no_show=True,
            fresh=self.fresh.get(),
            timeout_scale=tscale,
        )
        if args.id is not None and not args.id.isdigit():
            messagebox.showwarning("提示", "UID 必须是数字; 若输入的是昵称请选「昵称」")
            return
        self._remember(self.by.get(), ident, modes, args.games)

        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.nb.select(0)
        self.stopping = False
        self.btn_run.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.status.set("运行中 ...")
        self.thread = threading.Thread(target=self._worker, args=(args,), daemon=True)
        self.thread.start()

    def _worker(self, args: argparse.Namespace) -> None:
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = QueueWriter(self.q)  # type: ignore[assignment]
        code = 1
        try:
            code = asyncio.run(self._run(args))
        except asyncio.CancelledError:
            print("\n已停止 (进度已保存, 再点开始会自动续跑)")
            code = 130
        except SystemExit as e:
            print(f"\n{e}")
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            print(f"\n出错: {e}")
        finally:
            sys.stdout, sys.stderr = old_out, old_err
            self.q.put(("done", (code, args)))

    async def _run(self, args: argparse.Namespace) -> int:
        self.loop = asyncio.get_running_loop()
        self.task = asyncio.current_task()
        if self.stopping:
            raise asyncio.CancelledError
        return await mr.run(args)

    def stop(self) -> None:
        self.stopping = True
        self.status.set("正在停止 ...")
        self.btn_stop.configure(state="disabled")
        if self.loop and self.task:
            self.loop.call_soon_threadsafe(self.task.cancel)

    def _finished(self, payload) -> None:
        code, args = payload
        self.btn_run.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.loop = self.task = None
        uids = sorted(pathlib.Path(args.out).glob("rating_*.png"), key=lambda p: p.stat().st_mtime) \
            if pathlib.Path(args.out).exists() else []
        if code == 0 and uids:
            self.last_png = uids[-1]
            self.btn_img.configure(state="normal")
            self._load_image(self.last_png)
            self.nb.select(1)
            self.status.set("完成")
        else:
            self.status.set("已停止" if code == 130 else "未完成, 见日志")
        # 历史里补上 UID <-> 昵称 对应, 下拉里显示「UID (昵称)」
        ident = args.id or args.name
        root = store.default_root()
        uid = store.resolve_local(root, ident)
        for h in self.history:
            if str(h["ident"]) == ident and uid:
                h["uid"] = uid
                h["nickname"] = store.cached_nickname(root, uid) or h.get("nickname", "")
        self._fill_history()
        self._save_settings()
        # 跑完后差异报告 tab 切到刚跑的玩家 (list_players 按修改时间排, 第一个就是), 默认勾选新增
        self._refresh_players()

    # ---------------- 图片 ----------------
    def _load_image(self, path: pathlib.Path) -> None:
        try:
            from PIL import Image
            self.last_img = Image.open(path)
            self.last_img.load()
        except Exception as e:  # noqa: BLE001
            self.last_img = None
            self.canvas.configure(text=f"无法显示图片: {e}\n{path}", image="")
            return
        self._render_image()

    def _render_image(self) -> None:
        if self.last_img is None:
            return
        from PIL import Image, ImageTk
        w = max(self.img_frame.winfo_width() - 4, 50)
        h = max(self.img_frame.winfo_height() - 4, 50)
        iw, ih = self.last_img.size
        s = min(w / iw, h / ih)
        img = self.last_img.resize((max(int(iw * s), 1), max(int(ih * s), 1)), Image.LANCZOS)
        self.photo = ImageTk.PhotoImage(img)
        self.canvas.configure(image=self.photo, text="")


def main() -> None:
    os.chdir(app_dir())
    App().mainloop()


if __name__ == "__main__":
    main()
