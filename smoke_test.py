"""Headless smoke test: run the TUI against a fake bettercap REST server."""
import asyncio, json, threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from bettertui.api import BettercapClient
from bettertui.app import BetterTUI

SESSION = {
    "version": "2.33",
    "interface": {"ipv4": "192.168.1.10"},
    "gateway": {"ipv4": "192.168.1.1"},
    "modules": [
        {"name": "net.probe", "running": False},
        {"name": "net.recon", "running": True},
        {"name": "arp.spoof", "running": False},
    ],
    "lan": {"hosts": [
        {"ipv4": "192.168.1.1", "mac": "aa:bb:cc:dd:ee:ff", "hostname": "router", "vendor": "Cisco"},
        {"ipv4": "192.168.1.42", "mac": "de:ad:be:ef:00:01", "hostname": "laptop", "vendor": "Dell"},
    ]},
}
EVENTS = [{"time": "2026-10-03T12:04:33Z", "tag": "endpoint.new",
           "data": {"message": "192.168.1.42 detected"}}]
posted: list[str] = []


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        if self.path == "/api/session": self._send(SESSION)
        elif self.path == "/api/events": self._send(EVENTS)
        else: self.send_response(404); self.end_headers()
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        cmd = json.loads(self.rfile.read(n) or b"{}").get("cmd", "")
        posted.append(cmd)
        if cmd == "net.probe on":
            SESSION["modules"][0]["running"] = True
        self._send({"success": True})


async def main():
    srv = HTTPServer(("127.0.0.1", 8099), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    client = BettercapClient(port=8099, username="user", password="pass")
    app = BetterTUI(client, poll=0.3)
    async with app.run_test() as pilot:
        await pilot.pause(0.6)                      # let first refresh land
        hosts = app.query_one("#hosts")
        assert hosts.row_count == 2, f"hosts={hosts.row_count}"
        mods = app.query_one("#modules")
        assert mods.row_count == 3, f"mods={mods.row_count}"
        await pilot.press("s")                      # toggle scan -> net.probe on
        await pilot.pause(0.5)
        assert "net.probe on" in posted, posted
        app.query_one("#hosts").move_cursor(row=1)  # select the laptop
        await pilot.press("a")                      # arp spoof it
        await pilot.pause(0.5)
        assert "set arp.spoof.targets 192.168.1.42" in posted, posted
        assert "arp.spoof on" in posted, posted
    await client.aclose(); srv.shutdown()
    print("SMOKE OK — commands sent:", posted)


asyncio.run(main())
