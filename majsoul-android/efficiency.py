"""牌效分析: 打每张牌后的向听数与进张 (待牌种类*剩余枚数).

向听数用 MahjongRepository/mahjong (https://github.com/MahjongRepository/mahjong, MIT,
经天凤牌谱验证) 的 Shanten.calculate_shanten, 一般形/七对子/国士取最小.
进张 = 加进来能让向听数减少的牌; 剩余枚数 = 4 - 自己手里 - 场上看得见的 (牌河/副露/宝牌指示牌).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from mahjong.shanten import Shanten

HONORS = "ESWNPFC"
HONOR_NAMES = "东南西北白发中"
SUIT_NAMES = {"m": "万", "p": "筒", "s": "索"}


def deaka(t: str) -> str:
    return t[:-1] if t.endswith("r") else t


def tile_index(t: str) -> int:
    """mjai 牌名 -> 34 种编号 (1m..9m=0..8, p=9..17, s=18..26, 东南西北白发中=27..33); 认不出返回 -1."""
    t = deaka(t)
    if t in HONORS:
        return 27 + HONORS.index(t)
    if len(t) == 2 and t[0].isdigit() and t[1] in "mps" and t[0] != "0":
        return "mps".index(t[1]) * 9 + int(t[0]) - 1
    return -1


def index_tile(i: int) -> str:
    """34 种编号 -> mjai 牌名 (画牌用)."""
    return HONORS[i - 27] if i >= 27 else f"{i % 9 + 1}{'mps'[i // 9]}"


def tile_name(t: str) -> str:
    """mjai 牌名 -> 中文 (5m -> 5万, E -> 东)."""
    t = deaka(t)
    if t in HONORS:
        return HONOR_NAMES[HONORS.index(t)]
    return f"{t[0]}{SUIT_NAMES.get(t[1:], t[1:])}" if len(t) == 2 else t


def to_34(tiles: list[str]) -> list[int]:
    a = [0] * 34
    for t in tiles:
        i = tile_index(t)
        if i >= 0:
            a[i] += 1
    return a


@lru_cache(maxsize=200_000)
def _shanten(key: tuple[int, ...]) -> int:
    return Shanten.calculate_shanten(list(key))


def shanten(a: list[int]) -> int:
    """-1 = 和了, 0 = 听牌, n = n 向听."""
    return _shanten(tuple(a))


def ukeire(a: list[int], remaining: list[int]) -> tuple[int, list[tuple[int, int]]]:
    """
    a: 3n+1 张的手牌. 返回 (向听, [(牌编号, 剩余枚数), ...]).
    手里已经有 4 张的那种牌摸不到, 不算进张.
    """
    base = shanten(a)
    waits = []
    for i in range(34):
        if a[i] >= 4:
            continue
        a[i] += 1
        if shanten(a) < base:
            waits.append((i, max(remaining[i], 0)))
        a[i] -= 1
    return base, waits


def visible_counts(tehai: list[str], fuuros: list[dict[str, Any]],
                   snap: dict[str, Any] | None) -> list[int]:
    """自己能看到的每种牌的张数: 手牌 + 所有副露 + 牌河 (被鸣走的不重复算) + 宝牌指示牌."""
    seen = to_34(tehai)

    def add(ts: list[str]) -> None:
        for t in ts:
            i = tile_index(t)
            if i >= 0:
                seen[i] += 1

    def meld_tiles(m: dict[str, Any]) -> list[str]:
        t = m.get("type")
        c = list(m.get("consumed") or [])
        if t == "ankan":
            return c
        if t == "kakan":
            return c + [m.get("previous_pon_pai") or m.get("pai", ""), m.get("pai", "")]
        return c + [m.get("pai", "")]

    if snap:
        for melds in snap.get("melds") or []:
            for m in melds:
                add(meld_tiles(m))
        for river in snap.get("rivers") or []:
            add([r["pai"] for r in river if not r.get("called")])
        add(list(snap.get("dora") or []))
    else:  # 没对齐到牌桌: 只知道自己的副露
        for m in fuuros:
            add(meld_tiles(m))
    return [min(n, 4) for n in seen]


def analyze(tehai: list[str], fuuros: list[dict[str, Any]],
            snap: dict[str, Any] | None, only: list[str] | None = None) -> dict[str, Any] | None:
    """
    手牌 3n+2 张 (该打牌): 算打出后的向听和进张.
    only 给出时只算这些牌 (Mortal 前几优先 + 玩家实际打的牌), 不扫手里全部种类.
    手牌 3n+1 张 (别人打牌/鸣牌判断): 只算当前的向听和进张.
    """
    a = to_34(tehai)
    n = sum(a)
    if n == 0 or n > 14 or n % 3 == 0:
        return None
    seen = visible_counts(tehai, fuuros, snap)
    remaining = [4 - s for s in seen]
    if n % 3 == 1:
        sh, waits = ukeire(a, remaining)
        return {"kind": "wait", "shanten": sh, "waits": waits, "total": sum(c for _, c in waits)}

    now = shanten(a)
    want = None
    if only is not None:
        want = {tile_index(t) for t in only}
        want.discard(-1)
    rows = []
    for i in range(34):
        if not a[i] or (want is not None and i not in want):
            continue
        a[i] -= 1
        sh, waits = ukeire(a, remaining)
        a[i] += 1
        rows.append({"index": i, "tile": index_tile(i), "shanten": sh, "waits": waits,
                     "total": sum(c for _, c in waits), "kinds": len(waits)})
    rows.sort(key=lambda r: (r["shanten"], -r["total"], -r["kinds"], r["index"]))
    best = rows[0] if rows else None
    return {"kind": "discard", "shanten": now, "rows": rows, "partial": want is not None,
            "best_shanten": best["shanten"] if best else None,
            "best_total": best["total"] if best else None}


def find_row(res: dict[str, Any] | None, pai: str | None) -> dict[str, Any] | None:
    if not res or res.get("kind") != "discard" or not pai:
        return None
    i = tile_index(pai)
    return next((r for r in res["rows"] if r["index"] == i), None)


def shanten_text(sh: int | None) -> str:
    if sh is None:
        return "-"
    return "和了" if sh < 0 else "听牌" if sh == 0 else f"{sh} 向听"


def waits_text(waits: list[tuple[int, int]]) -> str:
    """纯文字: 3万*2 6万*4 东*1 (共 7 枚 / 3 种)."""
    if not waits:
        return "无"
    body = " ".join(f"{tile_name(index_tile(i))}*{c}" for i, c in waits)
    return f"{body}（共 {sum(c for _, c in waits)} 枚 / {len(waits)} 种）"
