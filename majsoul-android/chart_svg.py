"""结果图的网页版: 纯 Python 生成 SVG, 不依赖 matplotlib (安卓包里用这个).

内容和 mahjong_rating.draw_chart 一致:
  上图 Rating 折线 + 平均线 + AI 一致率, 下图 每局段位分变化柱 + 段位分走势, 右侧概览文字.
"""

from __future__ import annotations

import html
import math
import pathlib
import statistics
from typing import Any, Sequence

W, H = 760, 300          # 每张图的 SVG 尺寸 (viewBox, 网页里按宽度缩放)
PAD_L, PAD_R, PAD_T, PAD_B = 52, 52, 18, 30
C_RATING, C_AVG, C_ACC, C_UP, C_DOWN, C_CUM, C_FAIL = (
    "#1f77b4", "#d62728", "#2ca02c", "#2ca02c", "#d62728", "#9467bd", "#7f7f7f")


def _esc(s: Any) -> str:
    return html.escape(str(s), quote=True)


def _ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    if hi <= lo:
        return [lo]
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    start = math.ceil(lo / step) * step
    out, v = [], start
    while v <= hi + 1e-9:
        out.append(round(v, 6))
        v += step
    return out


class _Axes:
    def __init__(self, n: int, lo: float, hi: float) -> None:
        self.n, self.lo, self.hi = n, lo, hi
        self.pw = W - PAD_L - PAD_R
        self.ph = H - PAD_T - PAD_B

    def x(self, i: float) -> float:  # i 从 1 开始
        return PAD_L + (i - 0.5) / max(self.n, 1) * self.pw

    def y(self, v: float, lo: float | None = None, hi: float | None = None) -> float:
        lo = self.lo if lo is None else lo
        hi = self.hi if hi is None else hi
        return PAD_T + (1 - (v - lo) / ((hi - lo) or 1)) * self.ph


