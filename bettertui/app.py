"""bettertui — a friendly Textual front-end for bettercap.

Drives the real bettercap engine over its REST API. The engine does the work;
this just makes it discoverable: live host/module panels, an event log, one-key
actions for the common workflows, and a raw command bar for everything else.
"""

from __future__ import annotations

import argparse

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Input, RichLog, Static

from .api import BettercapClient, BettercapError, Event

# ---- quick-action recipes -------------------------------------------------
# Each is a bettercap command (or chain) that a keypress fires. This is the
# layer that turns "memorize the module names" into "press a key".
RECIPES: dict[str, list[str]] = {
    "scan_on": ["net.probe on"],
    "scan_off": ["net.probe off"],
    "arp_on": [
        "set arp.spoof.fullduplex true",
        "set arp.spoof.targets {ip}",
        "arp.spoof on",
    ],
    "arp_off": ["arp.spoof off"],
    "sniff_on": ["net.sniff on"],
    "sniff_off": ["net.sniff off"],
}


class BetterTUI(App):
    TITLE = "bettertui"
    SUB_TITLE = "a friendlier bettercap"
    CSS_PATH = "styles.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("s", "toggle_scan", "Scan"),
        Binding("a", "arp_spoof", "ARP spoof host"),
        Binding("k", "arp_stop", "Stop spoof"),
        Binding("n", "toggle_sniff", "Sniff"),
        Binding("slash", "focus_cmd", "Command"),
        Binding("c", "clear_log", "Clear log"),
    ]

    def __init__(self, client: BettercapClient, poll: float = 2.0) -> None:
        super().__init__()
        self.client = client
        self.poll = poll
        self._scan_on = False
        self._sniff_on = False

    # ---- layout -----------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="top"):
            with Vertical(id="hosts-pane"):
                yield Static("Hosts  [dim](↑/↓ to select)[/]", classes="pane-title")
                yield DataTable(id="hosts", cursor_type="row", zebra_stripes=True)
            with Vertical(id="modules-pane"):
                yield Static("Modules", classes="pane-title")
                yield DataTable(id="modules", cursor_type="row")
        yield RichLog(id="log", wrap=True, highlight=True, markup=True)
        yield Input(placeholder="bettercap command  (e.g. net.show)  — Enter to run", id="cmd")
        yield Footer()

    def on_mount(self) -> None:
        hosts = self.query_one("#hosts", DataTable)
        hosts.add_columns("IP", "MAC", "Name", "Vendor")
        mods = self.query_one("#modules", DataTable)
        mods.add_columns("Module", "State")
        self.log_line("[bold]bettertui[/] connected to " + self.client.base)
        self.log_line("[dim]Only run ARP/sniff actions against networks you own or are authorised to test.[/]")
        self.set_interval(self.poll, self.refresh_now)
        self.refresh_now()

    # ---- helpers ----------------------------------------------------------
    def log_line(self, text: str) -> None:
        self.query_one("#log", RichLog).write(text)

    def selected_ip(self) -> str | None:
        table = self.query_one("#hosts", DataTable)
        if table.row_count == 0 or table.cursor_row is None:
            return None
        try:
            row = table.get_row_at(table.cursor_row)
        except Exception:
            return None
        return str(row[0]) if row else None

    @work(exclusive=True, group="refresh")
    async def refresh_now(self) -> None:
        try:
            session = await self.client.session()
            events = await self.client.events()
        except BettercapError as e:
            self.log_line(f"[red]{e}[/]")
            return
        self._render_hosts(session.hosts)
        self._render_modules(session.modules)
        self._render_events(events)
        self.sub_title = f"iface {session.iface or '?'} · gw {session.gateway or '?'} · bettercap {session.version or '?'}"

    def _render_hosts(self, hosts) -> None:
        table = self.query_one("#hosts", DataTable)
        keep = self.selected_ip()
        table.clear()
        for h in sorted(hosts, key=lambda x: _ip_key(x.ip)):
            table.add_row(h.ip, h.mac, h.name or "[dim]—[/]", h.vendor or "[dim]—[/]", key=h.ip)
        if keep is not None:
            try:
                table.move_cursor(row=table.get_row_index(keep))
            except Exception:
                pass

    def _render_modules(self, modules) -> None:
        table = self.query_one("#modules", DataTable)
        table.clear()
        for m in sorted(modules, key=lambda x: (not x.running, x.name)):
            state = "[green]● on[/]" if m.running else "[dim]○ off[/]"
            table.add_row(m.name, state, key=m.name)
            if m.name == "net.probe":
                self._scan_on = m.running
            if m.name == "net.sniff":
                self._sniff_on = m.running

    def _render_events(self, events: list[Event]) -> None:
        # Only append events we haven't shown yet (dedupe against last render).
        prev = getattr(self, "_shown_sig", None)
        if prev is None:
            new = events[-15:]
        else:
            new = [e for e in events if (e.time, e.tag, e.message) not in prev]
        self._shown_sig = set((e.time, e.tag, e.message) for e in events[-200:])
        for e in new:
            self.log_line(f"[dim]{e.time[-8:]}[/] [cyan]{e.tag}[/] {e.message}")

    @work(group="cmd")
    async def _fire(self, cmds: list[str], ip: str | None = None) -> None:
        for raw in cmds:
            cmd = raw.format(ip=ip) if ip else raw
            try:
                await self.client.run(cmd)
                self.log_line(f"[green]›[/] {cmd}")
            except BettercapError as e:
                self.log_line(f"[red]✗ {cmd} — {e}[/]")
                return
        self.refresh_now()

    # ---- actions ----------------------------------------------------------
    def action_refresh(self) -> None:
        self.refresh_now()

    def action_toggle_scan(self) -> None:
        self._fire(RECIPES["scan_off" if self._scan_on else "scan_on"])

    def action_toggle_sniff(self) -> None:
        self._fire(RECIPES["sniff_off" if self._sniff_on else "sniff_on"])

    def action_arp_spoof(self) -> None:
        ip = self.selected_ip()
        if not ip:
            self.log_line("[yellow]Select a host first (↑/↓ in the Hosts panel).[/]")
            return
        self.log_line(f"[yellow]ARP spoofing {ip} — stop with 'k'.[/]")
        self._fire(RECIPES["arp_on"], ip=ip)

    def action_arp_stop(self) -> None:
        self._fire(RECIPES["arp_off"])

    def action_clear_log(self) -> None:
        self.query_one("#log", RichLog).clear()

    def action_focus_cmd(self) -> None:
        self.query_one("#cmd", Input).focus()

    @on(Input.Submitted, "#cmd")
    def on_cmd(self, event: Input.Submitted) -> None:
        cmd = event.value.strip()
        event.input.value = ""
        if cmd:
            self._fire([cmd])


def _ip_key(ip: str):
    try:
        return tuple(int(p) for p in ip.split("."))
    except ValueError:
        return (999,)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bettertui", description="A friendlier TUI for bettercap.")
    p.add_argument("--host", default="127.0.0.1", help="bettercap REST host")
    p.add_argument("--port", type=int, default=8081, help="bettercap REST port")
    p.add_argument("-u", "--user", default="user", help="api.rest username")
    p.add_argument("-p", "--password", default="pass", help="api.rest password")
    p.add_argument("--https", action="store_true", help="use https")
    p.add_argument("--poll", type=float, default=2.0, help="refresh interval (s)")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    client = BettercapClient(
        host=args.host,
        port=args.port,
        username=args.user,
        password=args.password,
        scheme="https" if args.https else "http",
    )
    app = BetterTUI(client, poll=args.poll)
    try:
        app.run()
    finally:
        import asyncio

        asyncio.run(client.aclose())


if __name__ == "__main__":
    main()
