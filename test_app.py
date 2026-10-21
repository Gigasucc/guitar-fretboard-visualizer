from fastapi.testclient import TestClient

from app_final import APP_VERSION, TUNING_PRESETS, app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version():
    response = client.get("/version")
    assert response.status_code == 200
    assert response.json() == {"version": APP_VERSION, "app": "guitar-fretboard"}


def test_tunings_presets():
    response = client.get("/tunings")
    assert response.status_code == 200
    payload = response.json()
    assert payload["default"] == "standard"
    assert {"standard", "drop_d", "dadgad"}.issubset(payload["presets"])
    assert payload["presets"]["standard"]["strings"] == 6
    assert len(payload["presets"]["standard"]["notes"]) == 6
    assert len(TUNING_PRESETS) >= 3


def test_fretboard_standard_notes():
    response = client.get("/fretboard", params={"tuning": "standard", "frets": 12})
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["grid"]) == 6
    assert len(payload["grid"][0]) == 13
    assert payload["grid"][0][0]["note"] == "E"
    assert payload["grid"][0][5]["note"] == "A"
    assert payload["grid"][0][12]["note"] == "E"


def test_scale_c_major_pitch_classes():
    response = client.get(
        "/fretboard",
        params={
            "tuning": "E2,A2,D3,G3,B3,E4",
            "root": "C",
            "mode": "major",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert set(payload["scale_pitch_classes"]) == {0, 2, 4, 5, 7, 9, 11}
    assert any(cell["is_root"] for row in payload["grid"] for cell in row)


def test_note_position():
    response = client.get(
        "/note",
        params={"tuning": "E2,A2,D3,G3,B3,E4", "string": 0, "fret": 5},
    )
    assert response.status_code == 200
    assert response.json()["note"] == "A"
    assert response.json()["open_note"] == "E2"


def test_unknown_mode_returns_400():
    response = client.get("/fretboard", params={"root": "C", "mode": "banana"})
    assert response.status_code == 400
    assert "Unknown mode" in response.json()["detail"]


def test_invalid_tuning_returns_400():
    response = client.get("/fretboard", params={"tuning": "X2,Q3"})
    assert response.status_code == 400
    assert "Invalid tuning note" in response.json()["detail"]


def test_svg_endpoint():
    response = client.get(
        "/fretboard.svg",
        params={"tuning": "E2,A2,D3,G3,B3,E4", "root": "C"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert "<svg" in response.text
    assert "<circle" in response.text


def test_html_page_renders():
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<form" in response.text
    assert "<svg" in response.text
    assert "Guitar Fretboard Scale Visualizer" in response.text


def test_invalid_html_input_shows_page_error_not_json():
    response = client.get("/", params={"tuning": "X2,Q3"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Error:" in response.text
    assert "Invalid tuning note" in response.text


def test_invalid_fret_query_returns_400_not_422():
    response = client.get("/fretboard", params={"frets": "abc"})
    assert response.status_code == 400
    assert "frets must be an integer" in response.json()["detail"]
