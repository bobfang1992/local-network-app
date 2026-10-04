"""设备去留历史:从 categorization_log 算出「每小时在不在」和「什么时候来、什么时候走」。

数据源:每次扫描,在线的设备在 categorization_log 里各有一行 device_status='online'(scan_id 对得上 scans.id)。
**没出现 = 那次扫描里没有它的 online 行**,不是有一行 offline —— 离开太久的设备根本不再记行。
所以判断「不在」必须拿 scans 表当分母:那个小时扫过几次、它出现了几次。

⚠️ 时间:库里存的是**服务器本地时间、不带时区**(bobrasp2 是 Europe/London)。
这里一律用 `datetime.fromisoformat(s).astimezone()` 按系统时区规则(含夏令时)转成 epoch 毫秒再给前端,
前端拿到的是绝对时刻,不用再猜时区。
"""
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


def to_ms(ts: str) -> int:
    return int(datetime.fromisoformat(ts).astimezone().timestamp() * 1000)


def hourly_presence(conn, ip: str, days: int = 14) -> List[Dict]:
    """最近 days 天,每个小时:扫了几次、这台出现了几次。小时按服务器本地时间切。"""
    since = (datetime.now() - timedelta(days=days)).isoformat()
    scans = dict(conn.execute(
        "SELECT substr(scan_time,1,13) h, count(*) FROM scans WHERE scan_time >= ? GROUP BY h",
        (since,)).fetchall())
    seen = dict(conn.execute(
        "SELECT substr(timestamp,1,13) h, count(DISTINCT scan_id) FROM categorization_log "
        "WHERE ip = ? AND device_status = 'online' AND timestamp >= ? GROUP BY h",
        (ip, since)).fetchall())
    out = []
    start = datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(days=days)
    h = start
    while h <= datetime.now():
        key = h.strftime("%Y-%m-%dT%H")
        out.append({"t": to_ms(h.isoformat()), "scans": scans.get(key, 0), "seen": seen.get(key, 0)})
        h += timedelta(hours=1)
    return out


def detect_events(scans: Sequence[Tuple[int, int]], present: Dict[str, set],
                  min_away_ms: int) -> List[Dict]:
    """纯函数。scans: [(scan_id, t_ms)] 按时间升序;present: ip -> 出现过的 scan_id 集合。

    防抖:连续缺席**超过 min_away_ms** 才算「走了」(手机息屏掉一两次扫描不算)。
    走的时刻记**最后一次见到**的时间;回来时带上离开了多久。窗口开头的状态不产生事件。
    """
    events: List[Dict] = []
    for ip, ids in present.items():
        state: Optional[bool] = None      # True=在, False=已确认离开
        last_seen: Optional[int] = None
        left_at: Optional[int] = None
        for sid, t in scans:
            here = sid in ids
            if here:
                if state is False:
                    events.append({"ip": ip, "type": "arrive", "t": t,
                                   "away_ms": t - left_at if left_at else None})
                state, last_seen = True, t
            else:
                if state is None:
                    state = False if not ids or min(ids) > sid else state
                elif state is True and last_seen is not None and t - last_seen > min_away_ms:
                    events.append({"ip": ip, "type": "leave", "t": last_seen})
                    state, left_at = False, last_seen
    events.sort(key=lambda e: e["t"], reverse=True)
    return events


def recent_events(conn, hours: int = 72, min_away_min: int = 15) -> List[Dict]:
    since = (datetime.now() - timedelta(hours=hours)).isoformat()
    scans = [(sid, to_ms(t)) for sid, t in conn.execute(
        "SELECT id, scan_time FROM scans WHERE scan_time >= ? ORDER BY id", (since,)).fetchall()]
    if not scans:
        return []
    present: Dict[str, set] = {}
    for ip, sid in conn.execute(
            "SELECT ip, scan_id FROM categorization_log WHERE device_status = 'online' AND scan_id >= ?",
            (scans[0][0],)):
        present.setdefault(ip, set()).add(sid)
    events = detect_events(scans, present, min_away_min * 60 * 1000)
    names = {ip: (notes or "").strip() or (host if host and host != "Unknown" else "")
             for ip, notes, host in conn.execute("SELECT ip, notes, hostname FROM devices")}
    for e in events:
        e["name"] = names.get(e["ip"], "")
    return events


def server_offset_min() -> int:
    off = datetime.now().astimezone().utcoffset()
    return int(off.total_seconds() // 60) if off else 0
