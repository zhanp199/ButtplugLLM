"""DeviceController — the single place that talks to hardware, and the single
place safety is enforced.

Every actuator command flows through here and is clamped to the configured
ceilings. Indefinite commands are watched by a deadman timer; timed commands and
patterns are driven by cancellable asyncio tasks. ``stop_all`` cancels everything
and is callable from any path (UI button, safe-word) without involving the LLM.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from buttplug import Client, WebsocketConnector

import config
from patterns import Pattern

logger = logging.getLogger("controller")

# Key identifying one actuator on one device.
Key = tuple[int, int]


class DeviceController:
    def __init__(
        self,
        intiface_url: str = config.INTIFACE_URL,
        max_intensity: float = config.MAX_INTENSITY,
        max_duration_ms: int = config.MAX_DURATION_MS,
        watchdog_timeout_s: float = config.WATCHDOG_TIMEOUT_S,
    ):
        self.intiface_url = intiface_url
        self.max_intensity = max_intensity
        self.max_duration_ms = max_duration_ms
        self.watchdog_timeout_s = watchdog_timeout_s

        self.client = Client("LLMToy")
        self._tasks: dict[Key, asyncio.Task] = {}  # timed / pattern tasks
        self._indefinite: dict[Key, float] = {}  # key -> last activity monotonic time
        self._lock = asyncio.Lock()
        self._watchdog: asyncio.Task | None = None
        self._connected = False

    # --- lifecycle ---------------------------------------------------------
    async def connect(self) -> None:
        connector = WebsocketConnector(self.intiface_url)
        await self.client.connect(connector)
        self._connected = True
        logger.info("Connected to Intiface at %s", self.intiface_url)
        try:
            await self.client.start_scanning()
        except Exception as e:  # scanning is best-effort
            logger.warning("start_scanning failed: %s", e)
        self._watchdog = asyncio.create_task(self._watchdog_loop())

    async def disconnect(self) -> None:
        await self.stop_all()
        if self._watchdog:
            self._watchdog.cancel()
        try:
            if self.client.connected:
                await self.client.disconnect()
        except Exception:
            pass
        self._connected = False

    async def scan(self, seconds: float = 4.0) -> None:
        await self.client.start_scanning()
        await asyncio.sleep(seconds)
        try:
            await self.client.stop_scanning()
        except Exception:
            pass

    # --- introspection -----------------------------------------------------
    def _device(self, index: int):
        dev = self.client.devices.get(index)
        if dev is None:
            raise ValueError(f"No device with index {index}")
        return dev

    def list_devices(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for idx, dev in self.client.devices.items():
            out.append(
                {
                    "index": idx,
                    "name": dev.name,
                    "vibrate_actuators": [
                        {"index": a.index, "description": a.description,
                         "step_count": a.step_count}
                        for a in dev.actuators
                    ],
                    "linear_actuators": [
                        {"index": a.index, "description": a.description}
                        for a in dev.linear_actuators
                    ],
                    "rotatory_actuators": [
                        {"index": a.index, "description": a.description}
                        for a in dev.rotatory_actuators
                    ],
                }
            )
        return out

    def status(self) -> dict[str, Any]:
        return {
            "connected": self._connected and self.client.connected,
            "intiface_url": self.intiface_url,
            "device_count": len(self.client.devices),
            "active": [
                {"device": d, "actuator": a} for (d, a) in self._indefinite
            ]
            + [{"device": d, "actuator": a} for (d, a) in self._tasks],
            "limits": {
                "max_intensity": self.max_intensity,
                "max_duration_ms": self.max_duration_ms,
                "watchdog_timeout_s": self.watchdog_timeout_s,
            },
        }

    # --- safety helpers ----------------------------------------------------
    def _clamp_i(self, intensity: float) -> float:
        return max(0.0, min(self.max_intensity, float(intensity)))

    def _clamp_d(self, duration_ms: int) -> int:
        return max(0, min(self.max_duration_ms, int(duration_ms)))

    async def _cancel(self, key: Key) -> None:
        task = self._tasks.pop(key, None)
        if task:
            task.cancel()
        self._indefinite.pop(key, None)

    def _untrack(self, key: Key) -> None:
        """Remove this task's tracking entry, but only if it is still the current
        one. A new command may have already replaced it (await self._cancel +
        create_task); without this identity check the cancelled old task's finally
        would delete the *new* task's entry, orphaning it (untrackable by
        stop_all, and able to resume after a stop)."""
        if self._tasks.get(key) is asyncio.current_task():
            self._tasks.pop(key, None)

    async def _set_vibrate(self, device: int, actuator: int, speed: float) -> None:
        dev = self._device(device)
        acts = dev.actuators
        if actuator < 0 or actuator >= len(acts):
            raise ValueError(f"Device {device} has no vibrate actuator {actuator}")
        await acts[actuator].command(self._clamp_i(speed))

    # --- commands ----------------------------------------------------------
    async def vibrate(
        self, device: int, actuator: int = 0, intensity: float = 0.5,
        duration_ms: int | None = None,
    ) -> dict[str, Any]:
        intensity = self._clamp_i(intensity)
        key: Key = (device, actuator)
        async with self._lock:
            await self._cancel(key)
            await self._set_vibrate(device, actuator, intensity)
            if duration_ms is None or intensity == 0.0:
                if intensity > 0.0:
                    self._indefinite[key] = time.monotonic()
            else:
                d = self._clamp_d(duration_ms)
                self._tasks[key] = asyncio.create_task(
                    self._timed_stop(key, d / 1000.0)
                )
        return {"ok": True, "device": device, "actuator": actuator,
                "intensity": intensity, "duration_ms": duration_ms}

    async def _timed_stop(self, key: Key, seconds: float) -> None:
        try:
            await asyncio.sleep(seconds)
            await self._set_vibrate(key[0], key[1], 0.0)
        except asyncio.CancelledError:
            pass
        finally:
            self._untrack(key)

    async def run_pattern(
        self, device: int, actuator: int, pattern: Pattern
    ) -> dict[str, Any]:
        key: Key = (device, actuator)
        async with self._lock:
            await self._cancel(key)
            self._tasks[key] = asyncio.create_task(
                self._run_pattern_task(key, pattern)
            )
        return {"ok": True, "device": device, "actuator": actuator,
                "pattern": pattern.name, "estimated_ms": pattern.total_ms()}

    async def _run_pattern_task(self, key: Key, pattern: Pattern) -> None:
        try:
            for _ in range(pattern.loop + 1):
                for step in pattern.steps:
                    s = step.clamped(self.max_intensity, self.max_duration_ms)
                    await self._set_vibrate(key[0], key[1], s.intensity)
                    await asyncio.sleep(s.duration_ms / 1000.0)
            await self._set_vibrate(key[0], key[1], 0.0)
        except asyncio.CancelledError:
            pass
        finally:
            self._untrack(key)

    async def linear_move(
        self, device: int, actuator: int, position: float, duration_ms: int = 1000
    ) -> dict[str, Any]:
        dev = self._device(device)
        acts = dev.linear_actuators
        if actuator < 0 or actuator >= len(acts):
            raise ValueError(f"Device {device} has no linear actuator {actuator}")
        position = max(0.0, min(1.0, float(position)))
        d = self._clamp_d(duration_ms)
        await acts[actuator].command(d, position)
        return {"ok": True, "device": device, "actuator": actuator,
                "position": position, "duration_ms": d}

    async def rotate(
        self, device: int, actuator: int, speed: float, clockwise: bool = True
    ) -> dict[str, Any]:
        dev = self._device(device)
        acts = dev.rotatory_actuators
        if actuator < 0 or actuator >= len(acts):
            raise ValueError(f"Device {device} has no rotatory actuator {actuator}")
        speed = self._clamp_i(speed)
        key: Key = (device, actuator)
        async with self._lock:
            await self._cancel(key)
            await acts[actuator].command(speed, bool(clockwise))
            if speed > 0.0:
                self._indefinite[key] = time.monotonic()
        return {"ok": True, "device": device, "actuator": actuator,
                "speed": speed, "clockwise": clockwise}

    async def stop_device(self, device: int) -> dict[str, Any]:
        async with self._lock:
            for key in [k for k in self._tasks if k[0] == device]:
                await self._cancel(key)
            for key in [k for k in self._indefinite if k[0] == device]:
                self._indefinite.pop(key, None)
            try:
                await self._device(device).stop()
            except Exception as e:
                logger.warning("stop_device(%s) failed: %s", device, e)
        return {"ok": True, "device": device}

    async def stop_all(self) -> dict[str, Any]:
        async with self._lock:
            for key in list(self._tasks):
                await self._cancel(key)
            self._indefinite.clear()
            try:
                await self.client.stop_all()
            except Exception as e:
                logger.warning("stop_all failed: %s", e)
        logger.info("stop_all executed")
        return {"ok": True}

    # --- watchdog ----------------------------------------------------------
    async def _watchdog_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(1.0)
                if not (self._connected and self.client.connected):
                    # connection lost -> make sure nothing keeps running locally
                    self._indefinite.clear()
                    continue
                now = time.monotonic()
                expired = [
                    key for key, ts in self._indefinite.items()
                    if now - ts > self.watchdog_timeout_s
                ]
                for key in expired:
                    logger.warning("watchdog stopping idle actuator %s", key)
                    self._indefinite.pop(key, None)
                    try:
                        await self._set_vibrate(key[0], key[1], 0.0)
                    except Exception:
                        pass
        except asyncio.CancelledError:
            pass
