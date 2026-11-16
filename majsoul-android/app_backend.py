"""
QML 界面的 Python 后端 (桌面和安卓共用).

  Backend        参数/历史/运行/停止/结果图/差异报告, 暴露给 QML 叫 app
  HistoryModel   输入过的玩家 (下拉框)
  GameListModel  差异报告页的本地对局列表 (可勾选)

跑谱在后台线程里 asyncio.run(mahjong_rating.run(args)); 日志和结束都经 Signal 回主线程.
"""
from __future__ import annotations

import argparse
import asyncio
import io
import os
import pathlib
import sys
import threading
import time
import traceback
from contextlib import redirect_stdout
from typing import Any

from PySide6.QtCore import (Property, QAbstractListModel, QModelIndex, QObject, Qt, QTimer,
                            QUrl, Signal, Slot)
from PySide6.QtGui import QDesktopServices

import mahjong_rating as mr
import store
from report_server import ReportServer
from version import __version__

HISTORY_MAX = 30
LOG_MAX_CHARS = 400_000  # 日志页只留最后这么多字, 太长了 TextArea 会卡


# --------------------------------------------------------------------------------------
# 日志: 后台线程的 print 都收到这里, 定时批量发到界面
# --------------------------------------------------------------------------------------


class LogSink(QObject):
    text = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._buf: list[str] = []
        self._lock = threading.Lock()
        self._timer = QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._flush)
        self._timer.start()

    # 文件接口 (任何线程)
    def write(self, s: str) -> int:
        if s:
            with self._lock:
                self._buf.append(s)
        return len(s)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False

    def _flush(self) -> None:
        with self._lock:
            if not self._buf:
                return
            s, self._buf = "".join(self._buf), []
        self.text.emit(s)


class _ThreadStream:
    """sys.stdout 的替身: 后台线程写到 LogSink, 其它线程照旧写原来的流 (控制台)."""

    def __init__(self, orig, sink: LogSink, owner: threading.Thread) -> None:
        self.orig, self.sink, self.owner = orig, sink, owner

    def write(self, s: str) -> int:
        if threading.current_thread() is self.owner:
            return self.sink.write(s)
        return self.orig.write(s) if self.orig else len(s)

    def flush(self) -> None:
        if self.orig:
            try:
                self.orig.flush()
            except Exception:  # noqa: BLE001
                pass

    def isatty(self) -> bool:
        return False

    def __getattr__(self, name):
        return getattr(self.orig, name)


# --------------------------------------------------------------------------------------
# 列表模型
# --------------------------------------------------------------------------------------


class HistoryModel(QAbstractListModel):
    LabelRole, IdentRole, ByRole = Qt.UserRole + 1, Qt.UserRole + 2, Qt.UserRole + 3

    def __init__(self) -> None:
        super().__init__()
        self.items: list[dict[str, Any]] = []

    def roleNames(self):
        return {Qt.DisplayRole: b"display", self.LabelRole: b"label",
                self.IdentRole: b"ident", self.ByRole: b"by"}

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.items)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.items):
            return None
        h = self.items[index.row()]
        if role in (Qt.DisplayRole, self.LabelRole):
            return hist_label(h)
        if role == self.IdentRole:
            return str(h["ident"])
        if role == self.ByRole:
            return h.get("by", "id")
        return None

    def reset(self, items: list[dict[str, Any]]) -> None:
        self.beginResetModel()
        self.items = items
        self.endResetModel()


def hist_label(h: dict[str, Any]) -> str:
    """下拉里显示: UID 后面带上昵称, 昵称后面带上 UID, 方便认人."""
    ident, by = str(h["ident"]), h.get("by", "id")
    root = store.default_root()
    if by == "id" and ident.isdigit():
        name = h.get("nickname") or store.cached_nickname(root, int(ident))
        return f"{ident}  ({name})" if name else ident
    uid = h.get("uid") or store.lookup_nickname(root, ident)
    return f"{ident}  (UID {uid})" if uid else ident


