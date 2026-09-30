from pathlib import Path

from sedori import db
from sedori.collector.csv_collector import CsvCollector
from sedori.config import build_config
from sedori.pipeline import run_pipeline

SAMPLE = Path(__file__).parent.parent / "data" / "sample_items.csv"


class Rec:
    name = "rec"

    def __init__(self):
        self.sent = []

    def send(self, item, market, verdict):
        self.sent.append(item.item_id)
        return True


def cfg():
    return build_config({
        "profit": {"size_class_by_keyword": {"switch": "s80", "airpods": "compact"}},
        "exclude": {"keywords_junk": ["ジャンク"], "brands": ["ルイヴィトン"], "categories": ["チケット"]},
    })


def test_end_to_end_and_no_duplicate_notification():
    from datetime import datetime
    conn = db.connect(":memory:")
    n = Rec()
    now = datetime(2026, 6, 30)
    st = run_pipeline(conn, CsvCollector(SAMPLE), [n], cfg(), now=now)
    # m1001: 条件OK / m1006: 着払いでも利益条件OK。ジャンク・ブランド・高値・相場なしは対象外
    assert n.sent == ["m1001", "m1006"]
    assert st.notified == 2
    st2 = run_pipeline(conn, CsvCollector(SAMPLE), [n], cfg(), now=now)
    assert len(n.sent) == 2 and st2.notified == 0 and st2.skipped_duplicate == 2


def test_failed_send_not_marked_notified():
    from datetime import datetime

    class Fail(Rec):
        def send(self, *a):
            return False

    conn = db.connect(":memory:")
    st = run_pipeline(conn, CsvCollector(SAMPLE), [Fail()], cfg(), now=datetime(2026, 6, 30))
    assert st.notified == 0 and st.errors == 2
    assert conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == 0
