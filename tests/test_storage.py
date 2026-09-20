import pytest

from advisor.storage import Storage


@pytest.fixture
async def store(tmp_path):
    s = Storage(str(tmp_path / "t.sqlite3"))
    yield s
    await s.close()


async def test_user_created_with_defaults(store):
    profile = await store.ensure_user(7, "محمد")
    assert profile.user_id == 7
    assert profile.risk_profile == "متوازن"
    assert profile.daily_brief is False
    assert "متوازن" in profile.as_context()


async def test_ensure_user_is_idempotent_and_keeps_name(store):
    await store.ensure_user(7, "محمد")
    await store.update_profile(7, risk_profile="محافظ")
    again = await store.ensure_user(7, "")           # اسم فاضي لا يمسح القديم
    assert again.display_name == "محمد"
    assert again.risk_profile == "محافظ"


async def test_watchlist_add_dedupe_remove(store):
    await store.ensure_user(1)
    await store.add_watch(1, "btc")
    await store.add_watch(1, "BTC")                   # نفس الرمز بحالة مختلفة
    assert await store.get_watchlist(1) == ["BTC"]
    await store.remove_watch(1, "btc")
    assert await store.get_watchlist(1) == []


async def test_holdings_upsert_preserves_price_when_omitted(store):
    await store.ensure_user(1)
    await store.upsert_holding(1, "eth", 2, 3000, "طويل المدى")
    await store.upsert_holding(1, "ETH", 3)           # تحديث كمية فقط
    holdings = await store.get_holdings(1)
    assert holdings == [{"symbol": "ETH", "quantity": 3.0, "avg_price": 3000.0, "note": ""}]


async def test_history_is_trimmed_and_ordered(store):
    await store.ensure_user(1)
    for i in range(6):
        await store.append_message(1, "user", f"س{i}")
    recent = await store.recent_messages(1, 3)
    assert [m["content"] for m in recent] == ["س3", "س4", "س5"]
    await store.clear_messages(1)
    assert await store.recent_messages(1, 10) == []


async def test_daily_brief_subscribers(store):
    await store.ensure_user(1)
    await store.ensure_user(2)
    await store.update_profile(2, daily_brief=True)
    subs = await store.subscribers()
    assert [s.user_id for s in subs] == [2]
