"""去留事件的防抖规则。跑法:cd backend && python -m pytest test_presence.py"""
from presence import detect_events

M = 60_000
SCANS = [(i, i * M) for i in range(1, 61)]   # 每分钟一次扫描


def test_short_blip_is_not_a_departure():
    # 掉两次扫描(手机息屏)不算走
    ev = detect_events(SCANS, {"ph": set(range(1, 11)) | set(range(13, 61))}, 15 * M)
    assert ev == []


def test_leave_then_arrive_records_last_seen_and_away_time():
    ev = detect_events(SCANS, {"ph": set(range(1, 21)) | set(range(51, 61))}, 15 * M)
    assert [e["type"] for e in ev] == ["arrive", "leave"]
    leave, arrive = ev[1], ev[0]
    assert leave["t"] == 20 * M                 # 走的时刻 = 最后一次见到
    assert arrive["t"] == 51 * M
    assert arrive["away_ms"] == 31 * M


def test_first_appearance_in_window_is_an_arrival_without_away_time():
    ev = detect_events(SCANS, {"tv": set(range(30, 61))}, 15 * M)
    assert ev == [{"ip": "tv", "type": "arrive", "t": 30 * M, "away_ms": None}]


def test_present_whole_window_produces_nothing():
    assert detect_events(SCANS, {"nas": set(range(1, 61))}, 15 * M) == []
