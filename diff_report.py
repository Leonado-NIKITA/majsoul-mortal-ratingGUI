"""Mortal 差异项报告: 把 mjai 报告里 "自己的选择 != AI 选择" 的局面整理成 HTML.

数据来源: mjai.ekyu.moe 返回的报告 JSON (mahjong_rating.py 存在 players/<UID>/reports/ 下).
  - review.kyokus[].entries[]  每个可选择的决策点 (含 is_equal / actual / expected / details)
  - mjai_log                   整局的 mjai 事件, 用来复原当时的牌桌

entries 里没有事件序号, 这里按 mjai-reviewer (src/review/mortal.rs) 的同一套规则重放
mjai_log, 算出每个事件处的 (巡目, 余牌, last_actor, tile, 标志位, 手牌), 再按顺序对齐.

牌面 / 手牌 / 副露的画法照搬 mjai-reviewer 的 templates/macros.tera + report.css + pai.svg.

用法 (离线重建, 不用重跑):
    python diff_report.py                # 最近一次跑的玩家, 输出到 rating_out/
    python diff_report.py rating_out --id 12345678 --open
"""

from __future__ import annotations

import argparse
import copy
import html
import json
import pathlib
import re
import shutil
import sys
import time
from typing import Any

try:  # 牌效分析依赖 mahjong 库; 没装就不显示这一块, 报告其余部分照常
    import efficiency as eff
except ImportError:  # pragma: no cover
    eff = None

SEAT_REL = ["自家", "下家", "对家", "上家"]
WINDS = ["东", "南", "西", "北"]
BAKAZE = {"E": 0, "S": 1, "W": 2, "N": 3}
HONORS = "ESWNPFC"
SKIP_TYPES = {"start_game", "start_kyoku", "end_kyoku", "end_game"}
KAN_TYPES = {"ankan", "kakan", "daiminkan"}


def esc(s: Any) -> str:
    return html.escape(str(s), quote=True)