def _frame(ax: _Axes, yticks: Sequence[float], fmt: str, color: str = "#444",
           right: tuple[Sequence[float], float, float, str, str] | None = None) -> list[str]:
    s = [f'<rect x="{PAD_L}" y="{PAD_T}" width="{ax.pw}" height="{ax.ph}" fill="#fff" stroke="#ccc"/>']
    for t in yticks:
        y = ax.y(t)
        s.append(f'<line x1="{PAD_L}" x2="{W - PAD_R}" y1="{y:.1f}" y2="{y:.1f}" stroke="#eee"/>')
        s.append(f'<text x="{PAD_L - 6}" y="{y + 4:.1f}" text-anchor="end" fill="{color}">'
                 f'{fmt.format(t)}</text>')
    if right:
        ticks, lo, hi, rfmt, rcolor = right
        for t in ticks:
            y = ax.y(t, lo, hi)
            s.append(f'<text x="{W - PAD_R + 6}" y="{y + 4:.1f}" fill="{rcolor}">{rfmt.format(t)}</text>')
    step = max(1, (ax.n + 24) // 25)
    for i in range(1, ax.n + 1, step):
        s.append(f'<text x="{ax.x(i):.1f}" y="{H - PAD_B + 16}" text-anchor="middle" fill="#666">{i}</text>')
    return s


def _poly(pts: list[tuple[float, float]], color: str, width: float = 2, dash: str = "") -> str:
    if len(pts) < 2:
        return ""
    d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    da = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="{width}"{da}/>'


def _legend(items: list[tuple[str, str]], x: float, y: float) -> list[str]:
    s, cx = [], x
    for color, label in items:
        s.append(f'<rect x="{cx}" y="{y - 8}" width="12" height="4" fill="{color}"/>')
        s.append(f'<text x="{cx + 16}" y="{y - 3}" fill="#333">{_esc(label)}</text>')
        cx += 24 + 7.2 * sum(2 if ord(c) > 0x2E80 else 1 for c in label)
    return s


def rating_svg(games: list[Any]) -> str:
    done = sorted(games, key=lambda g: g.start_time)
    n = len(done)
    ratings = [g.rating for g in done]
    ok = [r for r in ratings if r is not None]
    if not ok:
        return ""
    avg = statistics.fmean(ok)
    lo, hi = min(ok), max(ok)
    pad = max(2.0, (hi - lo) * 0.2)
    ax = _Axes(n, lo - pad, hi + pad)
    s = _frame(ax, _ticks(ax.lo, ax.hi), "{:g}", C_RATING,
               right=([0, 25, 50, 75, 100], 0, 100, "{:g}%", C_ACC))
    accs = [(i, g.accordance * 100) for i, g in enumerate(done, 1) if g.accordance is not None]
    s.append(_poly([(ax.x(i), ax.y(a, 0, 100)) for i, a in accs], C_ACC, 1.5))
    for i, a in accs:
        s.append(f'<rect x="{ax.x(i) - 2.5:.1f}" y="{ax.y(a, 0, 100) - 2.5:.1f}" width="5" height="5" fill="{C_ACC}"/>')
    ya = ax.y(avg)
    s.append(f'<line x1="{PAD_L}" x2="{W - PAD_R}" y1="{ya:.1f}" y2="{ya:.1f}" stroke="{C_AVG}" '
             f'stroke-width="1.6" stroke-dasharray="6 4"/>')
    # 折线在没跑出来的局处断开
    seg: list[tuple[float, float]] = []
    for i, r in enumerate(ratings, 1):
        if r is None:
            s.append(_poly(seg, C_RATING))
            seg = []
            yf = ax.y(ax.lo + pad * 0.45)
            s.append(f'<text x="{ax.x(i):.1f}" y="{yf:.1f}" text-anchor="middle" fill="{C_FAIL}" '
                     f'font-size="14" font-weight="bold">×</text>')
            continue
        seg.append((ax.x(i), ax.y(r)))
    s.append(_poly(seg, C_RATING))
    lab = 10 if n <= 24 else 8
    for i, r in enumerate(ratings, 1):
        if r is None:
            continue
        x, y = ax.x(i), ax.y(r)
        s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="{C_RATING}"/>')
        s.append(f'<text x="{x:.1f}" y="{y - 7:.1f}" text-anchor="middle" fill="{C_RATING}" '
                 f'font-size="{lab}">{r:.1f}</text>')
    n_fail = sum(1 for r in ratings if r is None)
    leg = [(C_RATING, "Rating"), (C_AVG, f"平均 {avg:.1f}"), (C_ACC, "AI 一致率 (%)")]
    if n_fail:
        leg.append((C_FAIL, f"跑谱失败 {n_fail} 局"))
    s += _legend(leg, PAD_L + 6, H - 4)
    return _svg(s)


def pt_svg(games: list[Any], level_score: int | None, level_cap: int) -> str:
    from mahjong_rating import cumulative_pt

    done = sorted(games, key=lambda g: g.start_time)
    n = len(done)
    deltas = [g.pt_delta for g in done]
    vals = [d or 0 for d in deltas]
    span = (max(abs(v) for v in vals) or 1) * 1.6
    ax = _Axes(n, -span, span)
    cum = cumulative_pt(done, level_score, level_cap)
    cum_pts = [(i, c) for i, c in enumerate(cum, 1) if c is not None]
    right = None
    clo = chi = 0.0
    if len(cum_pts) >= 2:
        cs = [c for _, c in cum_pts]
        m = max(10.0, (max(cs) - min(cs)) * 0.12)
        clo, chi = min(cs) - m, max(cs) + m
        right = (_ticks(clo, chi, 4), clo, chi, "{:g}", C_CUM)
    s = _frame(ax, _ticks(-span, span, 4), "{:+g}", "#444", right=right)
    y0 = ax.y(0)
    s.append(f'<line x1="{PAD_L}" x2="{W - PAD_R}" y1="{y0:.1f}" y2="{y0:.1f}" stroke="#888"/>')
    bw = ax.pw / max(n, 1) * 0.62
    lab = 10 if n <= 24 else 8
    for i, d in enumerate(deltas, 1):
        v = d or 0
        y = ax.y(v)
        top, h = (y, y0 - y) if v >= 0 else (y0, y - y0)
        col = C_UP if v >= 0 else C_DOWN
        s.append(f'<rect x="{ax.x(i) - bw / 2:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{max(h, 0.5):.1f}" '
                 f'fill="{col}" fill-opacity="0.75"/>')
        if d:
            ty = y - 4 if v > 0 else y + 12
            s.append(f'<text x="{ax.x(i):.1f}" y="{ty:.1f}" text-anchor="middle" fill="{col}" '
                     f'font-size="{lab}">{d:+d}</text>')
    leg = [(C_UP, "每局段位分变化")]
    if right:
        pts = [(ax.x(i), ax.y(c, clo, chi)) for i, c in cum_pts]
        s.append(_poly(pts, C_CUM, 1.8))
        for x, y in pts:
            s.append(f'<rect x="{x - 3:.1f}" y="{y - 3:.1f}" width="6" height="6" fill="{C_CUM}" '
                     f'transform="rotate(45 {x:.1f} {y:.1f})"/>')
        hi_i, hi_c = max(cum_pts, key=lambda p: p[1])
        lo_i, lo_c = min(cum_pts, key=lambda p: p[1])
        last_i, last_c = cum_pts[-1]
        for i, c, text, col, dy in ((hi_i, hi_c, f"最高 {hi_c:.0f}", "#d62728", -10),
                                    (lo_i, lo_c, f"最低 {lo_c:.0f}", "#2ca02c", 18),
                                    (last_i, last_c, f"最近 {last_c:.0f}", "#ff7f0e",
                                     -24 if last_i == hi_i else -10)):
            s.append(f'<text x="{ax.x(i):.1f}" y="{ax.y(c, clo, chi) + dy:.1f}" text-anchor="middle" '
                     f'fill="{col}" font-weight="bold" font-size="10">{text}</text>')
        leg.append((C_CUM, "段位分走势" + ("（升/降段处断开）" if len(cum_pts) < n else "")))
    s += _legend(leg, PAD_L + 6, H - 4)
    return _svg(s)


def _svg(parts: list[str]) -> str:
    body = "\n".join(p for p in parts if p)
    return (f'<svg viewBox="0 0 {W} {H + 8}" xmlns="http://www.w3.org/2000/svg" '
            f'font-family="sans-serif" font-size="11">{body}</svg>')


CSS = """
body{margin:0;font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif;background:#f6f7f9;color:#222}
.wrap{display:flex;flex-wrap:wrap;gap:12px;padding:10px}
.charts{flex:1 1 560px;min-width:0}
.card{background:#fff;border:1px solid #ddd;border-radius:6px;padding:8px;margin-bottom:10px}
.card h3{margin:0 0 4px;font-size:14px}
.card svg{width:100%;height:auto;display:block}
pre{flex:0 1 420px;margin:0;background:#fff;border:1px solid #ddd;border-radius:6px;padding:10px;
    font:12px/1.55 "Consolas","Microsoft YaHei",monospace;overflow-x:auto;white-space:pre}
h2{margin:10px 10px 0;font-size:16px}
@media (max-width:760px){pre{flex-basis:100%}h2{font-size:14px}}
"""


def write(games: list[Any], uid: int, nickname: str, overview: list[str],
          level_score: int | None, level_cap: int, out: pathlib.Path) -> pathlib.Path | None:
    from mahjong_rating import MODE_FULL, MODEL_TAG

    r = rating_svg(games)
    if not r:
        print("  ! 没有成功跑出分数的对局, 跳过绘图")
        return None
    done = sorted(games, key=lambda g: g.start_time)
    modes = ", ".join(sorted({MODE_FULL.get(g.mode_id, str(g.mode_id)) for g in done}))
    title = f"{nickname} ({uid})  Mortal {MODEL_TAG}  最近 {len(done)} 场 [{modes}]"
    doc = (f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
           f'<meta name="viewport" content="width=device-width,initial-scale=1">'
           f'<title>{_esc(title)}</title><style>{CSS}</style></head><body>'
           f'<h2>{_esc(title)}</h2><div class="wrap"><div class="charts">'
           f'<div class="card"><h3>Rating 与 AI 一致率</h3>{r}</div>'
           f'<div class="card"><h3>段位分</h3>{pt_svg(games, level_score, level_cap)}</div>'
           f'</div><pre>{_esc(chr(10).join(overview))}</pre></div></body></html>')
    out.write_text(doc, encoding="utf-8")
    print(f"  [OK] 图 (网页版): {out}")
    return out
