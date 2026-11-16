"""
程序内 WebView 网页后端 (安卓用; 桌面也能跑, 便于调试).

跟 mahjong_rating.LazyBrowser 提供同样的接口 (fetch_records / submit / page_get_json / close ...),
区别是网页显示在界面里的 QML WebView 上:
  - 牌谱屋: 打开首页, 注入 mobile/ama_hook.js, 再用前端路由跳到玩家页, 收集页面自己请求到的 player_records.
  - mjai 提交: 打开提交页自动填表, Turnstile 自动过不了时把网页页面切到前台让用户点一下.

线程: 跑谱流程在工作线程的 asyncio 循环里, WebView 在 Qt 主线程.
  - Python -> QML: 发 Signal (跨线程自动排队到主线程).
  - QML -> Python: 调 WebBridge 的 Slot (主线程), 再用 call_soon_threadsafe 交还给工作线程的循环.
安卓上 runJavaScript 的回调跑在安卓 UI 线程, 在里面执行 QML JS 会段错误;
所以 QML 侧不用回调, 脚本把结果写进 document.title, 由 onTitleChanged 读回 (见 qml/WebPage.qml).
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import time
from typing import Any

from PySide6.QtCore import QObject, Property, Signal, Slot

import mahjong_rating as mr
import store

HOOK_JS = (pathlib.Path(__file__).resolve().parent / "mobile" / "ama_hook.js")
CHUNK = 3000  # document.title 一次传回的字符数 (桌面 WebView2 的 title 会被截到 4096)


class WebBridge(QObject):
    """QML WebView 和 Python 之间的桥. 在主线程创建, 暴露给 QML 叫 web."""

    jsRequested = Signal(int, str)   # (序号, 完整脚本) -> QML 执行
    navRequested = Signal(str)       # 打开网址
    attention = Signal(str)          # 需要用户看网页 (人机验证要手动点), 界面切到网页页
    urlChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._seq = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._url = ""
        self._loaded = 0  # 每加载完一次页面 +1
        self._load_waiters: list[asyncio.Future] = []
        # 结果都经同一个 document.title 传回, 连着改几次 title 中间的可能收不到; 一次只跑一段脚本
        self._js_lock: asyncio.Lock | None = None
        self._big_lock: asyncio.Lock | None = None  # window.__mjrBuf 是共用的

    # ---------------- QML 调这些 (主线程) ----------------

    @Property(str, notify=urlChanged)
    def url(self) -> str:
        return self._url

    @Slot(int, str)
    def jsDone(self, seq: int, result: str) -> None:
        self._call(self._resolve_js, seq, result)

    @Slot(str, bool)
    def loaded(self, url: str, ok: bool) -> None:
        """WebView onLoadingChanged: 加载完成 (ok) 或失败."""
        self._url = url
        self.urlChanged.emit()
        self._call(self._resolve_load, url, ok)

    @Slot(str)
    def urlSeen(self, url: str) -> None:
        """WebView url 变了 (含前端路由跳转)."""
        if url != self._url:
            self._url = url
            self.urlChanged.emit()

    def _call(self, fn, *a) -> None:
        loop = self._loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(fn, *a)

    # ---------------- 工作线程的循环里执行 ----------------

    def _resolve_js(self, seq: int, result: str) -> None:
        fut = self._pending.pop(seq, None)
        if fut is not None and not fut.done():
            fut.set_result(result)

    def _resolve_load(self, url: str, ok: bool) -> None:
        self._loaded += 1
        waiters, self._load_waiters = self._load_waiters, []
        for f in waiters:
            if not f.done():
                f.set_result((url, ok))

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        # 锁绑定在当前循环上, 每次运行 (新的 asyncio.run) 重建
        self._js_lock = asyncio.Lock() if loop is not None else None
        self._big_lock = asyncio.Lock() if loop is not None else None

    async def js(self, body: str, timeout: float = 20) -> str:
        """执行一段 JS 函数体 (要 return 结果), 返回字符串. 出错返回 'ERR ...'."""
        assert self._js_lock is not None
        async with self._js_lock:
            self._seq += 1
            seq = self._seq
            fut = asyncio.get_running_loop().create_future()
            self._pending[seq] = fut
            script = ("(function(){var r; try { r = (function(){" + body + "\n})(); }"
                      " catch (e) { r = 'ERR ' + e; }"
                      f" document.title = 'MJR{seq}:' + String(r); }})()")
            self.jsRequested.emit(seq, script)
            try:
                return await asyncio.wait_for(fut, timeout)
            finally:
                self._pending.pop(seq, None)

    async def js_big(self, expr: str, timeout: float = 30) -> str:
        """取一个可能很长的字符串结果 (例如几百局对局记录的 JSON), 分段经 title 传回."""
        assert self._big_lock is not None
        async with self._big_lock:
            n = await self.js(f"window.__mjrBuf = String({expr}); return window.__mjrBuf.length;",
                              timeout)
            try:
                total = int(n)
            except ValueError:
                raise RuntimeError(f"取数据失败: {n[:120]}") from None
            parts = []
            for i in range(0, total, CHUNK):
                parts.append(await self.js(f"return window.__mjrBuf.substr({i}, {CHUNK});", timeout))
            await self.js("window.__mjrBuf = null; return 1;")
            return "".join(parts)

    async def goto(self, url: str, timeout: float) -> str:
        """打开网址, 等到加载完成, 返回最终网址."""
        fut = asyncio.get_running_loop().create_future()
        self._load_waiters.append(fut)
        self.navRequested.emit(url)
        got, ok = await asyncio.wait_for(fut, timeout)
        if not ok:
            raise RuntimeError(f"网页加载失败: {got}")
        return got

    async def wait_load(self, timeout: float) -> tuple[str, bool]:
        fut = asyncio.get_running_loop().create_future()
        self._load_waiters.append(fut)
        return await asyncio.wait_for(fut, timeout)


class WebViewRecords:
    """牌谱屋玩家页 (WebView 版). 接口同 mahjong_rating.PlaywrightRecords."""

    # 路由跳转后前端会马上改 document.title, 盖掉 js() 靠 title 回传的结果 (超时, 异常信息为空);
    # 所以延后跳转, 先让本次结果传回去.
    NAV = ("setTimeout(function () { history.pushState({}, '', %s);"
           " window.dispatchEvent(new PopStateEvent('popstate', {state: {}})); }, 300); return 'nav';")

    def __init__(self, web: WebBridge) -> None:
        self.web = web
        self.hook = HOOK_JS.read_text(encoding="utf-8")

    async def _ensure_hook(self) -> None:
        r = await self.web.js("return window.__mjr ? 'ok' : 'none';")
        if r == "ok" and "amae-koromo" in self.web.url:
            return
        await self.web.goto(mr.AMA_CHART + "/", mr.TIMEOUTS["page_load"])
        await asyncio.sleep(2)
        # 脚本开头是 // 注释: 直接拼 "return " 会被自动分号变成 return; 所以包一层括号
        r = await self.web.js("return (\n" + self.hook.strip().rstrip(";") + "\n);")
        if r not in ("installed", "already"):
            raise RuntimeError(f"牌谱屋页面注入失败: {r[:120]}")

    async def open(self, uid: int, mid: int) -> None:
        await self._ensure_hook()
        await self.web.js("window.__mjr.clear(); return 1;")
        # 先回首页再进玩家页, 保证前端路由重新请求数据
        await self.web.js(self.NAV % json.dumps("/"))
        await asyncio.sleep(1.0)
        await self.web.js(self.NAV % json.dumps(f"/player/{uid}/{mid}"))
        await asyncio.sleep(1.0)

    async def _all(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(await self.web.js_big("window.__mjr ? window.__mjr.take() : '[]'"))
        except ValueError:
            return []
        return [r for r in data if isinstance(r, dict) and r.get("uuid")]

    async def stat(self, mid: int) -> tuple[int, int]:
        r = await self.web.js(
            "if (!window.__mjr) return '0,0'; var a = JSON.parse(window.__mjr.take()), n = 0, lo = 0;"
            f" a.forEach(function (x) {{ if (x.modeId === {int(mid)}) {{ n++;"
            " if (!lo || x.startTime < lo) lo = x.startTime; } });"
            " return n + ',' + lo;")
        try:
            n, lo = r.split(",")
            return int(n), int(lo)
        except ValueError:
            return 0, 0

    async def records(self, mid: int) -> list[dict[str, Any]]:
        return [r for r in await self._all() if r.get("modeId") == mid]

    async def scroll(self) -> None:
        await self.web.js(mr.SCROLL_JS + " return 1;")


FILL_JS = """
var f = document.forms.reviewForm; if (!f) return 'noform';
var i = document.querySelector('input[name=log-url]');
i.value = %(url)s; i.dispatchEvent(new Event('input', {bubbles: true}));
function sel(n, v) {
  var s = document.querySelector('select[name=' + n + ']'); if (!s) return n + '?';
  s.value = v; s.dispatchEvent(new Event('change', {bubbles: true}));
  return s.value === v ? 'ok' : n + '=' + s.value;
}
var r = [sel('engine', 'mortal'), sel('mortal-model-tag', %(model)s),
         sel('player-id', %(seat)s)].filter(function (x) { return x !== 'ok'; });