def assets_dir() -> pathlib.Path:
    """开发时在脚本旁边; PyInstaller 打包后在 _MEIPASS 里."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        p = pathlib.Path(base) / "assets"
        if p.exists():
            return p
    return pathlib.Path(__file__).resolve().parent / "assets"


# --------------------------------------------------------------------------------------
# 牌
# --------------------------------------------------------------------------------------


def deaka(t: str) -> str:
    return t[:-1] if t.endswith("r") else t


def tile_key(t: str) -> tuple[int, int, int]:
    """与 convlog Tile 的 Ord 一致: 同花色按数字, 赤 5 排在普通 5 前面, 字牌 东南西北白发中."""
    if t in HONORS:
        return 3, HONORS.index(t), 0
    if len(t) >= 2 and t[0].isdigit():
        return "mps".index(t[1]), int(t[0]), 0 if t.endswith("r") else 1
    return 9, 0, 0


def sort_tiles(ts: list[str]) -> list[str]:
    return sorted(ts, key=tile_key)


def remove_tile(hand: list[str], t: str) -> None:
    if t in hand:
        hand.remove(t)
    elif deaka(t) in hand:  # 兜底: 赤宝牌信息不一致时按普通牌删
        hand.remove(deaka(t))


def tile_svg(t: str) -> str:
    """一张牌: 一个 <i>, 用精灵图 (pai-up.svg) 做背景. 比 <svg><use> 少一个节点, 也没有 shadow tree."""
    if t == "back":
        return '<i class="tile bk"></i>'
    return f'<i class="tile k-{esc(t.lower())}"></i>'


def tile_side_svg(t: str) -> str:
    """横置的牌 (立直宣言牌 / 副露被鸣的那张), 用横向精灵图 (pai-side.svg), 不靠 CSS 旋转占位."""
    if t == "back":
        return '<i class="tile side bk"></i>'
    return f'<i class="tile side k-{esc(t.lower())}"></i>'


# 精灵图的列顺序. 行: 0 明牌, 1 牌背 (只有第 0 列), 2 灰牌 (摸切 / 被鸣). 牌名与 pai.svg 里 pai-<名> 对应
SPRITE_TILES = ([f"{n}{s}" for s in "mps" for n in range(1, 10)] + ["5mr", "5pr", "5sr"]
                + [h.lower() for h in HONORS])
SPRITE_ROWS = ((0, "#f2f2f2"), (1, "#ffba1e"), (2, "#c3ccd5"))  # (行, 填充色)
SPRITE_BLUR = 20  # 原来 1.5px 的内阴影, 折算到 320 单位宽的牌上


def sprite_css() -> str:
    """精灵图的 CSS: 背景图 + 每种牌的列位置. 背景按元素尺寸缩放, 所以各处牌的大小规则不用改."""
    n, r = len(SPRITE_TILES), len(SPRITE_ROWS)
    sel = ",".join(f".tile.k-{t}" for t in SPRITE_TILES) + ",.tile.bk"
    side_sel = ",".join(f".tile.side.k-{t}" for t in SPRITE_TILES) + ",.tile.side.bk"
    out = [f"{sel}{{background-image:url(pai-up.png);background-repeat:no-repeat;"
           f"background-size:{n * 100}% {r * 100}%;background-position:0 0}}",
           f"{side_sel}{{background-image:url(pai-side.png)}}"]
    for i, t in enumerate(SPRITE_TILES):
        out.append(f".tile.k-{t}{{background-position-x:{i / (n - 1) * 100:.4f}%}}")
    out.append(".tile.bk{background-position:0 50%}")
    out.append(".rt.tg .tile:not(.bk){background-position-y:100%}")
    return "\n".join(out)


def sprite_sheets(pai_svg: str) -> tuple[str, str]:
    """从 pai.svg 生成两张精灵图 (竖放 / 横放), 返回 (pai-up.svg, pai-side.svg) 的内容."""
    m = re.search(r'<svg style="display: none">(.*)</svg>', pai_svg, flags=re.S)
    defs = m.group(1) if m else ""
    def flt(blur: float) -> str:
        return ('<filter id="inset-shadow"><feOffset dx="0" dy="0"/>'
                f'<feGaussianBlur stdDeviation="{blur}" result="offset-blur"/>'
                '<feComposite operator="out" in="SourceGraphic" in2="offset-blur" result="inverse"/>'
                '<feFlood flood-color="black" flood-opacity="1" result="color"/>'
                '<feComposite operator="in" in="color" in2="inverse" result="shadow"/>'
                '<feComposite operator="over" in="shadow" in2="SourceGraphic"/></filter>')
    n = len(SPRITE_TILES)

    def cell(ref: str, fill: str, x: int, y: int, side: bool) -> str:
        use = (f'<use href="#{ref}" width="320" height="446" fill="{fill}" '
               'filter="url(#inset-shadow)"/>')
        if side:
            return (f'<g transform="translate({x * 446} {y * 320})">'
                    f'<g transform="rotate(-90) translate(-320 0)">{use}</g></g>')
        return f'<g transform="translate({x * 320} {y * 446})">{use}</g>'

    sheets = []
    for side in (False, True):
        w, h = (446, 320) if side else (320, 446)
        cells = []
        for row, fill in SPRITE_ROWS:
            if row == 1:
                cells.append(cell("tile", fill, 0, row, side))
                continue
            for i, t in enumerate(SPRITE_TILES):
                cells.append(cell(f"pai-{t}", fill, i, row, side))
        sheets.append(
            '<svg xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none" '
            f'viewBox="0 0 {n * w} {len(SPRITE_ROWS) * h}">'
            # 横置牌: 原来的滤镜按 446 宽的 viewBox 算, 1.5 的模糊半径近乎没有内阴影, 这里保持一致
            f"<defs>{flt(1.5 if side else SPRITE_BLUR)}{defs}</defs>{''.join(cells)}</svg>")
    return sheets[0], sheets[1]


def tiles_html(ts: list[str]) -> str:
    return "".join(tile_svg(t) for t in ts)


# --------------------------------------------------------------------------------------
# 动作 / 副露 (macros.tera 的 Python 版)
# --------------------------------------------------------------------------------------


def render_action(a: dict[str, Any]) -> str:
    t = a.get("type")
    if t == "none":
        return "跳过"
    if t == "dahai":
        return "打 " + tile_svg(a["pai"])
    if t == "reach":
        return "立直"
    if t == "hora":
        return "自摸" if a.get("target") == a.get("actor") else "荣和"
    if t == "chi":
        return tiles_html(a.get("consumed") or []) + " 吃"
    if t == "pon":
        return tiles_html(a.get("consumed") or []) + " 碰"
    if t in ("kakan", "daiminkan"):
        return "杠 " + tile_svg(a["pai"])
    if t == "ankan":
        return "杠 " + tile_svg((a.get("consumed") or ["back"])[0])
    if t == "ryukyoku":
        return "流局"
    return esc(t)


def action_text(a: dict[str, Any]) -> str:
    """纯文字版 (汇总表里用)."""
    t = a.get("type")
    names = {"none": "跳过", "reach": "立直", "ryukyoku": "流局"}
    if t in names:
        return names[t]
    if t == "dahai":
        return f"打{a['pai']}"
    if t == "hora":
        return "自摸" if a.get("target") == a.get("actor") else "荣和"
    if t == "chi":
        return "吃" + "".join(a.get("consumed") or [])
    if t == "pon":
        return "碰" + "".join(a.get("consumed") or [])
    if t in ("kakan", "daiminkan"):
        return f"杠{a.get('pai')}"
    if t == "ankan":
        return f"杠{(a.get('consumed') or ['?'])[0]}"
    return str(t)


def same_action(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """mortal.rs equal_ignore_aka_consumed 的宽松版; 杠统一当成一类 (details 里的杠都写成 ankan)."""
    ta, tb = a.get("type"), b.get("type")
    if ta in KAN_TYPES and tb in KAN_TYPES:
        ka = a.get("pai") or (a.get("consumed") or [""])[0]
        kb = b.get("pai") or (b.get("consumed") or [""])[0]
        return deaka(ka) == deaka(kb)
    if ta != tb:
        return False
    if ta == "dahai":
        return a.get("pai") == b.get("pai")
    if ta in ("chi", "pon"):
        return sorted(map(deaka, a.get("consumed") or [])) == sorted(map(deaka, b.get("consumed") or []))
    return True


def render_fuuro(f: dict[str, Any], owner: int, small: bool = False) -> str:
    """macros.tera: render_fuuro. owner = 副露所属座位, 横置方向按 target 相对 owner 计算."""
    rot_tile = tile_side_svg if small else None
    t = f.get("type")

    def li(tile: str, rotated: bool = False) -> str:
        if small:
            return f"<span>{rot_tile(tile) if rotated else tile_svg(tile)}</span>"
        cls = ' class="rotated"' if rotated else ""
        return f"<li{cls}>{tile_svg(tile)}</li>"

    def wrap(items: list[str]) -> str:
        if small:
            return '<span class="meld">' + "".join(items) + "</span>"
        return '<ul class="consumed">' + "".join(items) + "</ul>"

    c = f.get("consumed") or []
    if t in ("pon", "chi", "daiminkan"):
        rel = (f.get("target", owner) + 4 - owner) % 4
        called = li(f["pai"], True)
        others = [li(x) for x in c]
        if rel == 1:
            items = others + [called]
        elif rel == 2:
            items = others[:1] + [called] + others[1:]
        else:
            items = [called] + others
        return wrap(items)
    if t == "ankan":
        mid = c[1:3] if len(c) >= 3 else c
        return wrap([li("back")] + [li(x) for x in mid] + [li("back")])
    if t == "kakan":
        rel = (f.get("previous_pon_target", owner) + 4 - owner) % 4
        if small:
            added = ('<span class="stack">' + tile_side_svg(f["pai"])
                     + tile_side_svg(f.get("previous_pon_pai", f["pai"])) + "</span>")
        else:
            added = ('<li class="rotated added">' + tile_svg(f["pai"])
                     + tile_svg(f.get("previous_pon_pai", f["pai"])) + "</li>")
        others = [li(x) for x in c]
        if rel == 1:
            items = others + [added]
        elif rel == 2:
            items = others[:1] + [added] + others[1:]
        else:
            items = [added] + others
        return wrap(items)
    return ""


def render_tehai_state(entry: dict[str, Any], me: int) -> str:
    """macros.tera: render_tehai_state."""
    st = entry.get("state") or {}
    tehai = st.get("tehai") or []
    out = ['<ul class="tehai-state">']
    n = len(tehai)
    for i, t in enumerate(tehai):
        if i < n - 1 or entry.get("at_self_chi_pon"):
            out.append(f"<li>{tile_svg(t)}</li>")
        elif entry.get("at_self_riichi"):
            out.append(f'<li class="tsumo" before="摸 " after=" 立直">{tile_svg(t)}</li>')
        elif entry.get("last_actor") == me:
            out.append(f'<li class="tsumo" before="摸 ">{tile_svg(t)}</li>')
        else:
            out.append(f"<li>{tile_svg(t)}</li>")
            who = SEAT_REL[(entry.get("last_actor", me) + 4 - me) % 4]
            verb = "加杠" if entry.get("at_opponent_kakan") else "打出"
            out.append(f'<li class="tsumo" before="{who}{verb} ">{tile_svg(entry.get("tile", "back"))}</li>')
    for f in reversed(st.get("fuuros") or []):
        out.append(f'<li class="fuuro">{render_fuuro(f, me)}</li>')
    out.append("</ul>")
    return "".join(out)


# --------------------------------------------------------------------------------------
# 重放 mjai_log, 复原牌桌
# --------------------------------------------------------------------------------------


class Table:
    def __init__(self, ev: dict[str, Any]) -> None:
        self.bakaze = BAKAZE.get(ev.get("bakaze", "E"), 0)
        self.kyoku = int(ev.get("kyoku", 1))
        self.honba = int(ev.get("honba", 0))
        self.kyotaku = int(ev.get("kyotaku", 0))
        self.oya = int(ev.get("oya", 0))
        self.scores = list(ev.get("scores") or [25000] * 4)
        self.dora = [ev["dora_marker"]] if ev.get("dora_marker") else []
        self.rivers: list[list[dict[str, Any]]] = [[] for _ in range(4)]
        self.melds: list[list[dict[str, Any]]] = [[] for _ in range(4)]
        self.hands: list[list[str]] = [sort_tiles(list(h)) for h in (ev.get("tehais") or [[]] * 4)]
        self.riichi = [False] * 4
        self.drawn = [False] * 4  # 手牌最后一张是刚摸的牌 (画的时候和手牌隔开)
        self.pending_side = [False] * 4  # 下一张打出的牌要横置 (立直宣言牌, 或宣言牌被鸣后补横)
        self.tiles_left = 70
        self.last_discard: tuple[int, int] | None = None  # (座位, 牌河下标), 用于高亮

    def name(self) -> str:
        return f"{WINDS[self.bakaze]}{self.kyoku}局 {self.honba}本场"

    def apply(self, ev: dict[str, Any]) -> None:
        t = ev.get("type")
        a = ev.get("actor")
        if t == "tsumo":
            self.tiles_left -= 1
            self.hands[a].append(ev["pai"])
            self.drawn[a] = True
            self.last_discard = None
        elif t == "dahai":
            remove_tile(self.hands[a], ev["pai"])
            self.hands[a] = sort_tiles(self.hands[a])
            self.drawn[a] = False
            side = self.pending_side[a]
            self.pending_side[a] = False
            self.rivers[a].append({"pai": ev["pai"], "tg": bool(ev.get("tsumogiri")),
                                   "side": side, "called": False})
            self.last_discard = (a, len(self.rivers[a]) - 1)
        elif t in ("chi", "pon", "daiminkan"):
            tgt = ev.get("target")
            if tgt is not None and self.rivers[tgt]:
                last = self.rivers[tgt][-1]
                last["called"] = True
                if last["side"]:  # 立直宣言牌被鸣, 下一张补横
                    self.pending_side[tgt] = True
            for c in ev.get("consumed") or []:
                remove_tile(self.hands[a], c)
            self.hands[a] = sort_tiles(self.hands[a])
            self.drawn[a] = False
            self.melds[a].append({"type": t, "target": tgt, "pai": ev["pai"],
                                  "consumed": list(ev.get("consumed") or [])})
            self.last_discard = None
        elif t == "kakan":
            remove_tile(self.hands[a], ev["pai"])
            self.hands[a] = sort_tiles(self.hands[a])
            self.drawn[a] = False
            for i, m in enumerate(self.melds[a]):
                if m["type"] == "pon" and deaka(m["pai"]) == deaka(ev["pai"]):
                    self.melds[a][i] = {"type": "kakan", "pai": ev["pai"],
                                        "previous_pon_target": m["target"],
                                        "previous_pon_pai": m["pai"], "consumed": m["consumed"]}
                    break
        elif t == "ankan":
            for c in ev.get("consumed") or []:
                remove_tile(self.hands[a], c)
            self.hands[a] = sort_tiles(self.hands[a])
            self.drawn[a] = False
            self.melds[a].append({"type": "ankan", "consumed": list(ev.get("consumed") or [])})
        elif t == "reach":
            self.pending_side[a] = True
        elif t == "reach_accepted":
            self.riichi[a] = True
            if isinstance(ev.get("scores"), list) and len(ev["scores"]) == 4:
                self.scores = list(ev["scores"])
            else:
                self.scores[a] -= 1000
            self.kyotaku += 1
        elif t == "dora":
            if ev.get("dora_marker"):
                self.dora.append(ev["dora_marker"])

    def snapshot(self) -> dict[str, Any]:
        return {
            "name": self.name(), "bakaze": self.bakaze, "kyoku": self.kyoku,
            "honba": self.honba, "kyotaku": self.kyotaku, "oya": self.oya,
            "scores": list(self.scores), "dora": list(self.dora),
            "rivers": copy.deepcopy(self.rivers), "melds": copy.deepcopy(self.melds),
            "hands": [list(h) for h in self.hands], "drawn": list(self.drawn),
            "riichi": list(self.riichi),
            "tiles_left": self.tiles_left, "last_discard": self.last_discard,
        }


def replay(log: list[dict[str, Any]], me: int) -> list[list[dict[str, Any]]]:
    """
    按 mortal.rs 的循环逐事件推进, 返回每一局里"可能产生 entry 的事件点"列表.
    每个点带对齐用的签名和当时的牌桌快照.
    """
    kyokus: list[list[dict[str, Any]]] = []
    points: list[dict[str, Any]] = []
    table: Table | None = None
    junme = 0
    last_actor = 0
    last_tile: str | None = None
    for ev in log:
        t = ev.get("type")
        if t == "start_kyoku":
            table = Table(ev)
            points = []
        elif table is not None:
            table.apply(ev)

        at_self_chi_pon = at_self_riichi = False
        a = ev.get("actor")
        if t == "end_kyoku":
            kyokus.append(points)
            points = []
            junme = 0
        elif t == "tsumo":
            if a == me:
                last_tile = ev.get("pai")
                junme += 1
        elif t in ("chi", "pon") and a == me:
            at_self_chi_pon = True
            junme += 1
        elif t == "reach" and a == me:
            at_self_riichi = True
        elif t in ("dahai", "kakan"):
            last_tile = ev.get("pai")
        if a is not None:
            last_actor = a

        if t in SKIP_TYPES or table is None:
            continue
        points.append({
            "junme": junme, "tiles_left": table.tiles_left, "last_actor": last_actor,
            "tile": last_tile, "at_self_chi_pon": at_self_chi_pon,
            "at_self_riichi": at_self_riichi, "at_opponent_kakan": t == "kakan",
            "tehai": sort_tiles(table.hands[me]), "event": ev, "snap": table.snapshot(),
        })
    if points:  # 日志没有 end_kyoku 收尾
        kyokus.append(points)
    return kyokus


def align(entries: list[dict[str, Any]], points: list[dict[str, Any]]) -> list[dict[str, Any] | None]:
    """entries 是 points 的子序列, 顺序贪婪匹配签名 + 手牌."""
    out: list[dict[str, Any] | None] = []
    p = 0
    for e in entries:
        tehai = sort_tiles((e.get("state") or {}).get("tehai") or [])
        hit = None
        for i in range(p, len(points)):
            c = points[i]
            if (c["junme"] == e.get("junme") and c["tiles_left"] == e.get("tiles_left")
                    and c["last_actor"] == e.get("last_actor") and c["tile"] == e.get("tile")
                    and c["at_self_chi_pon"] == bool(e.get("at_self_chi_pon"))
                    and c["at_self_riichi"] == bool(e.get("at_self_riichi"))
                    and c["at_opponent_kakan"] == bool(e.get("at_opponent_kakan"))
                    and c["tehai"] == tehai):
                hit = i
                break
        if hit is None:
            out.append(None)
        else:
            out.append(points[hit])
            p = hit + 1
    return out


# --------------------------------------------------------------------------------------
# 牌桌 HTML
# --------------------------------------------------------------------------------------


def render_board(snap: dict[str, Any], me: int, names: list[str]) -> str:
    parts = ['<div class="board">']
    dora = snap["dora"][:5]
    dora_html = tiles_html(dora + ["back"] * (5 - len(dora)))
    parts.append(
        '<div class="center">'
        f'<div class="kyoku-name">{esc(snap["name"])}</div>'
        f'<div>供托 {snap["kyotaku"]}　余 {snap["tiles_left"]} 张</div>'
        f'<div class="dora">{dora_html}</div>'
        "</div>")
    for seat in range(4):
        rel = (seat + 4 - me) % 4
        river = snap["rivers"][seat]
        rows: list[str] = []
        # 每行 6 张, 第 3 行起不再换行 (与雀魂 / 天凤一致)
        for r, chunk in ((0, river[0:6]), (6, river[6:12]), (12, river[12:])):
            if not chunk:
                break
            cells = []
            for k, d in enumerate(chunk, start=r):
                cls = ["rt"]
                if d["tg"]:
                    cls.append("tg")
                if d["called"]:
                    cls.append("called")
                if snap["last_discard"] == (seat, k):
                    cls.append("hl")
                svg = tile_side_svg(d["pai"]) if d["side"] else tile_svg(d["pai"])
                cells.append(f'<span class="{" ".join(cls)}">{svg}</span>')
            rows.append('<div class="row">' + "".join(cells) + "</div>")
        melds = "".join(render_fuuro(m, seat, small=True) for m in snap["melds"][seat])
        hand = render_board_hand(snap["hands"][seat], bool(snap.get("drawn", [False] * 4)[seat]),
                                 hidden_ok=rel != 0)
        wind = WINDS[(seat - snap["oya"]) % 4]
        lab_cls = ["seat-label"]
        if seat == snap["oya"]:
            lab_cls.append("oya")
        if rel == 0:
            lab_cls.append("self")
        riichi = '<span class="riichi">立直</span>' if snap["riichi"][seat] else ""
        who = esc(names[seat]) if seat < len(names) and names[seat] else SEAT_REL[rel]
        title = f'{SEAT_REL[rel]} {who}'
        parts.append(
            f'<div class="layer r{rel}">'
            f'<div class="{" ".join(lab_cls)}" title="{title}">'
            f'<span class="wind">{wind}</span> {snap["scores"][seat]}{riichi}</div>'
            f'<div class="river">{"".join(rows)}</div>'
            f'<div class="hand-row">{hand}<div class="melds">{melds}</div></div>'
            "</div>")
    parts.append('<button type="button" class="reveal-btn" title="只切换这一张牌桌">他家手牌</button>')
    parts.append("</div>")
    return "".join(parts)


def render_board_hand(tiles: list[str], drawn: bool, hidden_ok: bool) -> str:
    """牌桌边缘的手牌. 他家手牌同时画明牌和牌背两份, 由页面上的开关决定显示哪一份."""
    def row(ts: list[str]) -> str:
        if drawn and ts:
            return tiles_html(ts[:-1]) + f'<span class="drawn">{tile_svg(ts[-1])}</span>'
        return tiles_html(ts)

    if not hidden_ok:
        return f'<div class="hand">{row(tiles)}</div>'
    return (f'<div class="hand opp open">{row(tiles)}</div>'
            f'<div class="hand opp closed">{row(["back"] * len(tiles))}</div>')


HAND_TOGGLE = """
<label class="hand-toggle"><input type="checkbox" id="show-hands"> 牌桌上显示他家手牌（复盘用，实战中不可见）</label>
<script>
(function () {
  var KEY = "diffReport.showHands";
  var box = document.getElementById("show-hands");
  function apply(on) {
    document.body.classList.toggle("show-hands", on);
    document.querySelectorAll(".board.reveal").forEach(function (b) { b.classList.remove("reveal"); });
  }
  var saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) {}
  box.checked = saved === null ? true : saved === "1";
  apply(box.checked);
  box.addEventListener("change", function () {
    try { localStorage.setItem(KEY, box.checked ? "1" : "0"); } catch (e) {}
    apply(box.checked);
  });
  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest && ev.target.closest(".reveal-btn");
    if (btn) btn.parentElement.classList.toggle("reveal");
  });
})();
</script>
"""


# --------------------------------------------------------------------------------------
# 单局报告
# --------------------------------------------------------------------------------------


def kyoku_title(k: dict[str, Any]) -> str:
    idx = int(k.get("kyoku", 0))
    return f"{WINDS[(idx // 4) % 4]}{idx % 4 + 1}局 {k.get('honba', 0)}本场"


def end_status_text(k: dict[str, Any], me: int) -> str:
    out = []
    for s in k.get("end_status") or []:
        if s.get("type") == "hora":
            a = s.get("actor", 0)
            who = SEAT_REL[(a + 4 - me) % 4]
            d = (s.get("deltas") or [0] * 4)[a]
            kind = "自摸" if s.get("target") == a else "荣和"
            out.append(f"{who}{kind} {d:+d}")
        else:
            out.append("流局")
    return "，".join(out)


def entry_metrics(e: dict[str, Any]) -> dict[str, Any]:
    details = e.get("details") or []
    ai = e.get("actual_index")
    if not isinstance(ai, int) or not 0 <= ai < len(details):
        ai = next((i for i, d in enumerate(details) if same_action(d["action"], e["actual"])), -1)
    ei = next((i for i, d in enumerate(details) if same_action(d["action"], e["expected"])), 0)
    q_ai = details[ai]["q_value"] if 0 <= ai < len(details) else None
    q_ei = details[ei]["q_value"] if details else None
    return {
        "actual_idx": ai, "expected_idx": ei,
        "loss": (q_ei - q_ai) if q_ai is not None and q_ei is not None else None,
        "p_actual": details[ai]["prob"] if 0 <= ai < len(details) else None,
        "p_expected": details[ei]["prob"] if details else None,
    }


EFF_TOP = 3  # 牌效只算 Mortal 排在前面的这几个打牌选择, 再加上玩家自己打的那张


def efficiency_targets(e: dict[str, Any]) -> list[str] | None:
    """
    该打牌的局面只算这些牌: Mortal Q 值最高的前 EFF_TOP 个打牌, 以及玩家实际打出的牌.
    不是打牌的局面 (鸣牌/和牌判断) 返回 None, 只算当前手牌的向听和进张.
    """
    act = e.get("actual") or {}
    if act.get("type") != "dahai" and (e.get("expected") or {}).get("type") != "dahai":
        return None
    tiles: list[str] = []
    for d in (e.get("details") or [])[:EFF_TOP]:
        a = d.get("action") or {}
        if a.get("type") == "dahai" and a.get("pai") not in tiles:
            tiles.append(a["pai"])
    if act.get("type") == "dahai" and act.get("pai") not in tiles:
        tiles.append(act["pai"])
    return tiles


def entry_efficiency(e: dict[str, Any], pt: dict[str, Any] | None) -> dict[str, Any] | None:
    if eff is None:
        return None
    st = e.get("state") or {}
    try:
        return eff.analyze(list(st.get("tehai") or []), list(st.get("fuuros") or []),
                           pt["snap"] if pt else None, efficiency_targets(e))
    except Exception:  # noqa: BLE001  算不出来就不显示, 不影响报告
        return None


def waits_html(waits: list[tuple[int, int]]) -> str:
    """待牌: 牌图*剩余枚数, 已经没有剩余的那种灰掉. 文字写在 title 里, 悬停可见."""
    if not waits:
        return '<span class="muted">无</span>'
    out = []
    for i, c in waits:
        t = eff.index_tile(i)
        cls = "w dead" if c == 0 else "w"
        out.append(f'<span class="{cls}" title="{esc(eff.tile_name(t))}*{c}">'
                   f'{tile_svg(t)}<b>*{c}</b></span>')
    return "".join(out)


def waits_title(waits: list[tuple[int, int]]) -> str:
    """待牌的纯文字, 放在牌效行的 title 上, 悬停整行就能看, 不用再画一遍牌."""
    if not waits:
        return "无进张"
    body = " ".join(f"{eff.tile_name(eff.index_tile(i))}*{c}" for i, c in waits)
    return f"{body}（共 {sum(c for _, c in waits)} 枚 / {len(waits)} 种）"


def shanten_change(now: int, after: int) -> str:
    s = esc(eff.shanten_text(after))
    if after > now:
        return f'<span class="back-sh">{s}（退向）</span>'
    return s


def eff_brief(res: dict[str, Any] | None, a: dict[str, Any]) -> str:
    """一行文字: 打8索 → 2 向听 / 进张 24 枚 (6 种)."""
    if not res or a.get("type") != "dahai":
        return ""
    r = eff.find_row(res, a.get("pai"))
    if r is None:
        return ""
    return f"{eff.shanten_text(r['shanten'])} 进张 {r['total']} 枚/{r['kinds']} 种"


def render_efficiency(res: dict[str, Any] | None, e: dict[str, Any]) -> str:
    if not res:
        return ""
    now = res["shanten"]
    if res["kind"] == "wait":
        return ('<div class="eff"><h4>牌效（当前手牌）</h4>'
                f'<p>{esc(eff.shanten_text(now))}，进张 {res["total"]} 枚 / {len(res["waits"])} 种：'
                f'{waits_html(res["waits"])}</p></div>')

    act = e.get("actual") or {}
    exp = e.get("expected") or {}
    ia = eff.tile_index(act["pai"]) if act.get("type") == "dahai" else -1
    ie = eff.tile_index(exp["pai"]) if exp.get("type") == "dahai" else -1
    rows = []
    for r in res["rows"]:
        cls = []
        if r["index"] == ia:
            cls.append("actual")
        elif r["index"] == ie:
            cls.append("expected")
        best = r["shanten"] == res["best_shanten"] and r["total"] == res["best_total"]
        if best:
            cls.append("best")
        mark = []
        if r["index"] == ia:
            mark.append("自己")
        if r["index"] == ie:
            mark.append("Mortal")
        if best:
            mark.append("进张最多")
        rows.append(
            f'<tr class="{" ".join(cls)}"><td>{tile_svg(r["tile"])}</td>'
            f'<td>{shanten_change(now, r["shanten"])}</td>'
            f'<td class="num">{r["total"]}<small>/{r["kinds"]}种</small></td>'
            f'<td class="waits">{waits_html(r["waits"])}</td>'
            f'<td class="mark">{"<br>".join(mark)}</td></tr>')
    note = (f'只列 Mortal 前 {EFF_TOP} 优先和自己打的牌。'
            if res.get("partial") else '')
    return (
        '<div class="eff"><h4>牌效：打出后的向听与进张</h4>'
        f'<p class="muted">打牌前 {esc(eff.shanten_text(now))}。进张 = 摸到能让向听数减少的牌，'
        '“*N” 是除去自己手牌、副露、牌河和宝牌指示牌后还剩的枚数（他家手牌看不到，按未知计）。'
        f'{note}按 向听 → 进张枚数 排序。</p>'
        + hscroll('<table class="data eff-table"><thead><tr><th>打</th><th>打后向听</th><th>进张</th>'
                  '<th>待牌（种类*枚数）</th><th></th></tr></thead>'
                  f'<tbody>{"".join(rows)}</tbody></table>')
        + '</div>')


def render_entry(e: dict[str, Any], pt: dict[str, Any] | None, me: int, names: list[str],
                 anchor: str, m: dict[str, Any], res: dict[str, Any] | None = None) -> str:
    info = []
    sh = e.get("shanten")
    if isinstance(sh, int):
        info.append("听牌" if sh == 0 else f"{sh} 向听")
    if e.get("at_furiten"):
        info.append("振听")
    details = e.get("details") or []
    if m["actual_idx"] >= 0:
        info.append(f'<span class="order-loss">#{m["actual_idx"] + 1}</span>/{len(details)}')
    if m["loss"] is not None:
        info.append(f"Q 损失 {m['loss']:.3f}")

    p_a = "" if m["p_actual"] is None else f'<span class="p">{m["p_actual"] * 100:.1f}%</span>'
    p_e = "" if m["p_expected"] is None else f'<span class="p">{m["p_expected"] * 100:.1f}%</span>'
    b_a, b_e = eff_brief(res, e["actual"]), eff_brief(res, e["expected"])
    b_a = f'<span class="eff-brief">{esc(b_a)}</span>' if b_a else ""
    b_e = f'<span class="eff-brief">{esc(b_e)}</span>' if b_e else ""
    side = [
        render_tehai_state(e, me),
        '<div class="cmp">'
        f'<span class="role">自己:</span><span class="mine">{render_action(e["actual"])}</span>{p_a}{b_a}<br>'
        f'<span class="role">Mortal:</span><span class="ai">{render_action(e["expected"])}</span>{p_e}{b_e}'
        "</div>",
        render_efficiency(res, e),
    ]
    if details:
        rows = []
        for i, d in enumerate(details):
            cls = ""
            if i == m["actual_idx"]:
                cls = ' class="actual"'
            elif i == m["expected_idx"]:
                cls = ' class="expected"'
            rows.append(f"<tr{cls}><td>{render_action(d['action'])}</td>"
                        f"<td>{d['q_value']:.5f}</td><td>{d['prob'] * 100:.3f}</td></tr>")
        side.append(hscroll('<table class="data cands"><thead><tr><th>候选动作</th><th>Q 值</th>'
                            '<th>概率 ×100</th></tr></thead><tbody>' + "".join(rows)
                            + "</tbody></table>"))

    if pt is not None:
        board = f'<div class="board-slot">{render_board(pt["snap"], me, names)}</div>'
    else:
        board = ""
        side.insert(0, '<p class="warn">这一处没能在 mjai_log 里定位到对应事件，只显示手牌。</p>')

    # 牌桌 + 候选表是 DOM 大头 (一手约 400 个节点, 一局上百手): 先放进 <template> (不解析成节点),
    # 由 LAZY_JS 在滚到附近时再展开, 打开页面时只渲染标题和目录
    return (f'<section class="entry" id="{anchor}">'
            f'<h3>第 {e.get("junme", "?")} 巡（余 {e.get("tiles_left", "?")} 张）'
            f'<span class="info">{"　".join(info)}</span></h3>'
            '<div class="entry-ph">载入中 ...</div>'
            f'<template><div class="entry-body">{board}'
            f'<div class="entry-side">{"".join(side)}</div></div></template>'
            "</section>")


# 牌桌内部按 600px 排版; 屏幕窄时按外框宽度整体缩放 (CSS 算不了「宽度 / 600px」, 用脚本设 --bs)
BOARD_FIT = """<script>
(function () {
  function fit(root) {
    (root || document).querySelectorAll(".board-slot").forEach(function (s) {
      var w = s.clientWidth;
      if (w) s.style.setProperty("--bs", Math.min(1, w / 600));
    });
  }
  window.mjrFit = fit;
  window.addEventListener("resize", function () { fit(); });
})();
</script>"""

# 每一手的内容在 <template> 里, 滚到离视口 1.5 屏内才展开 (每帧最多展开一手, 不打断滚动);
# 点目录跳转时目标那手马上展开
LAZY_JS = """<script>
(function () {
  var queue = [], busy = false;
  function hydrate(sec) {
    var t = sec.querySelector(":scope > template"), ph = sec.querySelector(":scope > .entry-ph");
    if (!t) return;
    var frag = t.content;
    t.remove();
    sec.appendChild(frag);
    if (ph) ph.remove();
    if (window.mjrFit) window.mjrFit(sec);
  }
  function pump() {
    var sec = queue.shift();
    if (!sec) { busy = false; return; }
    hydrate(sec);
    requestAnimationFrame(pump);
  }
  function enqueue(sec) {
    queue.push(sec);
    if (!busy) { busy = true; requestAnimationFrame(pump); }
  }
  var secs = document.querySelectorAll("section.entry");
  if (!("IntersectionObserver" in window)) { secs.forEach(hydrate); return; }
  var io = new IntersectionObserver(function (list) {
    list.forEach(function (it) {
      if (it.isIntersecting) { io.unobserve(it.target); enqueue(it.target); }
    });
  }, {rootMargin: "1500px 0px"});

  // 目录 / 汇总页带 #锚点 跳进来: 先展开目标再滚过去; 上方的几手随后展开会把它挤下去,
  // 所以连续几帧都把它对回视口顶部 (用户一开始滚动就停止)
  var pin = null, pinFrames = 0;
  function stopPin() { pin = null; }
  ["wheel", "touchstart", "keydown", "mousedown"].forEach(function (n) {
    window.addEventListener(n, stopPin, {passive: true});
  });
  function repin() {
    if (!pin) return;
    pin.scrollIntoView({behavior: "instant", block: "start"});  // CSS 是 smooth, 这里要瞬时
    if (--pinFrames > 0) requestAnimationFrame(repin); else pin = null;
  }
  function jump() {
    var el = location.hash && document.getElementById(decodeURIComponent(location.hash.slice(1)));
    if (!el || !el.matches("section.entry")) return;
    hydrate(el);
    pin = el; pinFrames = 90;
    requestAnimationFrame(repin);
  }
  jump();
  secs.forEach(function (s) { if (s.querySelector(":scope > template")) io.observe(s); });
  window.addEventListener("hashchange", jump);
})();
</script>"""


def hscroll(html: str) -> str:
    """表格外包一层: 手机上放不下时横向滑动, 不撑破页面."""
    return f'<div class="hscroll">{html}</div>'


def page(title: str, body: str, css: str, svg: str) -> str:
    fit = BOARD_FIT if 'class="board-slot"' in body or "<template>" in body else ""
    lazy = LAZY_JS if "<template>" in body else ""
    return ("<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>{esc(title)}</title>"
            f"<style>{css}</style></head><body>{body}{svg}{fit}{lazy}</body></html>")


def game_when(g: dict[str, Any]) -> str:
    ts = g.get("start_time") or 0
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else "-"


def mode_name(mode_id: Any) -> str:
    try:
        from mahjong_rating import MODE_BY_ID
        return MODE_BY_ID.get(mode_id, str(mode_id))
    except Exception:  # noqa: BLE001
        return str(mode_id)


def build_game(report: dict[str, Any], g: dict[str, Any], css: str, svg: str,
               index_name: str = "index.html") -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    """返回 (HTML, 差异项摘要列表, 统计)."""
    review = report.get("review") or {}
    kyokus = review.get("kyokus") or []
    me = int(report.get("player_id", g.get("seat", 0)) or 0)
    log = report.get("mjai_log") if isinstance(report.get("mjai_log"), list) else []
    names: list[str] = []
    for ev in log[:3]:
        if ev.get("type") == "start_game":
            names = list(ev.get("names") or [])
    points_by_kyoku = replay(log, me) if log else []

    diffs: list[dict[str, Any]] = []
    sections: list[str] = []
    toc: list[str] = []
    n_aligned = n_diff = 0
    for ki, k in enumerate(kyokus):
        entries = k.get("entries") or []
        pts = align(entries, points_by_kyoku[ki]) if ki < len(points_by_kyoku) else [None] * len(entries)
        title = kyoku_title(k)
        items = []
        for ei, (e, pt) in enumerate(zip(entries, pts)):
            if e.get("is_equal", True):
                continue
            n_diff += 1
            n_aligned += pt is not None
            anchor = f"k{ki}e{ei}"
            m = entry_metrics(e)
            res = entry_efficiency(e, pt)
            items.append(render_entry(e, pt, me, names, anchor, m, res))
            diffs.append({"anchor": anchor, "kyoku": title, "junme": e.get("junme"),
                          "actual": action_text(e["actual"]), "expected": action_text(e["expected"]),
                          "loss": m["loss"], "p_actual": m["p_actual"],
                          "eff_actual": eff_brief(res, e["actual"]),
                          "eff_expected": eff_brief(res, e["expected"])})
        end = end_status_text(k, me)
        if items:
            toc.append(f'<li><a href="#kyoku{ki}">{esc(title)}</a> {len(items)} 处</li>')
            sections.append(f'<h2 class="kyoku" id="kyoku{ki}">{esc(title)}'
                            f'<span class="end-status">{esc(end)}</span></h2>' + "".join(items))
        else:
            toc.append(f'<li class="muted">{esc(title)} 0 处</li>')

    total = review.get("total_reviewed")
    matches = review.get("total_matches")
    rating = review.get("rating")
    me_name = names[me] if me < len(names) else ""
    task = g.get("report_task") or ""
    links = [f'<a href="{esc(g["record_url"])}" target="_blank" rel="noreferrer">雀魂牌谱</a>'] \
        if g.get("record_url") else []
    if task:
        links.append(f'<a href="https://mjai.ekyu.moe/report/{esc(task)}.html" target="_blank" '
                     'rel="noreferrer">mjai 原报告</a>（在线约保留 15 天）')
    warn = ""
    if not log:
        warn = '<p class="warn">报告里没有 mjai_log，无法复原牌桌，只显示手牌与候选。</p>'
    elif n_aligned < n_diff:
        warn = f'<p class="warn">{n_diff - n_aligned} 处差异没能对齐到牌桌事件。</p>'
    seat_names = "　".join(f"{SEAT_REL[(i + 4 - me) % 4]}: {esc(n)}" for i, n in enumerate(names))
    head = (
        f'<p><a href="{index_name}">← 返回汇总</a></p>'
        f"<h1>差异项报告</h1>"
        f'<div class="subtitle">{esc(game_when(g))}　{esc(mode_name(g.get("mode_id")))}　'
        f'{g.get("rank", "-")}位　{g.get("score", "-")}点</div>'
        '<dl class="meta">'
        f"<dt>玩家</dt><dd>{esc(me_name)}（座位 {me}，{esc(seat_names)}）</dd>"
        f"<dt>引擎</dt><dd>{esc(report.get('engine', ''))} {esc(review.get('model_tag', ''))}"
        f"　温度 {esc(review.get('temperature', ''))}</dd>"
        f"<dt>Rating</dt><dd>{'-' if rating is None else f'{rating * 100:.1f}'}</dd>"
        f"<dt>AI 一致率</dt><dd>{matches}/{total}"
        f"{'' if not total else f'（{matches / total * 100:.1f}%）'}</dd>"
        f"<dt>差异项</dt><dd>{n_diff} 处（自己的选择与 Mortal 首选不同的全部决策点）</dd>"
        f"<dt>链接</dt><dd>{'　'.join(links) or '-'}</dd>"
        "</dl>"
        f"{warn}"
        f'<ul class="toc">{"".join(toc)}</ul>'
        f"{HAND_TOGGLE if log else ''}"
    )
    body = head + ("".join(sections) or "<p>这一局没有差异项。</p>")
    stats = {"diffs": n_diff, "aligned": n_aligned, "total": total, "matches": matches,
             "rating": rating, "has_log": bool(log)}
    return page(f"差异项 {game_when(g)}", body, css, svg), diffs, stats


# --------------------------------------------------------------------------------------
# 汇总
# --------------------------------------------------------------------------------------


def find_report(reports_dir: pathlib.Path, g: dict[str, Any]) -> pathlib.Path | None:
    if g.get("report_file"):
        p = reports_dir / g["report_file"]
        if p.exists():
            return p
    hits = sorted(reports_dir.glob(f"{g.get('uuid', '?')}_a*.json"))
    return hits[0] if hits else None


def build(out_dir: pathlib.Path | str, uid: int, games: list[Any],
          nickname: str = "", reports_dir: pathlib.Path | str | None = None,
          label: str = "") -> pathlib.Path | None:
    """
    生成 out_dir/diff_<uid>/ 下的单局报告和 index.html; 没有任何本地报告时返回 None.
    reports_dir: 原始报告所在目录, 默认 players/<uid>/reports/.
    label: 这批对局是怎么选出来的 (显示在汇总页标题下).
    """
    from dataclasses import asdict, is_dataclass

    out_dir = pathlib.Path(out_dir)
    if reports_dir is None:
        import store
        reports_dir = store.default_root() / str(uid) / "reports"
    reports_dir = pathlib.Path(reports_dir)
    gs = [asdict(g) if is_dataclass(g) else dict(g) for g in games]
    gs.sort(key=lambda g: g.get("start_time") or 0, reverse=True)
    avail = [(g, find_report(reports_dir, g)) for g in gs]
    if not any(p for _, p in avail):
        print("  ! 没有本地保存的原始报告, 跳过差异报告")
        return None

    a = assets_dir()
    css = (a / "diff_report.css").read_text(encoding="utf-8")
    css += "\n" + sprite_css()
    dest = out_dir / f"diff_{uid}"
    dest.mkdir(parents=True, exist_ok=True)
    for png in ("pai-up.png", "pai-side.png"):  # 预先栅格化好的精灵图 (由 pai.svg 经 sprite_sheets 生成)
        shutil.copyfile(a / png, dest / png)
    svg = ""  # 牌面不再内联 122KB 的 pai.svg
    for old in dest.glob("*.html"):  # 上次选的局留下的单局页, 换了选择就不该再出现
        try:
            old.unlink()
        except OSError:
            pass

    rows: list[str] = []
    all_diffs: list[dict[str, Any]] = []
    n_games = n_diffs = 0
    for g, path in avail:
        base = (f"<td>{esc(game_when(g))}</td><td>{esc(mode_name(g.get('mode_id')))}</td>"
                f"<td>{g.get('rank', '-')}</td><td>{g.get('score', '-')}</td>")
        if path is None:
            reason = g.get("error") or ("没存原始报告" if g.get("rating") is not None else "未跑谱")
            rows.append(f'<tr class="muted">{base}<td>{g.get("rating") or "-"}</td><td>-</td>'
                        f'<td>-</td><td>{esc(reason[:60])}</td></tr>')
            continue
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            doc, diffs, st = build_game(report, g, css, svg)
        except Exception as exc:  # noqa: BLE001  某一局坏了不影响其它局
            rows.append(f'<tr class="muted">{base}<td>-</td><td>-</td><td>-</td>'
                        f'<td>生成失败: {esc(exc)}</td></tr>')
            print(f"    ! 差异报告生成失败 {game_when(g)}: {exc}")
            continue
        fname = f"{g.get('uuid', path.stem)}.html"
        (dest / fname).write_text(doc, encoding="utf-8")
        n_games += 1
        n_diffs += st["diffs"]
        for d in diffs:
            d.update(file=fname, when=game_when(g))
        all_diffs += diffs
        acc = (f"{st['matches']}/{st['total']}（{st['matches'] / st['total'] * 100:.1f}%）"
               if st["total"] else "-")
        rating = "-" if st["rating"] is None else f"{st['rating'] * 100:.1f}"
        note = "" if st["has_log"] else "无 mjai_log，无牌桌"
        if st["has_log"] and st["aligned"] < st["diffs"]:
            note = f"{st['diffs'] - st['aligned']} 处未对齐"
        rows.append(f"<tr>{base}<td>{rating}</td><td>{acc}</td>"
                    f'<td><a href="{esc(fname)}">{st["diffs"]} 处</a></td><td>{esc(note)}</td></tr>')

    top = sorted((d for d in all_diffs if d["loss"] is not None), key=lambda d: -d["loss"])[:30]
    top_rows = "".join(
        f'<tr><td>{esc(d["when"])}</td><td>{esc(d["kyoku"])}</td><td>{d["junme"]}</td>'
        f'<td>{esc(d["actual"])}<br><small class="muted">{esc(d.get("eff_actual", ""))}</small></td>'
        f'<td>{esc(d["expected"])}<br><small class="muted">{esc(d.get("eff_expected", ""))}</small></td>'
        f'<td>{d["loss"]:.3f}</td>'
        f'<td><a href="{esc(d["file"])}#{d["anchor"]}">查看</a></td></tr>' for d in top)
    who = f"{esc(nickname)} (UID {uid})" if nickname else f"UID {uid}"
    body = (
        f"<h1>差异项汇总</h1><div class=\"subtitle\">{who}　"
        f"{esc(label) + '　' if label else ''}共 {n_games} 局有报告，"
        f"差异项 {n_diffs} 处　生成于 {time.strftime('%Y-%m-%d %H:%M')}</div>"
        "<h2>对局列表</h2>"
        + hscroll('<table class="data games"><thead><tr><th>时间</th><th>场次</th><th>顺位</th>'
                  "<th>点数</th><th>Rating</th><th>AI 一致率</th><th>差异项</th><th>备注</th></tr></thead>"
                  f"<tbody>{''.join(rows)}</tbody></table>")
        + "<h2>Q 值损失最大的差异项</h2>"
        '<p class="muted">Q 损失 = Mortal 首选的 Q 值 − 自己选择的 Q 值，越大说明偏离越多。'
        '打牌项下面的小字是打出后的向听和进张枚数。</p>'
        + hscroll('<table class="data games"><thead><tr><th>对局</th><th>局</th><th>巡</th><th>自己</th>'
                  "<th>Mortal</th><th>Q 损失</th><th></th></tr></thead>"
                  f"<tbody>{top_rows or '<tr><td colspan=7>无</td></tr>'}</tbody></table>")
    )
    index = dest / "index.html"
    index.write_text(page(f"差异项汇总 {uid}", body, css, ""), encoding="utf-8")
    print(f"  [OK] 差异报告: {index}  ({n_games} 局, {n_diffs} 处差异)")
    return index


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="用已保存的 mjai 报告重新生成差异项报告")
    ap.add_argument("out", nargs="?", default="rating_out", help="输出目录 (默认 rating_out)")
    ap.add_argument("--id", default="", help="UID 或昵称 (默认: 最近一次跑的玩家)")
    ap.add_argument("--data", default=None, help="玩家数据目录 (默认: 程序目录下的 players/)")
    ap.add_argument("--all", action="store_true",
                    help="用本地全部对局 (默认只用上次运行新增的局)")
    ap.add_argument("--open", action="store_true", help="生成后用浏览器打开汇总页")
    args = ap.parse_args()
    index = rebuild(args.out, args.id, args.data, args.all)
    if index and args.open:
        import webbrowser
        webbrowser.open(index.resolve().as_uri())
    return 0 if index else 1


def build_selection(out: pathlib.Path | str, st: Any, uuids: list[str] | None = None,
                    label: str = "") -> pathlib.Path | None:
    """
    按选中的对局生成差异报告. uuids=None 时用默认选择 (上次运行新增的局;
    没有新增就用上次运行的全部; 再没有就是本地全部).
    """
    if uuids is None:
        uuids, label = st.default_selection()
    lib = {g["uuid"]: g for g in st.library()}
    games = [lib[u] for u in uuids if u in lib]
    if not games:
        print("  ! 没有选中任何有本地报告的对局, 跳过差异报告")
        return None
    return build(out, st.uid, games, st.profile.get("nickname", ""),
                 reports_dir=st.reports_dir, label=label)


def rebuild(out: pathlib.Path | str, ident: str = "",
            data: pathlib.Path | str | None = None, all_games: bool = False) -> pathlib.Path | None:
    """离线重建: 读 players/<UID>/ 里的对局和报告, 不联网."""
    import store

    root = pathlib.Path(data) if data else store.default_root()
    uid = store.resolve_local(root, ident)
    if uid is None:
        print(f"{root} 里没有{'玩家 ' + ident if ident else '任何玩家'}的数据, 先跑一次 mahjong_rating.py")
        return None
    st = store.PlayerStore(root, uid)
    if all_games:
        return build_selection(out, st, [g["uuid"] for g in st.library()], "全部本地对局")
    return build_selection(out, st)


if __name__ == "__main__":
    raise SystemExit(main())
