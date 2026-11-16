"""Qt 版后端: 在旧 Backend (参数/历史/运行/停止/结果图, 全是业务逻辑) 的基础上
换掉差异报告这一块: 不再生成 HTML, 改为后台线程生成每局 JSON 缓存 + ReviewNav 阅读器.

QML 里仍叫 app, 属性和槽与旧版同名; 新增:
  nav               ReviewNav (阅读器导航)
  summary           汇总 (对局表 + Q 损失最大的差异项)
  genBusy/genText   生成进度
  openGame(uuid, idx) / openSummary()
"""
from __future__ import annotations

import threading
from typing import Any

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

import app_backend
import store
from qtapp import diff_data
from qtapp.models import ReviewNav


class Backend(app_backend.Backend):
    summaryChanged = Signal()
    genChanged = Signal()
    showReader = Signal()      # 界面切到阅读器
    showSummary = Signal()     # 界面切到汇总
    _genDone = Signal(object, str)  # (summary | None, 错误)
    _genProg = Signal(int, int)

    def __init__(self, web_bridge=None) -> None:
        super().__init__(web_bridge)
        self.nav = ReviewNav()
        self._summary: dict[str, Any] = {}
        self._gen_busy = False
        self._gen_text = ""
        self._cur_uuid = ""
        self._genDone.connect(self._on_gen_done)
        self._genProg.connect(self._on_gen_prog)

    # ---------------- 属性 ----------------
    @Property(QObject, constant=True)
    def reviewNav(self) -> QObject:
        return self.nav

    @Property("QVariantMap", notify=summaryChanged)
    def summary(self) -> dict[str, Any]:
        return self._summary

    @Property(str, constant=True)
    def assetUrl(self) -> str:
        """牌面精灵图所在目录的网址 (以 / 结尾)."""
        return QUrl.fromLocalFile(str(store.resource_dir() / "assets")).toString() + "/"

    @Property(bool, notify=genChanged)
    def genBusy(self) -> bool:
        return self._gen_busy

    @Property(str, notify=genChanged)
    def genText(self) -> str:
        return self._gen_text

    @Property(bool, notify=summaryChanged)
    def hasSummary(self) -> bool:
        return bool(self._summary)

    # ---------------- 生成 (后台线程) ----------------
    @Slot()
    def generateReport(self) -> None:  # 覆盖旧版 (旧版生成 HTML)
        if self._gen_busy or not self.diff_store or not self.diff_sel:
            return
        st = self.diff_store
        uuids = [g["uuid"] for g in self.diff_lib if g["uuid"] in self.diff_sel]
        self._gen_busy = True
        self._gen_text = "正在生成差异数据 ..."
        self.genChanged.emit()
        self._set_status("正在生成差异数据 ...")
        out = self._out

        def work() -> None:
            try:
                res = diff_data.summarize(out, st, uuids, progress=self._genProg.emit)
                self._genDone.emit(res, "")
            except Exception as e:  # noqa: BLE001
                self._genDone.emit(None, str(e))

        threading.Thread(target=work, daemon=True, name="diff-gen").start()

    @Slot(int, int)
    def _on_gen_prog(self, i: int, n: int) -> None:
        self._gen_text = f"正在生成差异数据 {i + 1}/{n}"
        self.genChanged.emit()

    @Slot(object, str)
    def _on_gen_done(self, res: Any, err: str) -> None:
        self._gen_busy = False
        self._gen_text = ""
        self.genChanged.emit()
        self._set_status("就绪")
        if res is None:
            self.message.emit(f"生成失败: {err}")
            return
        if not any(g.get("ok") for g in res["games"]):
            self.message.emit("选中的对局没有本地报告")
            return
        self._summary = res
        self.summaryChanged.emit()
        self.openReport.emit("")  # 界面切到「报告」页 (汇总)
        self.showSummary.emit()

    @Slot()
    def openLastReport(self) -> None:  # 覆盖旧版
        if self._summary:
            self.openReport.emit("")
            self.showSummary.emit()
        else:
            self.message.emit("还没有差异报告, 勾选对局后点「生成报告」")

    # ---------------- 打开一局 ----------------
    def _flush_nav(self) -> None:
        if self.nav.dirty and self.nav._data is not None and self.diff_store:
            try:
                diff_data.save_game(self._out, self.diff_store.uid, self.nav._data)
            except OSError:
                pass
            self.nav.dirty = False

    @Slot(str, int)
    def openGame(self, uuid: str, idx: int) -> None:
        """idx<0: 这一局的第一个差异项."""
        if not self.diff_store:
            return
        if uuid != self._cur_uuid or not self.nav.loaded:
            self._flush_nav()
            g = next((x for x in self.diff_lib if x["uuid"] == uuid), None)
            data = diff_data.load_game(self._out, self.diff_store, g) if g else None
            if data is None:
                self.message.emit("这一局没有本地报告")
                return
            self._cur_uuid = uuid
            self.nav.load(data, idx)
        elif idx >= 0:
            self.nav.jumpTo(idx)
        self.showReader.emit()

    @Slot()
    def closeReader(self) -> None:
        self._flush_nav()
        self.showSummary.emit()

    def shutdown(self) -> None:
        self._flush_nav()
        super().shutdown()



