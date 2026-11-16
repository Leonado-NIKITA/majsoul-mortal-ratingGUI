"""玩家数据的本地存储: 放在程序根目录 players/ 下, 跨次运行复用, 不重复抓取.

目录结构:
    players/
      index.json              昵称 -> UID, 用昵称查人时不用再去牌谱屋搜索
      <UID>/
        player.json           玩家信息: 昵称(含曾用名)、段位、战绩概览缓存、上次运行的对局列表
        games.json            records: 牌谱屋对局记录 (按 uuid, 只增不减)
                              results: 跑谱结果 (rating / AI 一致率 / mjai 任务号, 按 uuid)
                              chains:  每个场次"从最新一局往前连续已知"的时间区间, 用来判断还要不要往前翻
        reports/*.json        mjai 原始报告 (差异报告用)
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import sys
import time
from typing import Any

OVERVIEW_TTL = 30 * 60  # 战绩概览缓存多久 (秒); 期间没有新对局就不再请求牌谱屋


IS_ANDROID = hasattr(sys, "getandroidapilevel") or "ANDROID_ARGUMENT" in os.environ


def app_dir() -> pathlib.Path:
    """
    数据根目录 (players/、rating_out/ 放在这下面):
      - 安卓: 应用私有目录 (卸载时一起清掉, 不需要存储权限)
      - 打包后的 exe: exe 所在目录
      - 开发时: 脚本所在目录
    """
    if IS_ANDROID:
        return android_data_dir()
    if getattr(sys, "frozen", False):
        return pathlib.Path(sys.executable).resolve().parent
    return pathlib.Path(__file__).resolve().parent


def android_data_dir() -> pathlib.Path:
    """安卓应用私有目录. 优先用 Qt 给的 AppDataLocation, 取不到再用 p4a 设置的环境变量."""
    try:
        from PySide6.QtCore import QStandardPaths
        loc = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        if loc:
            p = pathlib.Path(loc)
            p.mkdir(parents=True, exist_ok=True)
            return p
    except Exception:  # noqa: BLE001
        pass
    for key in ("ANDROID_PRIVATE", "ANDROID_APP_PATH", "HOME"):
        if os.environ.get(key):
            p = pathlib.Path(os.environ[key]) / "data"
            p.mkdir(parents=True, exist_ok=True)
            return p
    return pathlib.Path(__file__).resolve().parent


def resource_dir() -> pathlib.Path:
    """随程序一起发布的只读资源 (assets/ 等) 所在目录."""
    base = getattr(sys, "_MEIPASS", None)
    return pathlib.Path(base) if base else pathlib.Path(__file__).resolve().parent


def default_root() -> pathlib.Path:
    return app_dir() / "players"


def _read(path: pathlib.Path, default: Any, quarantine: bool = True) -> Any:
    """读 JSON. 文件坏了就改名成 .bad-<时间> 留底, 免得被下次写入覆盖丢数据."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as exc:
        if quarantine and path.exists():
            bad = path.with_name(f"{path.name}.bad-{int(time.time())}")
            try:
                path.rename(bad)
                print(f"      ! {path.name} 读不了 ({exc}), 已改名为 {bad.name} 留底")
            except OSError:
                pass
        return default