class GameListModel(QAbstractListModel):
    ROLES = ["uuid", "checked", "when", "mode", "rank", "score", "pt", "table",
             "rating", "acc", "diffs", "isNew"]

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict[str, Any]] = []
        self._role_ids = {Qt.UserRole + 1 + i: n for i, n in enumerate(self.ROLES)}

    def roleNames(self):
        return {k: v.encode() for k, v in self._role_ids.items()}

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        name = self._role_ids.get(role)
        return self.rows[index.row()].get(name) if name else None

    def reset(self, rows: list[dict[str, Any]]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def set_checked(self, sel: set[str]) -> None:
        role = Qt.UserRole + 1 + self.ROLES.index("checked")
        for i, r in enumerate(self.rows):
            on = r["uuid"] in sel
            if r["checked"] != on:
                r["checked"] = on
                idx = self.index(i)
                self.dataChanged.emit(idx, idx, [role])


def game_row(g: dict[str, Any], st: store.PlayerStore, new: set[str], sel: set[str]) -> dict:
    rec = st.records.get(g["uuid"]) or {}
    players = rec.get("players") or []
    table = ""
    if players:
        order = sorted(range(len(players)), key=lambda i: (-(players[i].get("score") or 0), i))
        table = "  ".join(("▶" if players[i].get("accountId") == st.uid else "")
                          + str(players[i].get("score", "?")) for i in order)
    pt = g.get("pt_delta")
    acc = g.get("accordance")
    return {
        "uuid": g["uuid"],
        "checked": g["uuid"] in sel,
        "when": time.strftime("%Y-%m-%d %H:%M", time.localtime(g.get("start_time") or 0)),
        "mode": str(mr.MODE_BY_ID.get(g.get("mode_id"), g.get("mode_id"))),
        "rank": int(g.get("rank") or 0),
        "score": str(g.get("score", "-")),
        "pt": "-" if pt is None else f"{pt:+d}",
        "table": table,
        "rating": "-" if g.get("rating") is None else str(g["rating"]),
        "acc": (f"{g.get('accordance_detail', '')} {acc * 100:.1f}%" if acc is not None else "-"),
        "diffs": "-" if g.get("diff_count") is None else str(g["diff_count"]),
        "isNew": g["uuid"] in new,
    }


# --------------------------------------------------------------------------------------
# 后端
# --------------------------------------------------------------------------------------


class Backend(QObject):
    logAppended = Signal(str)
    logCleared = Signal()
    runningChanged = Signal()
    statusChanged = Signal()
    chartChanged = Signal()
    playersChanged = Signal()
    diffChanged = Signal()
    formChanged = Signal()
    openReport = Signal(str)   # 网址: 界面切到报告页打开
    message = Signal(str)      # 提示框
    finished = Signal(int)
    progressChanged = Signal()
    _progressIn = Signal(str, int, int, str, float, float)  # 后台线程发, 排队到主线程

    def __init__(self, web_bridge=None) -> None:
        super().__init__()
        self.web_bridge = web_bridge  # 安卓: webbackend.WebBridge; 桌面为 None (用本机浏览器)
        self.sink = LogSink()
        self.sink.text.connect(self._on_log)
        self._running = False
        self._status = "就绪"
        self._chart = ""
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None
        self._stopping = False

        cfg = store.load_settings()
        hist = [h for h in cfg.get("history") or []
                if isinstance(h, dict) and str(h.get("ident") or "").strip()]
        if "history" not in cfg:  # 第一次用新版: 把本地已有数据的玩家放进下拉
            hist = [{"by": "id", "ident": str(uid), "uid": uid, "nickname": name}
                    for uid, name in store.list_players(store.default_root())][:HISTORY_MAX]
        if not cfg.get("ident") and hist:
            cfg["ident"], cfg["by"] = hist[0]["ident"], hist[0].get("by", "id")
        self.history = HistoryModel()
        self.history.reset(hist)
        self._by = cfg.get("by") if cfg.get("by") in ("id", "name") else "id"
        self._ident = str(cfg.get("ident") or "")
        self._games = int(cfg.get("games") or 20)
        self._conc = int(cfg.get("concurrency") or 3)
        self._tscale = float(cfg.get("timeout_scale") or 1.0)
        self._modes = [m for m in (cfg.get("modes") or ["玉"]) if m in mr.MODES] or ["玉"]
        default_out = store.app_dir() / "rating_out"
        self._out = str(default_out if store.IS_ANDROID else (cfg.get("out") or default_out))

        self.server = ReportServer(self._out)
        self.games = GameListModel()
        self.players: list[tuple[int, str]] = []
        self._player_idx = -1
        self.diff_store: store.PlayerStore | None = None
        self.diff_lib: list[dict[str, Any]] = []
        self.diff_sel: set[str] = set()
        self._diff_info = ""
        self.finished.connect(self._finish)  # 后台线程发出, 排队到主线程执行
        self._prog = ("", 0, 0, "", 0.0, 0.0)
        self._progressIn.connect(self._on_progress, Qt.QueuedConnection)
        self._find_chart()
        self.refreshPlayers(False)

    # ---------------- 只读属性 ----------------
    @Property(str, constant=True)
    def version(self) -> str:
        return __version__

    @Property(str, constant=True)
    def modelTag(self) -> str:
        return mr.MODEL_TAG

    @Property(bool, constant=True)
    def mobile(self) -> bool:
        return store.IS_ANDROID

    @Property(bool, constant=True)
    def mobileUi(self) -> bool:
        """手机布局 (底部导航、单列). 桌面上设 MJR_MOBILE_UI=1 可以预览."""
        return store.IS_ANDROID or os.environ.get("MJR_MOBILE_UI") == "1"

    @Property(bool, constant=True)
    def inAppWeb(self) -> bool:
        """提交跑谱用程序内的网页 (安卓). 桌面用本机 Edge/Chrome."""
        return self.web_bridge is not None

    @Property(list, constant=True)
    def modeNames(self) -> list[str]:
        return list(mr.MODES)

    @Property(QObject, constant=True)
    def historyModel(self) -> QObject:
        return self.history

    @Property(QObject, constant=True)
    def gameModel(self) -> QObject:
        return self.games

    @Property(bool, notify=runningChanged)
    def running(self) -> bool:
        return self._running

    @Property(str, notify=statusChanged)
    def status(self) -> str:
        return self._status

    def _set_status(self, s: str) -> None:
        self._status = s
        self.statusChanged.emit()

    # ---------------- 进度 ----------------
    @Slot(str, int, int, str, float, float)
    def _on_progress(self, stage: str, done: int, total: int, detail: str,
                     elapsed: float, limit: float) -> None:
        if self._running:
            self._prog = (stage, done, total, detail, elapsed, limit)
            self.progressChanged.emit()

    @Property(float, notify=progressChanged)
    def progressTime(self) -> float:
        """本阶段已等时间占上限的比例 (0~1); 没有上限时为 -1."""
        el, lim = self._prog[4], self._prog[5]
        return min(el / lim, 1.0) if lim > 0 else -1.0

    @Property(str, notify=progressChanged)
    def progressStage(self) -> str:
        return self._prog[0]

    @Property(int, notify=progressChanged)
    def progressDone(self) -> int:
        return self._prog[1]

    @Property(int, notify=progressChanged)
    def progressTotal(self) -> int:
        """0 = 不确定进度 (界面显示滚动条)."""
        return self._prog[2]

    @Property(str, notify=progressChanged)
    def progressText(self) -> str:
        stage, done, total, detail = self._prog[:4]
        s = stage + (f"  {done}/{total} 局" if total else "")
        return s + (f"  ({detail})" if detail else "")

    @Property(str, notify=chartChanged)
    def chartUrl(self) -> str:
        """结果图: PNG 文件网址, 或 (没有 matplotlib 时) 网页版图的 http 网址."""
        return self._chart

    # ---------------- 表单 (双向) ----------------
    def _prop(name, typ, formChanged=formChanged):  # noqa: N805  生成带 formChanged 通知的读写属性
        attr = "_" + name

        def get(self):
            return getattr(self, attr)

        def put(self, v):
            if getattr(self, attr) != v:
                setattr(self, attr, v)
                self.formChanged.emit()
        return Property(typ, get, put, notify=formChanged)

    by = _prop("by", str)
    ident = _prop("ident", str)
    gameCount = _prop("games", int)
    concurrency = _prop("conc", int)
    timeoutScale = _prop("tscale", float)
    modes = _prop("modes", list)
    outDir = _prop("out", str)
    del _prop

    @Property(str, notify=formChanged)
    def timeoutHint(self) -> str:
        s = min(max(self._tscale, 0.5), 10.0)
        b = mr._BASE_TIMEOUTS
        return f"验证 {int(b['captcha'] * s)}s / 报告 {int(b['report'] * s)}s"

    @Slot(str, bool)
    def setMode(self, name: str, on: bool) -> None:
        ms = [m for m in self._modes if m != name]
        if on:
            ms.append(name)
        self._modes = [m for m in mr.MODES if m in ms]  # 保持固定顺序
        self.formChanged.emit()

    # ---------------- 历史 ----------------
    @Slot(int)
    def pickHistory(self, i: int) -> None:
        if not 0 <= i < len(self.history.items):
            return
        h = self.history.items[i]
        self._by = h.get("by", "id")
        self._ident = str(h["ident"])
        if h.get("modes"):
            self._modes = [m for m in mr.MODES if m in h["modes"]] or self._modes
        if h.get("games"):
            self._games = int(h["games"])
        self.formChanged.emit()

    @Slot(int)
    def forgetHistory(self, i: int) -> None:
        if 0 <= i < len(self.history.items):
            cur = self.history.items[i]["ident"]
            self.history.reset([h for k, h in enumerate(self.history.items) if k != i])
            self.saveSettings()
            self._set_status(f"已从历史中删除 {cur}")

    def _remember(self, by: str, ident: str, modes: list[str], games: int) -> None:
        items = self.history.items
        old = next((x for x in items if str(x["ident"]) == ident and x.get("by") == by), {})
        h = {**old, "by": by, "ident": ident, "modes": modes, "games": games, "at": int(time.time())}
        self.history.reset(([h] + [x for x in items if x is not old])[:HISTORY_MAX])
        self.saveSettings()

    @Slot()
    def saveSettings(self) -> None:
        store.save_settings({
            "by": self._by, "ident": self._ident.strip(), "games": self._games,
            "concurrency": self._conc, "timeout_scale": self._tscale, "modes": self._modes,
            "out": self._out, "history": self.history.items,
        })

    # ---------------- 运行 ----------------
    def _on_log(self, s: str) -> None:
        self.logAppended.emit(s)

    @Slot(str, bool)
    def start(self, ident_text: str, fresh: bool) -> None:
        if self._running:
            return
        ident = ident_text.strip()
        # 下拉里选中的是「123  (昵称)」这种显示文字时, 换回原始输入
        for h in self.history.items:
            if ident == hist_label(h):
                ident, self._by = str(h["ident"]), h.get("by", "id")
                break
        if not ident:
            self.message.emit("请输入雀魂 UID 或昵称")
            return
        if self._by == "id" and not ident.isdigit():
            self.message.emit("UID 必须是数字; 若输入的是昵称请选「昵称」")
            return
        self._ident = ident
        self._tscale = min(max(self._tscale, 0.5), 10.0)
        modes = self._modes or ["玉"]
        args = argparse.Namespace(
            id=ident if self._by == "id" else None,
            name=ident if self._by == "name" else None,
            games=max(1, int(self._games)), mode=list(modes),
            concurrency=1 if self.web_bridge else max(1, min(int(self._conc), 8)),
            out=self._out, no_show=True, fresh=bool(fresh), timeout_scale=self._tscale)
        self.formChanged.emit()
        self._remember(self._by, ident, list(modes), args.games)
        self.logCleared.emit()
        self._stopping = False
        self._prog = ("准备中", 0, 0, "", 0.0, 0.0)
        self.progressChanged.emit()
        self._running = True
        self.runningChanged.emit()
        self._set_status("运行中 ...")
        self._thread = threading.Thread(target=self._worker, args=(args,), daemon=True,
                                        name="rating-worker")
        self._thread.start()

    def _worker(self, args: argparse.Namespace) -> None:
        me = threading.current_thread()
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = _ThreadStream(old_out, self.sink, me)  # type: ignore[assignment]
        sys.stderr = _ThreadStream(old_err, self.sink, me)  # type: ignore[assignment]
        code = 1
        mr.set_progress_callback(self._progressIn.emit)
        try:
            code = asyncio.run(self._run(args))
        except asyncio.CancelledError:
            print("\n已停止 (进度已保存, 再点开始会自动续跑)")
            code = 130
        except SystemExit as e:
            print(f"\n{e}")
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            print(f"\n出错: {e}")
        finally:
            mr.set_progress_callback(None)
            sys.stdout, sys.stderr = old_out, old_err
            self._loop = self._task = None
            # 回主线程收尾 (Signal 跨线程自动排队)
            self.finished.emit(code)

    async def _run(self, args: argparse.Namespace) -> int:
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.current_task()
        if self._stopping:
            raise asyncio.CancelledError
        if self.web_bridge is not None:
            import webbackend
            self.web_bridge.bind(self._loop)
            args.web = webbackend.WebViewSession(self.web_bridge)
        try:
            return await mr.run(args)
        finally:
            if self.web_bridge is not None:
                self.web_bridge.bind(None)

    @Slot()
    def stop(self) -> None:
        if not self._running:
            return
        self._stopping = True
        self._set_status("正在停止 ...")
        loop, task = self._loop, self._task
        if loop and task:
            loop.call_soon_threadsafe(task.cancel)

    def _finish(self, code: int) -> None:
        self.sink._flush()
        self._prog = ("", 0, 0, "", 0.0, 0.0)
        self.progressChanged.emit()
        self._running = False
        self.runningChanged.emit()
        self._set_status("完成" if code == 0 else ("已停止" if code == 130 else "未完成, 见日志"))
        # 历史里补上 UID <-> 昵称 对应
        root = store.default_root()
        uid = store.resolve_local(root, self._ident)
        if uid:
            for h in self.history.items:
                if str(h["ident"]) == self._ident:
                    h["uid"] = uid
                    h["nickname"] = store.cached_nickname(root, uid) or h.get("nickname", "")
            self.history.reset(list(self.history.items))
        self.saveSettings()
        self._find_chart(uid)
        self.refreshPlayers(False)  # 切到刚跑的玩家, 默认勾选新增

    # ---------------- 结果图 ----------------
    def _find_chart(self, uid: int | None = None) -> None:
        out = pathlib.Path(self._out)
        url = ""
        if out.exists():
            pat = f"rating_{uid}" if uid else "rating_*"
            hits = sorted(list(out.glob(pat + ".png")) + list(out.glob(pat + ".html")),
                          key=lambda p: p.stat().st_mtime)
            if hits:
                p = hits[-1]
                # 加时间戳, 同名文件重新生成后 Image 才会重新加载
                url = (QUrl.fromLocalFile(str(p)).toString() + f"?t={int(p.stat().st_mtime)}"
                       if p.suffix == ".png" else self.server.url_for(p))
        if url != self._chart:
            self._chart = url
            self.chartChanged.emit()

    @Slot()
    def openChartExternally(self) -> None:
        if self._chart:
            QDesktopServices.openUrl(QUrl(self._chart.split("?")[0]))

    @Slot()
    def openOutDir(self) -> None:
        p = pathlib.Path(self._out)
        p.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))

    @Slot()
    def openPlayersDir(self) -> None:
        p = store.default_root()
        p.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))

    @Slot(str)
    def setOutDirUrl(self, url: str) -> None:
        """文件夹对话框选中的 file:// 网址."""
        p = QUrl(url).toLocalFile() or url
        if p and p != self._out:
            self._out = p
            self.server.set_root(p)
            self.formChanged.emit()

    @Slot(str)
    def openExternal(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    # ---------------- 差异报告 ----------------
    @Property(list, notify=playersChanged)
    def playerLabels(self) -> list[str]:
        return [f"{name or '?'} ({uid})" for uid, name in self.players]

    @Property(int, notify=playersChanged)
    def playerIndex(self) -> int:
        return self._player_idx

    @Property(str, notify=diffChanged)
    def diffInfo(self) -> str:
        return self._diff_info

    @Property(int, notify=diffChanged)
    def selectedCount(self) -> int:
        return len(self.diff_sel)

    @Slot(bool)
    def refreshPlayers(self, keep: bool = True) -> None:
        cur = self.diff_store.uid if (keep and self.diff_store) else None
        self.players = store.list_players(store.default_root())
        uids = [u for u, _ in self.players]
        self._player_idx = (uids.index(cur) if cur in uids else 0) if uids else -1
        self.playersChanged.emit()
        if self._player_idx < 0:
            self.diff_store, self.diff_lib, self.diff_sel = None, [], set()
            self.games.reset([])
            self._diff_info = "还没有本地数据, 先跑一次"
            self.diffChanged.emit()
            return
        self._load_library(default=not keep)

    @Slot(int)
    def selectPlayer(self, i: int) -> None:
        if 0 <= i < len(self.players) and i != self._player_idx:
            self._player_idx = i
            self.playersChanged.emit()
            self._load_library(default=True)

    def _load_library(self, default: bool) -> None:
        uid = self.players[self._player_idx][0]
        old = set(self.diff_sel) if (not default and self.diff_store
                                     and self.diff_store.uid == uid) else None
        self.diff_store = st = store.PlayerStore(store.default_root(), uid)
        self.diff_lib = st.library()
        have = {g["uuid"] for g in self.diff_lib}
        self.diff_sel = set(st.default_selection()[0]) if old is None else old & have
        new = set(st.new_uuids())
        self.games.reset([game_row(g, st, new, self.diff_sel) for g in self.diff_lib])
        self._update_info()

    def _update_info(self) -> None:
        if not self.diff_store:
            return
        sel = [g for g in self.diff_lib if g["uuid"] in self.diff_sel]
        diffs = sum(g.get("diff_count") or 0 for g in sel)
        n_new = len(set(self.diff_store.new_uuids()) & {g["uuid"] for g in self.diff_lib})
        self._diff_info = (f"本地共 {len(self.diff_lib)} 局有报告（上次运行新增 {n_new} 局）　"
                           f"已选 {len(sel)} 局，差异项 {diffs} 处")
        self.diffChanged.emit()

    def _set_sel(self, sel: set[str]) -> None:
        self.diff_sel = set(sel)
        self.games.set_checked(self.diff_sel)
        self._update_info()

    @Slot(int)
    def toggleGame(self, row: int) -> None:
        if 0 <= row < len(self.games.rows):
            u = self.games.rows[row]["uuid"]
            self._set_sel(self.diff_sel ^ {u})

    @Slot()
    def selectNew(self) -> None:
        if self.diff_store:
            have = {g["uuid"] for g in self.diff_lib}
            self._set_sel(set(self.diff_store.new_uuids()) & have)

    @Slot()
    def selectAll(self) -> None:
        self._set_sel({g["uuid"] for g in self.diff_lib})

    @Slot()
    def selectNone(self) -> None:
        self._set_sel(set())

    @Slot()
    def generateReport(self) -> None:
        """按勾选的对局生成差异报告 (只读本地报告, 不联网), 生成后在报告页打开."""
        import diff_report

        if not self.diff_store or not self.diff_sel:
            return
        st = self.diff_store
        uuids = [g["uuid"] for g in self.diff_lib if g["uuid"] in self.diff_sel]
        label = ("上次运行新增" if set(uuids) == set(st.new_uuids()) else f"手动选择 {len(uuids)} 局")
        self._set_status("正在生成差异报告 ...")
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                idx = diff_report.build_selection(self._out, st, uuids, label)
        except Exception as e:  # noqa: BLE001
            self._set_status("就绪")
            self.message.emit(f"生成失败: {e}")
            return
        self.logAppended.emit(buf.getvalue())
        self._set_status("就绪")
        if idx:
            self.openReport.emit(self.server.url_for(idx))
        else:
            self.message.emit(buf.getvalue().strip() or "选中的对局没有本地报告")

    @Slot()
    def openLastReport(self) -> None:
        out = pathlib.Path(self._out)
        idx = None
        if self.diff_store:
            p = out / f"diff_{self.diff_store.uid}" / "index.html"
            idx = p if p.exists() else None
        if idx is None and out.exists():
            hits = sorted(out.glob("diff_*/index.html"), key=lambda p: p.stat().st_mtime)
            idx = hits[-1] if hits else None
        if idx:
            self.openReport.emit(self.server.url_for(idx))
        else:
            self.message.emit("还没有差异报告, 勾选对局后点「生成报告」")

    @Slot(str, result=bool)
    def isLocalUrl(self, url: str) -> bool:
        return url.startswith("http://127.0.0.1:") or url.startswith("file:")

    def shutdown(self) -> None:
        self.stop()
        self.saveSettings()
        self.server.stop()
