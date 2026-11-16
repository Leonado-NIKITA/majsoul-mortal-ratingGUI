"""Qt 版的模型与阅读器导航.

HistoryModel / GameListModel 是纯 Qt 列表模型, 和旧版完全一样, 直接复用.
ReviewNav: 差异阅读器的导航状态 (当前决策点、仅看差异、上/下一差异、上/下一巡、目录).
按钮、按键、手势在 QML 里调用同一组槽.
"""
from __future__ import annotations

import bisect
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

import store
from app_backend import GameListModel, HistoryModel, game_row, hist_label  # noqa: F401  (re-export)
from qtapp import diff_data


class ReviewNav(QObject):
    changed = Signal()          # 当前决策点变了
    gameChanged = Signal()      # 换了一局
    prefsChanged = Signal()     # 仅看差异 / 他家手牌 开关
    toast = Signal(str)         # 到头了等提示

    def __init__(self) -> None:
        super().__init__()
        self._data: dict[str, Any] | None = None
        self._entries: list[dict[str, Any]] = []
        self._diffs: list[int] = []
        self._i = 0
        self.dirty = False  # 有一致项的牌效是翻页时算出来的, 离开这局时写回缓存
        cfg = store.load_settings()
        self._only = bool(cfg.get("onlyDiff", True))
        self._hands = bool(cfg.get("showHands", True))

    # ---------------- 装载 ----------------
    def load(self, data: dict[str, Any], start: int = -1) -> None:
        """start<0: 第一个差异项 (没有差异就第 0 个)."""
        self._data = data
        self.dirty = False
        self._entries = data["entries"]
        self._diffs = [e["idx"] for e in self._entries if e["isDiff"]]
        if start < 0 or start >= len(self._entries):
            start = self._diffs[0] if self._diffs else 0
        self._i = start
        self._touch()
        self.gameChanged.emit()
        self.changed.emit()
        self.prefsChanged.emit()

    def _touch(self) -> None:
        if self._entries:
            if diff_data.ensure_eff(self._entries[self._i]):
                self.dirty = True

    def prefs(self) -> dict[str, Any]:
        return {"onlyDiff": self._only, "showHands": self._hands}

    def _save(self) -> None:
        cfg = store.load_settings()
        cfg.update(self.prefs())
        store.save_settings(cfg)

    # ---------------- 属性 ----------------
    @Property(bool, notify=gameChanged)
    def loaded(self) -> bool:
        return bool(self._entries)

    @Property(int, notify=gameChanged)
    def count(self) -> int:
        return len(self._entries)

    @Property(int, notify=gameChanged)
    def diffCount(self) -> int:
        return len(self._diffs)

    @Property(int, notify=changed)
    def index(self) -> int:
        return self._i

    @Property("QVariantMap", notify=changed)
    def current(self) -> dict[str, Any]:
        if not self._entries:
            return {}
        return {k: v for k, v in self._entries[self._i].items() if k != "raw"}

    @Property("QVariantMap", notify=gameChanged)
    def header(self) -> dict[str, Any]:
        return self._data["header"] if self._data else {}

    @Property("QVariantList", notify=gameChanged)
    def names(self) -> list[str]:
        return list(self._data["names"]) if self._data else []

    @Property(int, notify=gameChanged)
    def me(self) -> int:
        return int(self._data["me"]) if self._data else 0

    @Property(bool, notify=prefsChanged)
    def onlyDiff(self) -> bool:
        return self._only

    @onlyDiff.setter
    def onlyDiff(self, v: bool) -> None:
        if v != self._only:
            self._only = bool(v)
            self._save()
            self.prefsChanged.emit()

    @Property(bool, notify=prefsChanged)
    def showHands(self) -> bool:
        return self._hands

    @showHands.setter
    def showHands(self, v: bool) -> None:
        if v != self._hands:
            self._hands = bool(v)
            self._save()
            self.prefsChanged.emit()

    @Property(int, notify=changed)
    def diffNo(self) -> int:
        """当前位置之前 (含) 有几个差异项."""
        return bisect.bisect_right(self._diffs, self._i)

    @Property(str, notify=changed)
    def positionText(self) -> str:
        if not self._entries:
            return ""
        e = self._entries[self._i]
        s = f"{e['kyoku']} 第{e['junme']}巡"
        if e["isDiff"]:
            return f"{s} · 差异 {self.diffNo}/{len(self._diffs)}"
        return f"{s} · 一致 · 第 {self._i + 1}/{len(self._entries)} 手"

    @Property(bool, notify=changed)
    def canPrevDiff(self) -> bool:
        return self._find(-1, True) >= 0

    @Property(bool, notify=changed)
    def canNextDiff(self) -> bool:
        return self._find(1, True) >= 0

    @Property(bool, notify=changed)
    def canPrevTurn(self) -> bool:
        return self._i > 0

    @Property(bool, notify=changed)
    def canNextTurn(self) -> bool:
        return self._i < len(self._entries) - 1

    @Property("QVariantList", notify=gameChanged)
    def kyokus(self) -> list[dict[str, Any]]:
        return self._data["kyokus"] if self._data else []

    @Property("QVariantList", notify=prefsChanged)
    def toc(self) -> list[dict[str, Any]]:
        """目录: 小局标题行 + 决策点行. 仅看差异时只列差异项."""
        out: list[dict[str, Any]] = []
        if not self._data:
            return out
        for ki, k in enumerate(self._data["kyokus"]):
            out.append({"type": "kyoku", "ki": ki, "title": k["title"], "end": k["end"],
                        "diffs": k["diffs"], "first": k["first"]})
            for e in self._entries[k["first"]:k["first"] + k["count"]]:
                if self._only and not e["isDiff"]:
                    continue
                label = f"{e['junme']}巡  {e['actualText']}"
                if e["isDiff"]:
                    label += f" → {e['expectedText']}"
                out.append({"type": "entry", "idx": e["idx"], "isDiff": e["isDiff"], "label": label,
                            "loss": e["loss"] if e["loss"] is not None else -1.0})
        return out

    # ---------------- 导航 ----------------
    def _find(self, step: int, diff_only: bool) -> int:
        i = self._i + step
        while 0 <= i < len(self._entries):
            if not diff_only or self._entries[i]["isDiff"]:
                return i
            i += step
        return -1

    def _go(self, i: int, msg: str) -> bool:
        if i < 0:
            self.toast.emit(msg)
            return False
        self._i = i
        self._touch()
        self.changed.emit()
        return True

    @Slot(result=bool)
    def nextDiff(self) -> bool:
        return self._go(self._find(1, True), "已是最后一处差异")

    @Slot(result=bool)
    def prevDiff(self) -> bool:
        return self._go(self._find(-1, True), "已是第一处差异")

    @Slot(result=bool)
    def nextTurn(self) -> bool:
        return self._go(self._find(1, False), "已是最后一巡")

    @Slot(result=bool)
    def prevTurn(self) -> bool:
        return self._go(self._find(-1, False), "已是第一巡")

    @Slot(result=bool)
    def swipeNext(self) -> bool:
        return self.nextDiff() if self._only else self.nextTurn()

    @Slot(result=bool)
    def swipePrev(self) -> bool:
        return self.prevDiff() if self._only else self.prevTurn()

    @Slot(int)
    def jumpTo(self, i: int) -> None:
        if 0 <= i < len(self._entries):
            self._go(i, "")

    @Slot(int)
    def jumpToKyoku(self, k: int) -> None:
        ks = self.kyokus
        if 0 <= k < len(ks) and ks[k]["count"]:
            first = ks[k]["first"]
            d = next((e["idx"] for e in self._entries[first:first + ks[k]["count"]] if e["isDiff"]), first)
            self._go(d, "")

    @Slot()
    def first(self) -> None:
        self._go(0 if self._entries else -1, "")

    @Slot()
    def last(self) -> None:
        self._go(len(self._entries) - 1, "")

    @Slot()
    def toggleOnlyDiff(self) -> None:
        self.onlyDiff = not self._only


