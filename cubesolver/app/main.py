"""Webserver: REST-API, WebSocket für Live-Daten, Kamera-Stream, Oberfläche.

Start:  python -m app.main            (Simulation, Port 8000)
        CUBESOLVER_MODE=pi python -m app.main
"""
from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import machine as mach
from .camera import CameraManager
from .config import Settings
from .hardware import SIDES, PiHardware, SimHardware
from .vision import PiCamera, SimCamera

STATIC = Path(__file__).resolve().parent.parent / "static"


class Hub:
    """Verteilt Ereignisse an alle verbundenen Browser."""

    def __init__(self):
        self.clients: set[asyncio.Queue] = set()
        self.loop: asyncio.AbstractEventLoop | None = None

    def emit(self, ev: dict):
        if self.loop is None:
            return
        for q in list(self.clients):
            self.loop.call_soon_threadsafe(_put, q, ev)


def _put(q, ev):
    if q.qsize() < 500:
        q.put_nowait(ev)


hub = Hub()
ctx: dict = {}


def build():
    settings = Settings()
    startup_error = None
    hw = cam = None
    if settings["mode"] == "pi":
        try:
            hw = PiHardware(settings)
        except Exception as e:
            startup_error = f"Hardware nicht erreichbar ({e}) – läuft in Simulation"
        if hw is not None:
            try:
                cam = PiCamera(settings["cam_width"], settings["cam_height"], settings["cam_fixed_exposure"])
            except Exception as e:
                startup_error = f"Kamera nicht erreichbar ({e}) – Kamerabild simuliert"
                cam = SimCamera(lambda: None, settings["cam_width"], settings["cam_height"], settings)
    if hw is None:
        hw = SimHardware(settings)
    if cam is None:
        cam = SimCamera(getattr(hw, "bottom_colors", lambda: None), settings["cam_width"], settings["cam_height"], settings)
    cam_mgr = CameraManager(cam, settings)
    m = mach.Machine(settings, hw, cam_mgr, emit=hub.emit)
    if startup_error:
        m.log(startup_error, "error")
    return settings, hw, cam_mgr, m, startup_error


@asynccontextmanager
async def lifespan(app: FastAPI):
    hub.loop = asyncio.get_running_loop()
    settings, hw, cam_mgr, m, err = build()
    ctx.update(settings=settings, hw=hw, cam=cam_mgr, m=m, startup_error=err)
    task = asyncio.create_task(_ticker())
    yield
    task.cancel()
    m.stop()
    cam_mgr.close()
    hw.close()


app = FastAPI(title="Cube-Solver", lifespan=lifespan)


async def _ticker():
    """Schickt 5x pro Sekunde den Maschinenzustand an alle Browser."""
    while True:
        await asyncio.sleep(0.2)
        if hub.clients:
            try:
                snap = await run_in_threadpool(ctx["m"].snapshot)
                hub.emit({"type": "state", **snap})
            except Exception as e:
                print("state error", e)


async def _call(fn, *args):
    try:
        return await run_in_threadpool(fn, *args)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, str(e))


def M() -> mach.Machine:
    return ctx["m"]


# ===================================================================== Seiten
@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")


# ===================================================================== Zustand
@app.get("/api/state")
async def state():
    snap = await run_in_threadpool(M().snapshot)
    snap["startup_error"] = ctx.get("startup_error")
    return snap


@app.get("/api/cube")
async def cube():
    return M().model.to_json()


@app.get("/api/log")
async def log():
    return M().log_lines


# ===================================================================== Einstellungen
@app.get("/api/settings")
async def get_settings():
    return ctx["settings"].schema()


@app.put("/api/settings")
async def put_settings(changes: dict):
    try:
        ctx["settings"].update(changes)
    except Exception as e:
        raise HTTPException(400, str(e))
    M().log("Einstellungen gespeichert")
    return ctx["settings"].schema()


# ===================================================================== Programme
@app.get("/api/programs")
async def programs():
    return mach.list_programs()


@app.get("/api/programs/{name}")
async def get_program(name: str):
    try:
        return mach.load_program(name)
    except FileNotFoundError:
        raise HTTPException(404, "Programm nicht gefunden")


@app.put("/api/programs/{name}")
async def put_program(name: str, program: dict):
    try:
        mach.save_program(name, program)
    except Exception as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.delete("/api/programs/{name}")
async def delete_program(name: str):
    p = mach.PROGRAM_DIR / f"{name}.json"
    if p.exists():
        p.unlink()
    return {"ok": True}


# ===================================================================== Ablauf
@app.post("/api/run")
async def run(body: dict):
    program = body.get("program")
    if program is None:
        program = mach.load_program(body.get("name", "standard"))
    hw = ctx["hw"]
    if isinstance(hw, SimHardware) and (hw.cube is None or hw.cube.is_solved()):
        hw.insert_cube()
        M().log(f"Simulation: neuer Würfel eingelegt ({hw.scramble_text})")
    await _call(M().start_program, program)
    return {"ok": True}


@app.post("/api/stop")
async def stop():
    M().stop()
    return {"ok": True}