def _write(path: pathlib.Path, data: Any, indent: int | None = None) -> None:
    """先写临时文件再替换, 中途被 Ctrl+C 打断也不会留下半个文件."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")
    os.replace(tmp, path)


# --------------------------------------------------------------------------------------
# 不需要具体玩家的查询
# --------------------------------------------------------------------------------------


def settings_path() -> pathlib.Path:
    # 放 players/ 里: 装到 Program Files 时只有这个目录普通用户可写, 卸载时也跟玩家数据一起处理
    return default_root() / "settings.json"


def load_settings() -> dict[str, Any]:
    """GUI 上次的输入 (玩家、局数、场次...) 和输入过的玩家历史."""
    data = _read(settings_path(), {})
    return data if isinstance(data, dict) else {}


def save_settings(data: dict[str, Any]) -> None:
    try:
        _write(settings_path(), data, indent=1)
    except OSError:
        pass  # 目录没写权限时就不记了, 不影响跑谱


def lookup_nickname(root: pathlib.Path, name: str) -> int | None:
    uid = (_read(root / "index.json", {}).get("nicknames") or {}).get(name)
    return int(uid) if uid else None


def cached_nickname(root: pathlib.Path, uid: int) -> str:
    return (_read(root / str(uid) / "player.json", {}) or {}).get("nickname") or ""


def latest_uid(root: pathlib.Path) -> int | None:
    """最近一次更新过的玩家."""
    hits = [p for p in root.glob("*/player.json") if p.parent.name.isdigit()] \
        if root.exists() else []
    if not hits:
        return None
    return int(max(hits, key=lambda p: p.stat().st_mtime).parent.name)


def resolve_local(root: pathlib.Path, ident: str) -> int | None:
    """UID / 昵称 / 空 -> 本地已有的 UID (空 = 最近一次跑的玩家)."""
    ident = (ident or "").strip()
    if ident.isdigit():
        return int(ident)
    if ident:
        return lookup_nickname(root, ident)
    return latest_uid(root)


# --------------------------------------------------------------------------------------
# 单个玩家
# --------------------------------------------------------------------------------------


class PlayerStore:
    def __init__(self, root: pathlib.Path | str, uid: int) -> None:
        self.root = pathlib.Path(root)
        self.uid = int(uid)
        self.dir = self.root / str(self.uid)
        self.reports_dir = self.dir / "reports"
        self.profile: dict[str, Any] = _read(self.dir / "player.json", {}) or {}
        g = _read(self.dir / "games.json", {}) or {}
        self.records: dict[str, dict[str, Any]] = g.get("records") or {}
        self.results: dict[str, dict[str, Any]] = g.get("results") or {}
        self.chains: dict[str, list[int]] = g.get("chains") or {}

    # ---------------- 保存 ----------------
    def save_profile(self) -> None:
        self.profile["uid"] = self.uid
        self.profile["updated_at"] = int(time.time())
        _write(self.dir / "player.json", self.profile, indent=1)

    def save_games(self) -> None:
        _write(self.dir / "games.json",
               {"records": self.records, "results": self.results, "chains": self.chains})

    # ---------------- 玩家信息 ----------------
    def set_nickname(self, name: str) -> None:
        if not name or name == str(self.uid):
            return
        hist = self.profile.setdefault("nickname_history", [])
        if name not in hist:
            hist.append(name)
        self.profile["nickname"] = name
        idx = _read(self.root / "index.json", {}) or {}
        nicks = idx.setdefault("nicknames", {})
        if nicks.get(name) != self.uid:
            nicks[name] = self.uid
            _write(self.root / "index.json", idx, indent=1)

    def cached_overview(self, key: str) -> dict[str, Any] | None:
        ov = self.profile.get("overview") or {}
        if ov.get("key") != key or time.time() - ov.get("fetched_at", 0) > OVERVIEW_TTL:
            return None
        data = dict(ov.get("data") or {})
        data["now"] = int(time.time() * 1000)  # "最近对战 X 前" 按现在算
        return data

    def put_overview(self, key: str, data: dict[str, Any]) -> None:
        self.profile["overview"] = {"key": key, "fetched_at": int(time.time()), "data": data}
        stats = data.get("all") or {}
        for k in ("level", "max_level", "count"):
            if stats.get(k) is not None:
                self.profile[k] = stats[k]

    # ---------------- 牌谱屋对局记录 ----------------
    def chain(self, mode_id: int) -> dict[str, Any] | None:
        """{"lo", "hi"}: 该场次 [lo, hi] 区间内的对局本地都有 (startTime, 秒)."""
        ch = self.chains.get(str(mode_id))
        return ch if isinstance(ch, dict) and "lo" in ch and "hi" in ch else None

    def chain_records(self, mode_id: int) -> list[dict[str, Any]]:
        """该场次从(上次同步时的)最新一局往前连续已知的记录, 新的在前."""
        ch = self.chain(mode_id)
        if not ch:
            return []
        rs = [r for r in self.records.values()
              if r.get("modeId") == mode_id and ch["lo"] <= r.get("startTime", 0) <= ch["hi"]]
        return sorted(rs, key=lambda r: r.get("startTime", 0), reverse=True)

    def chain_full(self, mode_id: int) -> bool:
        """本地连续记录已经覆盖了牌谱屋统计的全部对局 (再往前没有了)."""
        cnt = self.synced_count(str(mode_id))
        return isinstance(cnt, int) and len(self.chain_records(mode_id)) >= cnt

    def chain_enough(self, mode_id: int, want: int) -> bool:
        return bool(self.chain(mode_id)) and (
            len(self.chain_records(mode_id)) >= want or self.chain_full(mode_id))

    def merge_records(self, mode_id: int, fresh: list[dict[str, Any]]) -> bool:
        """
        fresh: 本次从最新一局往前连续拿到的记录.
        跟已知区间接上了就合并成一段 (返回 True); 没接上(中间隔了太多新对局)就以这次的为准.
        """
        if not fresh:
            return False
        for r in fresh:
            self.records[r["uuid"]] = r
        lo = min(r["startTime"] for r in fresh)
        hi = max(r["startTime"] for r in fresh)
        ch = self.chain(mode_id)
        joined = bool(ch) and lo <= ch["hi"]
        if joined:
            lo = min(lo, ch["lo"])
            hi = max(hi, ch["hi"])
        self.chains[str(mode_id)] = {"lo": lo, "hi": hi}
        return joined

    def synced_count(self, key: str) -> int | None:
        return (self.profile.get("synced") or {}).get(key)

    def set_synced_count(self, key: str, count: int | None) -> None:
        if isinstance(count, int):
            self.profile.setdefault("synced", {})[key] = count

    # ---------------- 跑谱结果 ----------------
    def put_results(self, games: list[dict[str, Any]]) -> None:
        for g in games:
            self.results[g["uuid"]] = g
        self.save_games()

    def reset_reviews(self) -> tuple[int, int]:
        """--fresh: 清掉该玩家所有跑谱结果和原始报告 (对局记录和玩家信息保留)."""
        n = len(self.results)
        self.results.clear()
        m = 0
        for f in self.reports_dir.glob("*.json"):
            try:
                f.unlink()
                m += 1
            except OSError:
                pass
        self.profile["legacy_imported"] = True  # 别再把旧版缓存导回来
        self.save_games()
        self.save_profile()
        return n, m

    def import_legacy(self, out_dir: pathlib.Path) -> tuple[int, int]:
        """把旧版放在输出目录里的 results.json / reports/ 导进来 (只做一次, 原文件不动)."""
        if self.profile.get("legacy_imported"):
            return 0, 0
        old = _read(out_dir / "results.json", None, quarantine=False)
        n = m = 0
        if isinstance(old, dict) and str(old.get("uid")) == str(self.uid):
            for g in old.get("games") or []:
                u = g.get("uuid")
                if not u or (self.results.get(u) or {}).get("rating") is not None:
                    continue
                if g.get("rating") is None and not g.get("task_id"):
                    continue
                self.results[u] = g
                n += 1
            if old.get("nickname") and not self.profile.get("nickname"):
                self.set_nickname(old["nickname"])
        src = out_dir / "reports"
        if src.exists():
            for f in src.glob(f"*_a{self.uid}.json"):
                dst = self.reports_dir / f.name
                if not dst.exists():
                    self.reports_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dst)
                    m += 1
        self.profile["legacy_imported"] = True
        self.save_games()
        self.save_profile()
        return n, m

    # ---------------- 上次运行 ----------------
    def set_last_run(self, uuids: list[str], mode_ids: list[int], want: int,
                     new_uuids: list[str] | None = None) -> None:
        """new_uuids: 这次运行新拿到报告的对局 (差异报告默认只看这些)."""
        self.profile["last_run"] = {"uuids": uuids, "new_uuids": new_uuids or [],
                                    "mode_ids": mode_ids, "games": want, "at": int(time.time())}

    def last_run_games(self) -> list[dict[str, Any]]:
        uuids = (self.profile.get("last_run") or {}).get("uuids") or []
        return [self.results[u] for u in uuids if u in self.results]

    def new_uuids(self) -> list[str]:
        return list((self.profile.get("last_run") or {}).get("new_uuids") or [])

    def default_selection(self) -> tuple[list[str], str]:
        """差异报告默认选哪些局: 上次新增的 -> 上次运行的全部 -> 本地所有有报告的."""
        have = {g["uuid"] for g in self.library()}
        new = [u for u in self.new_uuids() if u in have]
        if new:
            return new, "上次运行新增"
        last = [g["uuid"] for g in self.last_run_games() if g["uuid"] in have]
        if last:
            return last, "上次运行 (无新增)"
        return sorted(have), "全部本地对局"

    # ---------------- 本地对局库 ----------------
    def has_report(self, g: dict[str, Any]) -> bool:
        return bool(g.get("report_file")) and (self.reports_dir / g["report_file"]).exists()

    def library(self) -> list[dict[str, Any]]:
        """本地存了原始报告的全部对局, 新的在前. 缺差异数的(旧版导入的)顺手补算并存起来."""
        out: list[dict[str, Any]] = []
        dirty = False
        for g in self.results.values():
            if not self.has_report(g):
                continue
            if g.get("diff_count") is None:
                rep = _read(self.reports_dir / g["report_file"], None, quarantine=False)
                if isinstance(rep, dict):
                    g["diff_count"] = count_diffs(rep)
                    dirty = True
            out.append(g)
        if dirty:
            self.save_games()
        return sorted(out, key=lambda g: g.get("start_time") or 0, reverse=True)


def count_diffs(report: dict[str, Any]) -> int:
    kyokus = (report.get("review") or {}).get("kyokus") or []
    return sum(1 for k in kyokus for e in (k.get("entries") or []) if e.get("is_equal") is False)


def list_players(root: pathlib.Path) -> list[tuple[int, str]]:
    """本地有数据的玩家 (UID, 昵称), 最近更新的在前."""
    hits = [p for p in root.glob("*/player.json") if p.parent.name.isdigit()] \
        if root.exists() else []
    hits.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [(int(p.parent.name), (_read(p, {}, quarantine=False) or {}).get("nickname") or "")
            for p in hits]
