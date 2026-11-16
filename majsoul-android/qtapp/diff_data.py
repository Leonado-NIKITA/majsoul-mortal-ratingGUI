"""差异报告数据层 (Qt 版): 把 mjai 报告整理成纯数据 (dict / list), 不拼 HTML.

复用 diff_report 的 replay / align / entry_metrics / entry_efficiency / action_text,
所以和旧 HTML 报告用的是同一份计算. 区别:
  - 输出每局全部决策点 (含与 Mortal 一致的), 界面一次只看一个;
  - 动作、手牌、副露、牌效都是结构化数据, 由 QML 画;
  - 每局缓存为 diff_<uid>/<uuid>.json; 一致项的牌效在翻到时才算 (ensure_eff).
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

import diff_report as dr

try:
    import efficiency as eff
except ImportError:  # pragma: no cover
    eff = None

CACHE_VER = 2
SEAT_REL = dr.SEAT_REL


# --------------------------------------------------------------------------------------
# 动作 / 副露 / 手牌 的结构化表示
# --------------------------------------------------------------------------------------


def act_view(a: dict[str, Any]) -> dict[str, Any]:
    """{"pre": 文字, "tiles": [牌], "post": 文字}; QML 里依次画 pre, 牌, post."""
    t = a.get("type")
    pre, tiles, post = "", [], ""
    if t == "none":
        pre = "跳过"
    elif t == "dahai":
        pre, tiles = "打", [a["pai"]]
    elif t == "reach":
        pre = "立直"
    elif t == "hora":
        pre = "自摸" if a.get("target") == a.get("actor") else "荣和"
    elif t == "chi":
        tiles, post = list(a.get("consumed") or []), "吃"
    elif t == "pon":
        tiles, post = list(a.get("consumed") or []), "碰"
    elif t in ("kakan", "daiminkan"):
        pre, tiles = "杠", [a["pai"]]
    elif t == "ankan":
        pre, tiles = "杠", [(a.get("consumed") or ["back"])[0]]
    elif t == "ryukyoku":
        pre = "流局"
    else:
        pre = str(t)
    return {"pre": pre, "tiles": tiles, "post": post}


def meld_items(f: dict[str, Any], owner: int) -> list[dict[str, Any]]:
    """副露从左到右的牌: {"t": 牌, "rot": 横置, "add": 加杠叠在上面的牌 ('' 表示没有)}.
    排列规则同 diff_report.render_fuuro."""
    def it(tile: str, rot: bool = False, add: str = "") -> dict[str, Any]:
        return {"t": tile, "rot": rot, "add": add}

    t = f.get("type")
    c = f.get("consumed") or []
    if t in ("pon", "chi", "daiminkan"):
        rel = (f.get("target", owner) + 4 - owner) % 4
        called = it(f["pai"], True)
        others = [it(x) for x in c]
        if rel == 1:
            return others + [called]
        if rel == 2:
            return others[:1] + [called] + others[1:]
        return [called] + others
    if t == "ankan":
        mid = c[1:3] if len(c) >= 3 else c
        return [it("back")] + [it(x) for x in mid] + [it("back")]
    if t == "kakan":
        rel = (f.get("previous_pon_target", owner) + 4 - owner) % 4
        added = it(f["pai"], True, f.get("previous_pon_pai", f["pai"]))
        others = [it(x) for x in c]
        if rel == 1:
            return others + [added]
        if rel == 2:
            return others[:1] + [added] + others[1:]
        return [added] + others
    return []


def tehai_view(e: dict[str, Any], me: int) -> dict[str, Any]:
    """手牌行: tiles = [{pai, before, after}], fuuros = [[meld_items]]. 规则同 render_tehai_state."""
    st = e.get("state") or {}
    tehai = st.get("tehai") or []
    out = []
    n = len(tehai)
    for i, t in enumerate(tehai):
        if i < n - 1 or e.get("at_self_chi_pon"):
            out.append({"pai": t, "before": "", "after": ""})
        elif e.get("at_self_riichi"):
            out.append({"pai": t, "before": "摸 ", "after": " 立直"})
        elif e.get("last_actor") == me:
            out.append({"pai": t, "before": "摸 ", "after": ""})
        else:
            out.append({"pai": t, "before": "", "after": ""})
            who = SEAT_REL[(e.get("last_actor", me) + 4 - me) % 4]
            verb = "加杠" if e.get("at_opponent_kakan") else "打出"
            out.append({"pai": e.get("tile", "back"), "before": f"{who}{verb} ", "after": ""})
    fuuros = [meld_items(f, me) for f in reversed(st.get("fuuros") or [])]
    return {"tiles": out, "fuuros": fuuros}


# --------------------------------------------------------------------------------------
# 牌效
# --------------------------------------------------------------------------------------


def _waits(waits: list[tuple[int, int]]) -> list[dict[str, Any]]:
    return [{"tile": eff.index_tile(i), "name": eff.tile_name(eff.index_tile(i)), "n": c}
            for i, c in waits]


def eff_view(res: dict[str, Any] | None, e: dict[str, Any]) -> dict[str, Any] | None:
    if not res or eff is None:
        return None
    now = res["shanten"]
    if res["kind"] == "wait":
        return {"kind": "wait", "shText": eff.shanten_text(now), "total": res["total"],
                "kinds": len(res["waits"]), "waits": _waits(res["waits"]), "rows": [], "note": ""}
    act, exp = e.get("actual") or {}, e.get("expected") or {}
    ia = eff.tile_index(act["pai"]) if act.get("type") == "dahai" else -1
    ie = eff.tile_index(exp["pai"]) if exp.get("type") == "dahai" else -1
    rows = []
    for r in res["rows"]:
        best = r["shanten"] == res["best_shanten"] and r["total"] == res["best_total"]
        marks = []
        if r["index"] == ia:
            marks.append("自己")
        if r["index"] == ie:
            marks.append("Mortal")
        if best:
            marks.append("进张最多")
        rows.append({"tile": r["tile"], "shText": eff.shanten_text(r["shanten"]),
                     "back": r["shanten"] > now, "total": r["total"], "kinds": r["kinds"],
                     "waits": _waits(r["waits"]), "marks": marks, "best": best,
                     "isActual": r["index"] == ia, "isExpected": r["index"] == ie})
    note = f"只列 Mortal 前 {dr.EFF_TOP} 优先和自己打的牌" if res.get("partial") else ""
    return {"kind": "discard", "shText": eff.shanten_text(now), "total": 0, "kinds": 0,
            "waits": [], "rows": rows, "note": note}


def _briefs(res: dict[str, Any] | None, e: dict[str, Any]) -> tuple[str, str]:
    if eff is None or not res:
        return "", ""
    return dr.eff_brief(res, e["actual"]), dr.eff_brief(res, e["expected"])


def ensure_eff(entry: dict[str, Any]) -> bool:
    """一致项的牌效按需计算, 结果写进 entry. 返回是否有变化."""
    if not entry.get("effPending"):
        return False
    raw = entry.pop("raw")
    pt = {"snap": entry["board"]} if entry.get("board") else None
    res = dr.entry_efficiency(raw, pt)
    entry["eff"] = eff_view(res, raw)
    entry["briefA"], entry["briefE"] = _briefs(res, raw)
    entry["effPending"] = False
    return True


# --------------------------------------------------------------------------------------
# 单局
# --------------------------------------------------------------------------------------


def _board(pt: dict[str, Any] | None) -> dict[str, Any] | None:
    if pt is None:
        return None
    snap = dict(pt["snap"])
    snap["meldv"] = [[meld_items(m, seat) for m in snap["melds"][seat]] for seat in range(4)]
    ld = snap.get("last_discard")
    snap["last_discard"] = list(ld) if ld else None
    return snap


def build_game_data(report: dict[str, Any], g: dict[str, Any], eager_equal: bool = False) -> dict[str, Any]:
    review = report.get("review") or {}
    kyokus = review.get("kyokus") or []
    me = int(report.get("player_id", g.get("seat", 0)) or 0)
    log = report.get("mjai_log") if isinstance(report.get("mjai_log"), list) else []
    names: list[str] = []
    for ev in log[:3]:
        if ev.get("type") == "start_game":
            names = list(ev.get("names") or [])
    points_by_kyoku = dr.replay(log, me) if log else []

    entries: list[dict[str, Any]] = []
    ks: list[dict[str, Any]] = []
    n_diff = n_aligned = 0
    for ki, k in enumerate(kyokus):
        raw_entries = k.get("entries") or []
        pts = (dr.align(raw_entries, points_by_kyoku[ki])
               if ki < len(points_by_kyoku) else [None] * len(raw_entries))
        title = dr.kyoku_title(k)
        first, nd = len(entries), 0
        for ei, (e, pt) in enumerate(zip(raw_entries, pts)):
            is_diff = not e.get("is_equal", True)
            m = dr.entry_metrics(e)
            info = []
            sh = e.get("shanten")
            if isinstance(sh, int):
                info.append("听牌" if sh == 0 else f"{sh} 向听")
            if e.get("at_furiten"):
                info.append("振听")
            details = e.get("details") or []
            if m["actual_idx"] >= 0:
                info.append(f"#{m['actual_idx'] + 1}/{len(details)}")
            if m["loss"] is not None and is_diff:
                info.append(f"Q 损失 {m['loss']:.3f}")
            cands = []
            for i, d in enumerate(details):
                cands.append({"act": act_view(d["action"]), "q": d["q_value"], "prob": d["prob"],
                              "cls": "actual" if i == m["actual_idx"]
                              else "expected" if i == m["expected_idx"] else ""})
            if is_diff:
                n_diff += 1
                n_aligned += pt is not None
                nd += 1
            ent: dict[str, Any] = {
                "idx": len(entries), "ki": ki, "ei": ei, "kyoku": title, "isDiff": is_diff,
                "junme": e.get("junme"), "tilesLeft": e.get("tiles_left"),
                "info": "　".join(info), "loss": m["loss"], "pA": m["p_actual"], "pE": m["p_expected"],
                "actual": act_view(e["actual"]), "expected": act_view(e["expected"]),
                "actualText": dr.action_text(e["actual"]), "expectedText": dr.action_text(e["expected"]),
                "tehai": tehai_view(e, me), "cands": cands, "board": _board(pt),
                "aligned": pt is not None,
                "eff": None, "effPending": False, "briefA": "", "briefE": "",
            }
            if is_diff or eager_equal:
                res = dr.entry_efficiency(e, pt)
                ent["eff"] = eff_view(res, e)
                ent["briefA"], ent["briefE"] = _briefs(res, e)
            else:
                ent["effPending"] = eff is not None
                ent["raw"] = {"state": e.get("state"), "actual": e.get("actual"),
                              "expected": e.get("expected"), "details": details}
            entries.append(ent)
        ks.append({"title": title, "end": dr.end_status_text(k, me), "first": first,
                   "count": len(entries) - first, "diffs": nd})

    total, matches = review.get("total_reviewed"), review.get("total_matches")
    rating = review.get("rating")
    links = []
    if g.get("record_url"):
        links.append({"text": "雀魂牌谱", "url": g["record_url"]})
    if g.get("report_task"):
        links.append({"text": "mjai 原报告",
                      "url": f"https://mjai.ekyu.moe/report/{g['report_task']}.html"})
    warn = ""
    if not log:
        warn = "报告里没有 mjai_log，无法复原牌桌，只显示手牌与候选。"
    elif n_aligned < n_diff:
        warn = f"{n_diff - n_aligned} 处差异没能对齐到牌桌事件。"
    return {
        "ver": CACHE_VER, "uuid": g.get("uuid", ""), "me": me, "names": names,
        "header": {
            "when": dr.game_when(g), "mode": dr.mode_name(g.get("mode_id")),
            "rank": g.get("rank"), "score": g.get("score"),
            "rating": None if rating is None else round(rating * 100, 1),
            "matches": matches, "total": total,
            "engine": f"{report.get('engine', '')} {review.get('model_tag', '')}".strip(),
            "seatNames": [f"{SEAT_REL[(i + 4 - me) % 4]}: {n}" for i, n in enumerate(names)],
            "links": links, "warn": warn, "diffs": n_diff, "aligned": n_aligned,
        },
        "kyokus": ks, "entries": entries,
    }


def _cache_path(out_dir: pathlib.Path | str, uid: int, uuid: str) -> pathlib.Path:
    return pathlib.Path(out_dir) / f"diff_{uid}" / f"{uuid}.json"


def load_game(out_dir: pathlib.Path | str, st: Any, g: dict[str, Any]) -> dict[str, Any] | None:
    """读缓存; 没有或报告文件更新过就重新生成并写缓存. 没有本地报告返回 None."""
    src = dr.find_report(pathlib.Path(st.reports_dir), g)
    if src is None:
        return None
    cache = _cache_path(out_dir, st.uid, g["uuid"])
    mtime = src.stat().st_mtime
    if cache.exists():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if data.get("ver") == CACHE_VER and data.get("srcMtime") == mtime:
                return data
        except (OSError, ValueError):
            pass
    report = json.loads(src.read_text(encoding="utf-8"))
    data = build_game_data(report, g)
    data["srcMtime"] = mtime
    save_game(out_dir, st.uid, data)
    return data


def save_game(out_dir: pathlib.Path | str, uid: int, data: dict[str, Any]) -> None:
    cache = _cache_path(out_dir, uid, data["uuid"])
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(cache)


# --------------------------------------------------------------------------------------
# 汇总 (多局)
# --------------------------------------------------------------------------------------


def summarize(out_dir: pathlib.Path | str, st: Any, uuids: list[str],
              progress=None) -> dict[str, Any]:
    """选中的对局 -> {"games": [...], "top": [...], "diffs": n}. 每局的明细由 load_game 缓存."""
    lib = {g["uuid"]: g for g in st.library()}
    games = sorted((lib[u] for u in uuids if u in lib),
                   key=lambda g: g.get("start_time") or 0, reverse=True)
    rows, top = [], []
    n_diffs = 0
    for i, g in enumerate(games):
        if progress:
            progress(i, len(games))
        row: dict[str, Any] = {"uuid": g["uuid"], "when": dr.game_when(g),
                               "mode": dr.mode_name(g.get("mode_id")), "rank": g.get("rank"),
                               "score": g.get("score"), "ok": False, "note": ""}
        try:
            d = load_game(out_dir, st, g)
        except Exception as exc:  # noqa: BLE001  某一局坏了不影响其它局
            row["note"] = f"生成失败: {exc}"
            rows.append(row)
            continue
        if d is None:
            row["note"] = g.get("error") or ("没存原始报告" if g.get("rating") is not None else "未跑谱")
            rows.append(row)
            continue
        h = d["header"]
        row.update(ok=True, rating=h["rating"], matches=h["matches"], total=h["total"],
                   diffs=h["diffs"], note="" if d["entries"] is not None and h["warn"] == "" else h["warn"])
        n_diffs += h["diffs"]
        for e in d["entries"]:
            if e["isDiff"] and e["loss"] is not None:
                top.append({"uuid": g["uuid"], "idx": e["idx"], "when": h["when"], "kyoku": e["kyoku"],
                            "junme": e["junme"], "actual": e["actualText"], "expected": e["expectedText"],
                            "loss": e["loss"], "briefA": e["briefA"], "briefE": e["briefE"]})
        rows.append(row)
    top.sort(key=lambda x: -x["loss"])
    return {"games": rows, "top": top[:30], "diffs": n_diffs}