return r.length ? r.join(',') : 'ok';
"""
BTN_JS = ("var b = document.querySelector('form[name=reviewForm] button[type=submit]');"
          " return b ? (b.disabled ? 'disabled' : 'enabled') : 'nobtn';")
CLICK_JS = ("document.querySelector('form[name=reviewForm] button[type=submit]').click(); return 1;")


class WebViewSession:
    """程序内 WebView 的网页后端, 给 mahjong_rating.run() 用 (args.web)."""

    can_browse = True
    max_concurrency = 1  # 只有一个 WebView, 一次提交一局

    def __init__(self, web: WebBridge) -> None:
        self.web = web
        self.http_blocked = False
        self.http_sem = asyncio.Semaphore(2)
        self._get_seq = 0

    async def fetch_records(self, st: store.PlayerStore, mode_ids: list[int],
                            want: int) -> set[int]:
        return await mr.fetch_records(WebViewRecords(self.web), st, mode_ids, want)

    async def page_get_json(self, url: str) -> Any:
        if "amae-koromo" not in self.web.url:
            await self.web.goto(mr.AMA_CHART + "/", mr.TIMEOUTS["page_load"])
        self_url = json.dumps(url)
        # 异步 fetch 的结果先放进 window 变量, 再轮询取回; 会有几个请求同时进行, 每个用自己的键
        self._get_seq += 1
        key = json.dumps(f"g{self._get_seq}")
        slot = f"window.__mjrGet[{key}]"
        await self.web.js(
            "window.__mjrGet = window.__mjrGet || {}; " + slot + " = null;"
            " fetch(" + self_url + ", {cache: 'no-store'})"
            ".then(function (r) { return r.ok ? r.text() : 'null'; })"
            ".then(function (t) { " + slot + " = t; }, function () { " + slot + " = 'null'; });"
            " return 1;")
        try:
            deadline = time.time() + mr.TIMEOUTS["http"]
            while time.time() < deadline:
                await asyncio.sleep(0.5)
                if await self.web.js(f"return {slot} == null ? '0' : '1';") == "1":
                    try:
                        return json.loads(await self.web.js_big(slot))
                    except ValueError:
                        return None
            return None
        finally:
            try:
                await self.web.js(f"if (window.__mjrGet) delete {slot}; return 1;")
            except Exception:  # noqa: BLE001
                pass

    async def submit(self, game: "mr.Game") -> str:
        web = self.web
        await web.goto(mr.MJAI_FORM, mr.TIMEOUTS["page_load"])
        fill = FILL_JS % {
            "url": json.dumps(game.record_url), "model": json.dumps(mr.MODEL_TAG),
            "seat": json.dumps(str(game.seat))}
        # 加载完成的回调可能早于表单渲染 (noform), 或页面脚本随后又把输入框清空; 所以重试, 提交前再核对
        r = ""
        for _ in range(20):
            r = await web.js(fill)
            if r == "ok":
                break
            await asyncio.sleep(0.5)
        if r != "ok":
            raise RuntimeError(f"填表失败: {r[:120]}")
        url_check = ("var i = document.querySelector('input[name=log-url]');"
                     " return i && i.value === " + json.dumps(game.record_url) + " ? 'ok' : 'bad';")

        form_timeout = mr.TIMEOUTS["captcha"]
        start = time.time()
        asked = False
        while (b := await web.js(BTN_JS)) != "enabled":
            if b == "nobtn":
                raise RuntimeError("提交页上找不到提交按钮")
            waited = time.time() - start
            if waited > form_timeout:
                raise TimeoutError(f"人机验证未通过 ({int(form_timeout)}s)")
            if waited > 12 and not asked:  # 自动过不了: 请用户在网页上点一下「确认您是真人」
                asked = True
                web.attention.emit(f"请在网页上完成人机验证 ({game.when} {game.rank}位)")
            if await web.js(url_check) != "ok":  # 链接被清掉了, 补填
                await web.js(fill)
            await asyncio.sleep(1)

        if await web.js(url_check) != "ok":
            await web.js(fill)
        load = asyncio.ensure_future(web.wait_load(mr.TIMEOUTS["submit_nav"]))
        await web.js(CLICK_JS)
        try:
            url, _ = await load
        except asyncio.TimeoutError:
            url = web.url
        if "task=" not in url:
            # 有时页面先跳到中间页, 再等一下
            for _ in range(10):
                await asyncio.sleep(1)
                url = web.url
                if "task=" in url:
                    break
        if "task=" not in url:
            msg = await web.js("return (document.body ? document.body.innerText : '').slice(0, 300);")
            msg = " ".join(x.strip() for x in msg.splitlines() if x.strip())[:200]
            raise RuntimeError(f"提交未成功 (返回 {url}) {msg}")
        return url.split("task=")[-1].split("&")[0]

    def open_pages(self) -> int:
        return 1

    async def close(self) -> None:
        try:
            await self.web.goto("about:blank", 10)
        except Exception:  # noqa: BLE001
            pass
