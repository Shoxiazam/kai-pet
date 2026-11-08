"""Сеть Каев: дружба по коду, гости, открытки, защита от чужих — без настоящего ntfy.sh."""
import json
import shutil
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox

from kai_pet import network as net_module
from kai_pet.pet import ASSETS, look_id
from test_features import pet, played  # noqa: F401  (фикстуры)

FRIEND = "friendBox123"


class FakeTransport:
    def __init__(self):
        self.sent, self.listening = [], None

    def publish(self, box, message):
        self.sent.append((box, message))
        return True

    def listen(self, box, since, on_message):
        self.listening = box

    def stop(self):
        self.listening = None


def _net(pet):
    fake = FakeTransport()
    pet.network.transport = fake
    pet.network._save(name="Шохрух")
    return pet.network, fake


def _from_friend(net, kind, **fields):
    net._handle({"v": 1, "type": kind, "from": FRIEND, "name": "Азиз", **fields}, "id1")


def test_code_and_parsing(pet):
    net, _ = _net(pet)
    assert net.code.startswith("KAI-") and net.code == net.code            # код стабильный
    assert net_module.parse_code(" kai-abcDEF12_x ") == "abcDEF12_x"
    assert net_module.parse_code("привет") is None
    assert net_module.clean_text("а\nб\x00в" + "я" * 99, 10) == "а б в" + "я" * 5


def test_friendship_by_code(pet):
    net, fake = _net(pet)
    assert net.add_friend("KAI-" + FRIEND)
    assert fake.sent[-1][0] == FRIEND and fake.sent[-1][1]["type"] == "hello" and fake.listening == net.my_id
    _from_friend(net, "hello_ok")
    assert net.friends == {FRIEND: "Азиз"}


def test_stranger_cannot_add_himself(pet):
    net, fake = _net(pet)
    _from_friend(net, "hello_ok")                       # мы ему не писали
    assert net.friends == {}
    _from_friend(net, "card", text="спам")
    assert pet.sign_text != "спам"                       # открытки — только от друзей


def test_friend_request_asks_owner(pet, monkeypatch):
    net, fake = _net(pet)
    monkeypatch.setattr(net, "_run_box", lambda box: QMessageBox.No)
    _from_friend(net, "hello")
    assert net.friends == {}
    monkeypatch.setattr(net, "_run_box", lambda box: QMessageBox.Yes)
    _from_friend(net, "hello")
    assert net.friends == {FRIEND: "Азиз"} and fake.sent[-1][1]["type"] == "hello_ok"


def _befriend(net):
    net._save(friends={FRIEND: "Азиз"})


def test_card_shows_on_sign_cleaned(pet):
    net, _ = _net(pet)
    _befriend(net)
    _from_friend(net, "card", text="С днём\nрождения!\x07" + "!" * 100)
    assert pet.sign_text.startswith("С днём рождения!") and len(pet.sign_text) <= net_module.TEXT_MAX
    assert "Азиз" in pet.bubble.text.text()


def test_guest_visits_and_says_goodbye(pet, monkeypatch, tmp_path):
    net, fake = _net(pet)
    _befriend(net)
    monkeypatch.setattr(pet, "looks_root", lambda: tmp_path / "looks")
    look = net_module.safe_look({"kind": "fox", "color": "ginger", "acc": ["bow", "my_secret_svg", 5]})
    assert look["acc"] == ["bow"]                        # чужие свои-вещи и мусор не проходят
    shutil.copytree(ASSETS / "frames", net.guests_dir() / look_id(look) / "frames")
    pet.show()
    _from_friend(net, "visit", look={"kind": "fox", "color": "ginger", "acc": ["bow"]})
    assert net.guest is not None and net.guest.widget.isVisible()
    _from_friend(net, "visit", look={})                  # второй гость в это время не приходит
    QTest.qWait(300)
    net.guest.leave()
    assert net.guest is None and fake.sent[-1] == (FRIEND, fake.sent[-1][1]) and fake.sent[-1][1]["type"] == "visit_done"


def test_my_kai_goes_visiting_and_returns(pet):
    net, fake = _net(pet)
    _befriend(net)
    net.visit(FRIEND)
    assert fake.sent[-1][1]["type"] == "visit" and fake.sent[-1][1]["look"] == pet.look
    assert net.away == "Азиз" and "Азиз" in pet.sign_text
    _from_friend(net, "visit_done")
    assert net.away is None and "Азиз" not in pet.sign_text


def test_rate_limit(pet):
    net, _ = _net(pet)
    _befriend(net)
    for i in range(20):
        _from_friend(net, "card", text=f"№{i}")
    assert pet.sign_text == f"№{net_module.RATE_PER_MIN - 1}"   # дальше — отброшено


def test_transport_reads_ntfy_stream():
    """Настоящий цикл приёма против маленького сервера, отвечающего как ntfy (строки JSON)."""
    events = [{"event": "open"}, {"event": "message", "id": "m1", "message": json.dumps({"type": "card", "text": "hi"})},
              {"event": "message", "id": "m2", "message": "не json"}]
    posted = []

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            for e in events:
                self.wfile.write((json.dumps(e) + "\n").encode())

        def do_POST(self):
            posted.append((self.path, self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    t = net_module.Transport(f"http://127.0.0.1:{srv.server_port}")
    got = []
    t.listen("me", "12h", lambda m, since: got.append((m, since)))
    for _ in range(50):
        if got:
            break
        time.sleep(0.05)
    t.stop()
    assert got[0] == ({"type": "card", "text": "hi"}, "m1")
    assert t.publish("friend", {"type": "hello"}) and posted[0][0] == "/kaipet-friend"
    srv.shutdown()
