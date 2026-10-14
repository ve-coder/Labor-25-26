import json, random, time
from pathlib import Path

import pytest

from app import machine as mach
from app.camera import CameraManager
from app.config import Settings
from app.cube_model import CubeModel
from app.hardware import SimHardware
from app.vision import SimCamera


def make(tmp_path, **over):
    s = Settings(tmp_path / "settings.json")
    s.update({"sim_time_factor": 0.02, "cylinder_settle_ms": 0, "pause_between_moves_ms": 0,
              "stable_frames": 2, "enable_settle_ms": 0, **over})
    hw = SimHardware(s)
    cam = CameraManager(SimCamera(hw.bottom_colors, settings=s), s, fps=60)
    m = mach.Machine(s, hw, cam)
    mach.DATA_DIR = tmp_path
    m.stats = mach.Stats(tmp_path / "stats.json")
    return s, hw, cam, m


def run(m, program, timeout=60):
    m.start_program(program)
    m.thread.join(timeout)
    return m.status


def standard():
    return json.loads(mach.DEFAULT_PROGRAM_FILE.read_text())


@pytest.mark.parametrize("seed", range(5))
def test_standard_program_solves(tmp_path, seed):
    random.seed(seed)
    s, hw, cam, m = make(tmp_path)
    hw.insert_cube()
    assert not hw.cube.is_solved()
    status = run(m, standard())
    assert status == "fertig", m.error
    assert hw.cube.is_solved()
    assert all(v is False for v in hw.cyl_target.values())
    st = m.stats.summary()
    assert st["ok"] == 1 and st["avg_moves"] > 0
    cam.close()


def test_mirrored_camera(tmp_path):
    s, hw, cam, m = make(tmp_path, cam_mirror=True, cam_rotate="90")
    hw.insert_cube()
    assert run(m, standard()) == "fertig", m.error
    assert hw.cube.is_solved()
    cam.close()


def test_interlock_pair_with_fb(tmp_path):
    s, hw, cam, m = make(tmp_path)
    prog = {"blocks": [
        {"type": "cylinder", "target": "LR", "action": "extend"},
        {"type": "cylinder", "target": "FB", "action": "extend"},
        {"type": "pair", "angle": 90}]}
    assert run(m, prog) == "fehler"
    assert "verklemmen" in m.error
    cam.close()


def test_interlock_drop(tmp_path):
    s, hw, cam, m = make(tmp_path)
    prog = {"blocks": [
        {"type": "cylinder", "target": "D", "action": "extend"},
        {"type": "cylinder", "target": "LR", "action": "extend"},
        {"type": "cylinder", "target": "D", "action": "retract"},
        {"type": "cylinder", "target": "LR", "action": "retract"}]}
    assert run(m, prog) == "fehler"
    assert "fallen" in m.error
    cam.close()


def test_stop(tmp_path):
    s, hw, cam, m = make(tmp_path, sim_time_factor=0.5)
    hw.insert_cube()
    m.start_program(standard())
    time.sleep(1.0)
    m.stop()
    m.thread.join(10)
    assert m.status == "gestoppt"
    cam.close()


def test_home_catches_cube(tmp_path):
    s, hw, cam, m = make(tmp_path)
    prog = {"blocks": [
        {"type": "cylinder", "target": "D", "action": "extend"},
        {"type": "cylinder", "target": "LR", "action": "extend"},
        {"type": "cylinder", "target": "D", "action": "retract"},
        {"type": "home"}]}
    assert run(m, prog) == "fertig", m.error
    assert all(v is False for v in hw.cyl_target.values())
    cam.close()


def test_regrip_only_d_turns_whole_cube(tmp_path):
    """D allein dreht -> ganzer Würfel, Modell und simulierter Würfel bleiben gleich."""
    s, hw, cam, m = make(tmp_path)
    hw.insert_cube()
    before = hw.cube.facelets()
    prog = {"blocks": [
        {"type": "cylinder", "target": "D", "action": "extend"},
        {"type": "motor", "side": "D", "angle": 90, "speed": "regrip"},
        {"type": "cylinder", "target": "D", "action": "retract"}]}
    assert run(m, prog) == "fertig", m.error
    after = hw.cube.facelets()
    assert after["U"] != before["U"] or after["F"] != before["F"]
    # ganze Drehung um die senkrechte Achse
    assert after["R"] == before["F"]  # wie ein D-Zug: vorne wandert nach rechts
    cam.close()


def test_api_smoke(tmp_path, monkeypatch):
    monkeypatch.setenv("CUBESOLVER_DATA", str(tmp_path))
    from fastapi.testclient import TestClient
    from app import main
    with TestClient(main.app) as c:
        assert c.get("/api/state").json()["mode"] in ("sim", "pi")
        assert c.get("/api/programs").json()[0] == "standard"
        assert c.get("/api/programs/standard").json()["blocks"]
        r = c.put("/api/settings", json={"speed_solve": 999})
        assert r.status_code == 200
        assert c.put("/api/settings", json={"speed_solve": -5}).status_code == 400
        assert c.post("/api/manual/pair", json={"angle": 90}).status_code == 400
        assert c.get("/api/stats").json()["total"] >= 0
        assert c.get("/api/camera.jpg").status_code == 200


def test_scan_only_and_reference_dataset(tmp_path):
    import subprocess, sys
    s, hw, cam, m = make(tmp_path)
    hw.insert_cube()
    truth = hw.cube.copy()
    assert run(m, mach.load_program("nur_scannen")) == "fertig", m.error
    assert all(v is False for v in hw.cyl_target.values())
    assert sum(1 for st in m.model.stickers if st.rgb) == 54
    # Würfel liegt nach dem Scan wieder unten, erkannte Farben stimmen mit dem echten Würfel
    assert m.model.facelets() == hw.cube.facelets()
    # ein Feld absichtlich "korrigieren" -> Referenz speichern -> Auswertung zählt genau 1 Fehler
    face, idx = "F", 0
    real = m.model.face_stickers(face)[idx].color
    other = next(c for c in "WYROGB" if c != real)
    m.set_sticker(face, idx, other)
    r = m.save_reference("Test")
    assert r["corrected"] == 1
    ds = tmp_path / "dataset"
    for flag in ([], ["--resample"]):
        out = subprocess.run([sys.executable, "tools/eval_colors.py", "--json", "--dir", str(ds), *flag],
                             capture_output=True, text=True, check=True)
        res = json.loads(out.stdout)
        assert res["datasets"] == 1 and res["wrong"] == 1, res
    cam.close()