@app.post("/api/step_mode")
async def step_mode(body: dict):
    M().set_step_mode(bool(body.get("on")))
    return {"ok": True}


@app.post("/api/next")
async def next_step():
    M().next_step()
    return {"ok": True}


@app.post("/api/home")
async def home():
    m = M()
    m.manual_guard()
    await _call(m.go_home)
    return {"ok": True}


# ===================================================================== Handbetrieb
@app.post("/api/manual/cylinder")
async def manual_cylinder(body: dict):
    await _call(M().manual_cylinder, body["cyl"], bool(body["extended"]))
    return {"ok": True}


@app.post("/api/manual/jog")
async def manual_jog(body: dict):
    side = body["side"]
    if side not in SIDES:
        raise HTTPException(400, "Unbekannter Motor")
    await _call(M().manual_jog, side, int(body["steps"]), body.get("speed"))
    return {"ok": True}


@app.post("/api/manual/pair")
async def manual_pair(body: dict):
    await _call(M().manual_pair, int(body.get("angle", 90)))
    return {"ok": True}


@app.post("/api/manual/beep")
async def manual_beep(body: dict):
    ctx["hw"].beep(body.get("pattern", "kurz"))
    return {"ok": True}


@app.post("/api/manual/interlocks")
async def manual_interlocks(body: dict):
    m = M()
    m.manual_guard()
    m.interlocks = bool(body.get("on", True))
    m.log("Sicherheitsprüfungen " + ("an" if m.interlocks else "AUS – Vorsicht!"), "info" if m.interlocks else "warn")
    return {"ok": True}


# ===================================================================== Würfel
@app.post("/api/cube/sticker")
async def cube_sticker(body: dict):
    face, index, color = body["face"], int(body["index"]), body["color"]
    if color not in ("W", "Y", "R", "O", "G", "B"):
        raise HTTPException(400, "Ungültige Farbe")
    M().set_sticker(face, index, color)
    return {"ok": True}


@app.post("/api/cube/reset")
async def cube_reset():
    await _call(M().reset_model)
    return {"ok": True}


@app.post("/api/cube/solve_preview")
async def solve_preview():
    """Lösung aus dem aktuellen Modell berechnen (ohne Ausführen)."""
    await _call(M().compute_solution)
    return {"text": M().solution_text}


@app.post("/api/cube/reference")
async def cube_reference(body: dict | None = None):
    """Aktuellen Scan (mit Korrekturen) als Referenz für die Farberkennung speichern."""
    return await _call(M().save_reference, (body or {}).get("note", ""))


@app.get("/api/cube/detail")
async def cube_detail():
    """Alle 54 Sticker mit Messwert, automatisch erkannter und aktueller Farbe."""
    out = []
    for st in M().model.stickers:
        out.append({"id": st.id, "pos": st.pos, "normal": st.normal, "rgb": st.rgb,
                    "auto": getattr(st, "auto_color", None), "color": st.color,
                    "manual": bool(getattr(st, "manual", False))})
    return out


# ===================================================================== Simulation
@app.post("/api/sim/insert")
async def sim_insert():
    hw = ctx["hw"]
    if not isinstance(hw, SimHardware):
        raise HTTPException(400, "Nur in der Simulation")
    M().manual_guard()
    text = hw.insert_cube()
    M().log(f"Simulation: neuer Würfel eingelegt ({text})")
    return {"scramble": text}


@app.post("/api/sim/remove")
async def sim_remove():
    hw = ctx["hw"]
    if not isinstance(hw, SimHardware):
        raise HTTPException(400, "Nur in der Simulation")
    hw.remove_cube()
    return {"ok": True}


@app.get("/api/sim/truth")
async def sim_truth():
    hw = ctx["hw"]
    if not isinstance(hw, SimHardware) or hw.cube is None:
        return {}
    return hw.cube.to_json()


# ===================================================================== Statistik
@app.get("/api/stats")
async def stats():
    return M().stats.summary()


@app.delete("/api/stats")
async def stats_clear():
    M().stats.clear()
    return {"ok": True}


# ===================================================================== Kamera
@app.get("/api/camera.jpg")
async def camera_jpg():
    return Response(ctx["cam"].jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/api/camera.mjpg")
async def camera_mjpg():
    async def gen():
        last = None
        while True:
            jpg = ctx["cam"].jpeg
            if jpg and jpg is not last:
                last = jpg
                yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n"
            await asyncio.sleep(0.1)

    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")


# ===================================================================== WebSocket
@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    q: asyncio.Queue = asyncio.Queue()
    hub.clients.add(q)
    try:
        m = M()
        await websocket.send_text(json.dumps({"type": "cube", **m.model.to_json()}))
        await websocket.send_text(json.dumps({"type": "loghistory", "lines": m.log_lines[-100:]}))
        while True:
            ev = await q.get()
            await websocket.send_text(json.dumps(ev, default=str))
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        hub.clients.discard(q)


def main():
    import uvicorn

    port = int(os.environ.get("CUBESOLVER_PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="warning")


if __name__ == "__main__":
    main()
