import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.app import create_app
from test_safety import engine

HOST = "192.168.1.55"
ACCESS = "test-access-secret-" + "x" * 32


def test_remote_requires_link_then_can_use_authenticated_controls(tmp_path):
    e = engine(tmp_path)
    app = create_app(e, {"host": HOST, "access_token": ACCESS})
    with TestClient(app, base_url=f"http://{HOST}:8765", client=("192.168.1.99", 1234)) as client:
        assert client.get("/").status_code == 403
        assert client.get("/api/session").status_code == 403
        assert client.get("/?access=wrong").status_code == 403
        assert client.get("/?access=错误令牌").status_code == 403
        login = client.get(f"/?access={ACCESS}", follow_redirects=False)
        assert login.status_code == 303 and login.headers["location"] == "/"
        assert "HttpOnly" in login.headers["set-cookie"]
        assert login.headers["referrer-policy"] == "no-referrer"
        assert client.get("/api/session").status_code == 200
        state = client.get("/api/state")
        assert state.status_code == 200
        assert f"ws://{HOST}:8765" in state.headers["content-security-policy"]
        assert client.post("/api/control/stop", headers={"X-Studio": "1", "Origin": f"http://{HOST}:8765"}).status_code == 200
        assert client.post("/api/control/stop", headers={"X-Studio": "1", "Origin": "http://evil.example"}).status_code == 403
        with client.websocket_connect(f"ws://{HOST}:8765/ws/control", headers={"Origin": f"http://{HOST}:8765"}) as ws:
            assert ws.receive_json()["type"] == "state"


def test_remote_cannot_authenticate_via_localhost_host_header(tmp_path):
    app = create_app(engine(tmp_path), {"host": HOST, "access_token": ACCESS})
    with TestClient(app, client=("192.168.1.99", 1234)) as client:
        assert client.get("/api/session", headers={"Host": "localhost"}).status_code == 403
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/control", headers={"Origin": f"http://{HOST}:8765"}):
                pass


@pytest.mark.parametrize("host", ["0.0.0.0", "8.8.8.8", "127.0.0.1"])
def test_lan_config_rejects_non_lan_addresses(host):
    with pytest.raises(ValueError):
        create_app(lan_config={"host": host, "access_token": ACCESS})
