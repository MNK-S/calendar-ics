"""Generate a small hand-picked sample feed for visual checking."""

from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from eventernote_ics import Event, build_ics, load_groups

EVENTS = [
    Event(
        id="sample-500473",
        title="学園アイドルマスター『氷渡香名江 1st Single』リリース記念イベント [大阪]【1回目】",
        day=date(2027, 3, 14),
        url="https://www.eventernote.com/events/500473",
        venue="アニメイト大阪日本橋 5Fイベントホール",
        open_time=time(11, 0),
        start_time=time(12, 0),
        end_time=time(13, 0),
        performers=["学園アイドルマスター", "安倍彩野夏", "川村玲奈"],
        official_links=[
            "https://www.animate-onlineshop.jp/sphone/contents/fair_event/detail.php?id=116833"
        ],
    ),
    Event(
        id="sample-485534",
        title="『湊みやの一枚いいですか？』〜1st Location 福岡編〜【ゲスト：川村玲奈】昼の部",
        day=date(2026, 11, 29),
        url="https://www.eventernote.com/events/485534",
        venue="雷5656会館ときわホール",
        open_time=time(13, 15),
        start_time=time(14, 0),
        end_time=time(15, 30),
        performers=["湊みや", "川村玲奈"],
    ),
    Event(
        id="sample-495955",
        title="第13回 新千歳空港国際アニメーション映画祭 映画「BanG Dream! Ave Mujica prima aurora」",
        day=date(2026, 11, 21),
        url="https://www.eventernote.com/events/495955",
        venue="新千歳空港シアター",
        start_time=time(19, 30),
        end_time=time(21, 30),
        performers=["渡瀬結月", "高尾奏音", "Ave Mujica"],
    ),
    Event(
        id="sample-499987",
        title="渡瀬結月 Birthday Event 2027 こっち向いて、わたせ",
        day=date(2027, 2, 13),
        url="https://www.eventernote.com/events/499987",
        venue="ハーモニースクエア3F ハーモニーホール",
        performers=["渡瀬結月"],
    ),
    Event(
        id="sample-499364",
        title="朗読劇『明治法廷異聞 ―残照の狼牙―』2027年1月31日①",
        day=date(2027, 1, 31),
        url="https://www.eventernote.com/events/499364",
        performers=["堀金蒼平", "村井雄治", "山崎直宣", "川村玲奈", "波間まさし", "清水大登", "花まどか"],
    ),
    Event(
        id="sample-495477",
        title="斉藤朱夏 ファンイベント 2026 inソウル 12月6日 1部",
        day=date(2026, 12, 6),
        url="https://www.eventernote.com/events/495477",
        venue="Aube Studio",
        place_id="27978",
        tz_name="Asia/Seoul",
        open_time=time(13, 0),
        start_time=time(13, 30),
        end_time=time(15, 30),
        performers=["斉藤朱夏"],
        official_links=["https://atashi-shuka.bitfan.id/contents/447178"],
    ),
    Event(
        id="sample-487010",
        title="Yuuri Live 2026 in Los Angeles",
        day=date(2026, 9, 26),
        url="https://www.eventernote.com/events/487010",
        venue="The Wiltern",
        place_id="6794",
        tz_name="America/Los_Angeles",
        open_time=time(19, 0),
        start_time=time(20, 0),
        end_time=time(22, 0),
        performers=["優里(シンガーソングライター)"],
    ),
]

if __name__ == "__main__":
    groups = load_groups()
    ics = build_ics(EVENTS, groups, datetime.now(ZoneInfo("Asia/Tokyo")))
    Path("sample.ics").write_text(ics, encoding="utf-8", newline="")
    print("wrote sample.ics")
