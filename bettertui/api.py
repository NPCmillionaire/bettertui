"""Async client for the bettercap REST API (the `api.rest` module).

bettercap exposes a small HTTP API when the `api.rest` module is on:

    GET  /api/session            -> full session state (hosts, modules, env, ...)
    POST /api/session {"cmd":..} -> run a command, same as typing in the REPL
    GET  /api/events             -> recent events (newest last)
    DELETE /api/events           -> clear the event buffer

Auth is HTTP Basic, using api.rest.username / api.rest.password.

This module keeps zero bettercap-specific logic beyond the transport and a
handful of light parsers. The TUI drives everything through `run()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx


class BettercapError(Exception):
    """Raised when the API returns an error or cannot be reached."""


@dataclass
class Host:
    ip: str = ""
    mac: str = ""
    name: str = ""
    vendor: str = ""
    alive: bool = True
    first_seen: str = ""
    last_seen: str = ""

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "Host":
        return cls(
            ip=d.get("ipv4", "") or d.get("ip", ""),
            mac=d.get("mac", ""),
            name=d.get("hostname", "") or d.get("name", ""),
            vendor=d.get("vendor", ""),
            alive=d.get("alive", True),
            first_seen=d.get("first_seen", ""),
            last_seen=d.get("last_seen", ""),
        )


@dataclass
class Module:
    name: str = ""
    running: bool = False

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "Module":
        return cls(name=d.get("name", ""), running=bool(d.get("running", False)))


@dataclass
class Event:
    time: str = ""
    tag: str = ""
    message: str = ""

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "Event":
        # bettercap event shapes vary by tag; pull a human string out of each.
        msg = d.get("message")
        if not msg:
            data = d.get("data")
            if isinstance(data, dict):
                msg = data.get("message") or data.get("Message") or ""
            elif isinstance(data, str):
                msg = data
            else:
                msg = ""
        return cls(time=d.get("time", ""), tag=d.get("tag", ""), message=str(msg))


@dataclass
class Session:
    """A light snapshot of the pieces of /api/session the TUI renders."""

    hosts: list[Host] = field(default_factory=list)
    modules: list[Module] = field(default_factory=list)
    iface: str = ""
    gateway: str = ""
    version: str = ""

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "Session":
        lan = d.get("lan") or {}
        hosts = [Host.from_json(h) for h in (lan.get("hosts") or [])]
        modules = [Module.from_json(m) for m in (d.get("modules") or [])]
        iface = (d.get("interface") or {}).get("ipv4", "")
        gateway = (d.get("gateway") or {}).get("ipv4", "")
        return cls(
            hosts=hosts,
            modules=modules,
            iface=iface,
            gateway=gateway,
            version=d.get("version", ""),
        )


class BettercapClient:
    """Thin async wrapper around the bettercap REST API."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8081,
        username: str = "user",
        password: str = "pass",
        scheme: str = "http",
        timeout: float = 5.0,
    ) -> None:
        self.base = f"{scheme}://{host}:{port}"
        self._client = httpx.AsyncClient(
            base_url=self.base,
            auth=(username, password),
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str) -> Any:
        try:
            resp = await self._client.get(path)
        except httpx.HTTPError as e:
            raise BettercapError(f"cannot reach bettercap at {self.base}: {e}") from e
        if resp.status_code == 401:
            raise BettercapError("401 unauthorized — check api.rest username/password")
        if resp.status_code >= 400:
            raise BettercapError(f"{path} -> HTTP {resp.status_code}")
        return resp.json()

    async def session(self) -> Session:
        return Session.from_json(await self._get("/api/session"))

    async def events(self) -> list[Event]:
        data = await self._get("/api/events")
        if not isinstance(data, list):
            return []
        return [Event.from_json(e) for e in data]

    async def clear_events(self) -> None:
        try:
            await self._client.delete("/api/events")
        except httpx.HTTPError:
            pass

    async def run(self, cmd: str) -> None:
        """Run a bettercap command (e.g. "net.probe on")."""
        try:
            resp = await self._client.post("/api/session", json={"cmd": cmd})
        except httpx.HTTPError as e:
            raise BettercapError(f"command failed: {e}") from e
        if resp.status_code >= 400:
            raise BettercapError(f'"{cmd}" -> HTTP {resp.status_code}: {resp.text[:200]}')
