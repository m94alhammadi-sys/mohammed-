"""اختبارات واجهة HTTP والدردشة."""
import pytest
from fastapi.testclient import TestClient

from tests.fakes import FakeLLM, ok_connector


@pytest.fixture
def client(monkeypatch, tmp_path):
    """عميل اختبار بقاعدة بيانات معزولة ونموذج وهمي وبلا أي شبكة."""
    import backend.main as main
    from backend.memory import SqliteBM25Store
    from backend.store import ChatStore

    # عزل التخزين: كل اختبار يبدأ من قاعدة نظيفة
    monkeypatch.setattr(main, "store", ChatStore(tmp_path / "chat.db"))
    monkeypatch.setattr(main, "memory", SqliteBM25Store(tmp_path / "mem.db"))
    monkeypatch.setattr(main.orchestrator, "memory", main.memory)
    monkeypatch.setattr(main.orchestrator.chief, "memory", main.memory)
    for agent in main.orchestrator.agents.values():
        monkeypatch.setattr(agent, "memory", main.memory)

    async def fake_gather(agent_id, topic):
        return [ok_connector()]

    monkeypatch.setattr("backend.agents.base.gather_context", fake_gather)

    fake = FakeLLM()
    monkeypatch.setattr(main.orchestrator, "llm", fake)
    monkeypatch.setattr(main.orchestrator.chief, "llm", fake)
    for agent in main.orchestrator.agents.values():
        monkeypatch.setattr(agent, "llm", fake)

    with TestClient(main.app) as test_client:
        test_client.app_module = main
        yield test_client


def test_health(client):
    body = client.get("/api/health").json()
    assert body["ok"] is True and "model" in body


def test_chat_list_contains_war_room_and_every_agent(client):
    chats = client.get("/api/chats").json()
    ids = [c["id"] for c in chats]
    assert ids[0] == "war_room"
    for agent in ("abu_aloloum", "political_analyst", "economic_analyst",
                  "breaking_desk", "the_trader", "chief"):
        assert agent in ids


def test_war_room_is_marked_as_group_with_members(client):
    war_room = client.get("/api/chats").json()[0]
    assert war_room["is_group"] is True
    assert len(war_room["members"]) == 6


def test_direct_chat_roundtrip(client):
    response = client.post("/api/chat", json={"chat_id": "the_trader", "text": "ما وضع الذهب؟"})
    assert response.status_code == 200
    assert response.json()["author"] == "the_trader"

    history = client.get("/api/chats/the_trader/messages").json()
    assert [m["author"] for m in history] == ["user", "the_trader"]


def test_empty_message_is_rejected(client):
    assert client.post("/api/chat", json={"chat_id": "the_trader", "text": "   "}).status_code == 400


def test_unknown_chat_is_rejected(client):
    assert client.post("/api/chat", json={"chat_id": "ghost", "text": "مرحباً"}).status_code == 404


def test_cycle_produces_reports_and_a_decision(client):
    assert client.post("/api/cycle", json={"topic": "الذهب"}).json()["status"] == "started"

    # الدورة تعمل في الخلفية؛ ننتظر اكتمالها عبر ظهور القرار.
    import time
    for _ in range(100):
        messages = client.get("/api/chats/war_room/messages").json()
        if any(m["kind"] == "decision" for m in messages):
            break
        time.sleep(0.05)
    else:
        pytest.fail("لم يصدر قرار خلال المهلة")

    kinds = [m["kind"] for m in messages]
    assert kinds.count("report") == 5
    assert kinds.count("decision") == 1

    decision = next(m for m in messages if m["kind"] == "decision")
    assert "التقرير التنفيذي" in decision["text"]
    assert "decision_id" in decision["meta"]


def test_decision_is_retrievable_as_json(client):
    client.post("/api/cycle", json={"topic": "النفط"})
    import time
    for _ in range(100):
        listing = client.get("/api/decisions").json()
        if listing:
            break
        time.sleep(0.05)
    else:
        pytest.fail("لم يُحفظ أي قرار")

    payload = client.get(f"/api/decisions/{listing[0]['decision_id']}").json()
    assert "recommendation" in payload and "sources_used" in payload


def test_missing_decision_returns_404(client):
    assert client.get("/api/decisions/dec_missing").status_code == 404


def test_cycle_requires_a_topic(client):
    assert client.post("/api/cycle", json={"topic": "  "}).status_code == 400


def test_clearing_a_chat_empties_it(client):
    client.post("/api/chat", json={"chat_id": "the_trader", "text": "مرحباً"})
    assert client.delete("/api/chats/the_trader/messages").json()["deleted"] >= 1
    assert client.get("/api/chats/the_trader/messages").json() == []


def test_websocket_announces_mode(client):
    with client.websocket_connect("/ws") as socket:
        event = socket.receive_json()
        assert event["event"] == "ready" and "llm_enabled" in event["data"]


def test_websocket_streams_chat_messages(client):
    with client.websocket_connect("/ws") as socket:
        socket.receive_json()                       # ready
        client.post("/api/chat", json={"chat_id": "the_trader", "text": "مرحباً"})
        seen = [socket.receive_json() for _ in range(3)]
        assert any(e["event"] == "message" and e["data"]["author"] == "user" for e in seen)
        assert any(e["event"] == "status" for e in seen)


def test_index_page_is_served(client):
    response = client.get("/")
    assert response.status_code == 200 and "مجلس القرار" in response.text
