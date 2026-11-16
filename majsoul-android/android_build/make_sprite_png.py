"""把精灵图 SVG 栅格化成 PNG (一次性生成, 结果放进 assets/). 用法: python make_sprite_png.py <输出目录> [单元宽度]"""
import pathlib
import sys

from playwright.sync_api import sync_playwright

root = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
import diff_report as dr  # noqa: E402

out = pathlib.Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
cw = int(sys.argv[2]) if len(sys.argv) > 2 else 64  # 竖放牌单元宽, 高 = cw*446/320
ch = round(cw * 446 / 320)
n, r = len(dr.SPRITE_TILES), len(dr.SPRITE_ROWS)
up, side = dr.sprite_sheets((dr.assets_dir() / "pai.svg").read_text(encoding="utf-8"))
with sync_playwright() as p:
    b = p.chromium.launch()
    for name, svg, (w, h) in (("pai-up", up, (cw, ch)), ("pai-side", side, (ch, cw))):
        W, H = n * w, r * h
        pg = b.new_page(viewport={"width": W, "height": H})
        pg.set_content(f'<body style="margin:0;background:transparent">'
                       f'<div style="width:{W}px;height:{H}px">{svg.replace("<svg ", f"<svg width={chr(34)}{W}{chr(34)} height={chr(34)}{H}{chr(34)} ", 1)}</div></body>')
        pg.wait_for_timeout(300)
        pg.screenshot(path=str(out / f"{name}.png"), omit_background=True, clip={"x": 0, "y": 0, "width": W, "height": H})
        print(name, W, H)
    b.close()
for f in sorted(out.glob("*.png")):
    print(f.name, f.stat().st_size // 1024, "KB")
