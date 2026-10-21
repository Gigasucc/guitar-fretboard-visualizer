"""Guitar Fretboard Scale Visualizer: HTML UI, JSON API and SVG rendering."""

from __future__ import annotations

import html
import logging
from contextlib import asynccontextmanager
import os
import re
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

APP_VERSION = os.getenv("APP_VERSION", "0.1.0").strip() or "0.1.0"
LOG_LEVEL_NAME = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"
LOG_LEVEL = getattr(logging, LOG_LEVEL_NAME, logging.INFO)
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("guitar-fretboard")

NOTE_BASE_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
SHARP_NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_NOTES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

MODES: dict[str, list[int]] = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "pentatonic_major": [0, 2, 4, 7, 9],
    "pentatonic_minor": [0, 3, 5, 7, 10],
    "blues": [0, 3, 5, 6, 7, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
}
MODE_LABELS = {
    "major": "Major",
    "minor": "Minor",
    "pentatonic_major": "Major pentatonic",
    "pentatonic_minor": "Minor pentatonic",
    "blues": "Blues",
    "dorian": "Dorian",
    "mixolydian": "Mixolydian",
}

TUNING_PRESETS: dict[str, str] = {
    "standard": "E2,A2,D3,G3,B3,E4",
    "drop_d": "D2,A2,D3,G3,B3,E4",
    "drop_c": "C2,G2,C3,F3,A3,D4",
    "dadgad": "D2,A2,D3,G3,A3,D4",
    "open_g": "D2,G2,D3,G3,B3,D4",
    "open_d": "D2,A2,D3,F#3,A3,D4",
    "half_step_down": "D#2,G#2,C#3,F#3,A#3,D#4",
    "bass_4": "E1,A1,D2,G2",
    "bass_5": "B0,E1,A1,D2,G2",
    "ukulele": "G4,C4,E4,A4",
}

TUNING_NOTE_RE = re.compile(r"^([A-Ga-g])([#b]?)(-?\d+)$")
ROOT_NOTE_RE = re.compile(r"^([A-Ga-g])([#b]?)$")


class InputValidationError(ValueError):
    """A user-provided query parameter did not pass validation."""


def invalid(message: str) -> None:
    logger.warning("Validation error: %s", message)
    raise InputValidationError(message)


def note_name(pitch_class: int, notation: str) -> str:
    names = SHARP_NOTES if notation == "sharps" else FLAT_NOTES
    return names[pitch_class % 12]


def parse_tuning_note(value: str) -> dict[str, Any]:
    match = TUNING_NOTE_RE.fullmatch(value.strip())
    if not match:
        invalid(f"Invalid tuning note '{value}'. Use a note such as E2, F#3 or Bb2.")

    letter, accidental, octave_text = match.groups()
    letter = letter.upper()
    pitch_class = (NOTE_BASE_PC[letter] + (1 if accidental == "#" else -1 if accidental == "b" else 0)) % 12
    octave = int(octave_text)
    display = f"{letter}{accidental}{octave}"
    return {
        "display": display,
        "pitch_class": pitch_class,
        "octave": octave,
        "absolute": octave * 12 + pitch_class,
    }


def parse_tuning(value: str) -> list[dict[str, Any]]:
    raw = value.strip()
    if not raw:
        invalid("Tuning must not be empty.")
    raw = TUNING_PRESETS.get(raw, raw)
    parts = [part.strip() for part in raw.split(",")]
    if any(not part for part in parts):
        invalid("Tuning contains an empty note. Separate valid notes with commas.")

    notes = [parse_tuning_note(part) for part in parts]
    if not 4 <= len(notes) <= 8:
        invalid("Tuning must contain between 4 and 8 strings.")
    return notes


def parse_root(value: str) -> int:
    match = ROOT_NOTE_RE.fullmatch(value.strip())
    if not match:
        invalid(f"Invalid root note '{value}'. Use one note such as C, F# or Bb.")
    letter, accidental = match.groups()
    letter = letter.upper()
    return (NOTE_BASE_PC[letter] + (1 if accidental == "#" else -1 if accidental == "b" else 0)) % 12


def validate_notation(notation: str) -> str:
    if notation not in {"sharps", "flats"}:
        invalid("Notation must be either 'sharps' or 'flats'.")
    return notation


def parse_int(value: str | int, name: str, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        invalid(f"{name} must be an integer between {minimum} and {maximum}.")
    if not minimum <= parsed <= maximum:
        invalid(f"{name} must be between {minimum} and {maximum}.")
    return parsed


def _load_default_tuning() -> str:
    configured = os.getenv("DEFAULT_TUNING", TUNING_PRESETS["standard"]).strip()
    if not configured:
        configured = TUNING_PRESETS["standard"]
    try:
        notes = parse_tuning(configured)
    except InputValidationError:
        logger.warning("Invalid DEFAULT_TUNING environment value; using standard tuning.")
        notes = parse_tuning(TUNING_PRESETS["standard"])
    return ",".join(note["display"] for note in notes)


def _load_default_root() -> str:
    configured = os.getenv("DEFAULT_ROOT", "C").strip() or "C"
    try:
        pitch_class = parse_root(configured)
        return note_name(pitch_class, "sharps")
    except InputValidationError:
        logger.warning("Invalid DEFAULT_ROOT environment value; using C.")
        return "C"


def _load_default_mode() -> str:
    configured = os.getenv("DEFAULT_MODE", "major").strip()
    if configured not in MODES:
        logger.warning("Invalid DEFAULT_MODE environment value; using major.")
        return "major"
    return configured


def _load_default_frets() -> int:
    configured = os.getenv("DEFAULT_FRETS", "12").strip()
    try:
        return parse_int(configured, "DEFAULT_FRETS", 1, 24)
    except InputValidationError:
        logger.warning("Invalid DEFAULT_FRETS environment value; using 12.")
        return 12


def _load_default_notation() -> str:
    configured = os.getenv("NOTATION", "sharps").strip()
    if configured not in {"sharps", "flats"}:
        logger.warning("Invalid NOTATION environment value; using sharps.")
        return "sharps"
    return configured


DEFAULT_TUNING = _load_default_tuning()
DEFAULT_ROOT = _load_default_root()
DEFAULT_MODE = _load_default_mode()
DEFAULT_FRETS = _load_default_frets()
DEFAULT_NOTATION = _load_default_notation()


@asynccontextmanager
async def lifespan(application: FastAPI):
    logger.info("Starting guitar-fretboard version=%s default_tuning=%s", APP_VERSION, DEFAULT_TUNING)
    yield


app = FastAPI(
    title="Guitar Fretboard Scale Visualizer",
    description="Visualize musical scales on a guitar or bass fretboard.",
    version=APP_VERSION,
    lifespan=lifespan,
)


@app.middleware("http")
async def log_unhandled_exceptions(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        logger.exception("Unhandled exception while processing %s", request.url.path)
        raise


def build_fretboard_data(
    tuning: str,
    root: str,
    mode: str,
    frets_value: str | int,
    notation: str,
) -> dict[str, Any]:
    validated_notation = validate_notation(notation)
    tuning_notes = parse_tuning(tuning)
    root_pc = parse_root(root)
    if mode not in MODES:
        invalid(f"Unknown mode '{mode}'. Choose one of: {', '.join(MODES)}.")
    frets = parse_int(frets_value, "frets", 1, 24)

    scale_pitch_classes = sorted({(root_pc + interval) % 12 for interval in MODES[mode]})
    scale_set = set(scale_pitch_classes)
    grid: list[list[dict[str, Any]]] = []

    for open_note in tuning_notes:
        row: list[dict[str, Any]] = []
        for fret in range(frets + 1):
            pitch_class = (open_note["pitch_class"] + fret) % 12
            row.append(
                {
                    "fret": fret,
                    "note": note_name(pitch_class, validated_notation),
                    "pitch_class": pitch_class,
                    "is_root": pitch_class == root_pc,
                    "in_scale": pitch_class in scale_set,
                }
            )
        grid.append(row)

    return {
        "tuning": [note["display"] for note in tuning_notes],
        "root": note_name(root_pc, validated_notation),
        "mode": mode,
        "frets": frets,
        "notation": validated_notation,
        "scale_pitch_classes": scale_pitch_classes,
        "root_pitch_class": root_pc,
        "grid": grid,
    }


def render_svg(data: dict[str, Any]) -> str:
    # Each fret is a cell; the open-string note gets its own cell to the left of the nut.
    margin_x = 18
    margin_top = 29
    margin_bottom = 20
    cell_width = 34
    string_spacing = 22
    radius = 8
    string_count = len(data["grid"])
    frets = data["frets"]
    board_right = margin_x + cell_width * (frets + 1)
    width = board_right + margin_x
    height = margin_top + string_spacing * (string_count - 1) + margin_bottom

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" aria-label="Fretboard for '
        f'{html.escape(data["root"], quote=True)} {html.escape(data["mode"], quote=True)} scale">',
        f'<title>{html.escape(data["root"])} {html.escape(data["mode"])} fretboard</title>',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="white"/>',
    ]

    for fret in range(frets + 1):
        x = margin_x + cell_width * (fret + 0.5)
        parts.append(
            f'<text x="{x:.1f}" y="16" font-family="monospace" font-size="9" '
            f'text-anchor="middle" fill="black">{fret}</text>'
        )

    for fret in range(frets + 1):
        x = margin_x + cell_width * (fret + 1)
        stroke_width = 3 if fret == 0 else 1
        parts.append(
            f'<line x1="{x}" y1="{margin_top - 3}" x2="{x}" '
            f'y2="{height - margin_bottom + 3}" stroke="black" stroke-width="{stroke_width}"/>'
        )

    for string_index in range(string_count):
        y = margin_top + (string_count - 1 - string_index) * string_spacing
        stroke_width = max(0.8, 2.5 - string_index * 0.25)
        parts.append(
            f'<line x1="{margin_x}" y1="{y}" x2="{board_right}" y2="{y}" '
            f'stroke="black" stroke-width="{stroke_width:.2f}"/>'
        )

    for string_index, row in enumerate(data["grid"]):
        y = margin_top + (string_count - 1 - string_index) * string_spacing
        for cell in row:
            fret = cell["fret"]
            x = margin_x + cell_width * (fret + 0.5)
            if cell["is_root"]:
                fill, text_fill = "black", "white"
            elif cell["in_scale"]:
                fill, text_fill = "#d0d0d0", "black"
            else:
                fill, text_fill = "white", "black"
            parts.append(
                f'<circle cx="{x:.1f}" cy="{y}" r="{radius}" fill="{fill}" '
                f'stroke="black" stroke-width="1"/>'
            )
            if cell["in_scale"]:
                label = html.escape(cell["note"], quote=True)
                parts.append(
                    f'<text x="{x:.1f}" y="{y + 3.2:.1f}" font-family="monospace" '
                    f'font-size="9" text-anchor="middle" fill="{text_fill}">{label}</text>'
                )

    parts.append("</svg>")
    return "".join(parts)


def _log_board_request(path: str, tuning: str, root: str, mode: str, frets: str | int) -> None:
    logger.info("Request path=%s tuning=%s root=%s mode=%s frets=%s", path, tuning, root, mode, frets)


def html_page(
    tuning: str,
    root: str,
    mode: str,
    frets: str | int,
    notation: str,
    *,
    error: str | None = None,
    data: dict[str, Any] | None = None,
) -> str:
    safe_tuning = html.escape(tuning, quote=True)
    safe_frets = html.escape(str(frets), quote=True)
    safe_root_pc: int | None
    try:
        safe_root_pc = parse_root(root)
    except InputValidationError:
        safe_root_pc = parse_root(DEFAULT_ROOT)
    display_notation = notation if notation in {"sharps", "flats"} else DEFAULT_NOTATION

    root_options = []
    for pitch_class in range(12):
        value = note_name(pitch_class, display_notation)
        selected = " selected" if pitch_class == safe_root_pc else ""
        root_options.append(
            f'<option value="{html.escape(value, quote=True)}"{selected}>{html.escape(value)}</option>'
        )

    mode_options = []
    chosen_mode = mode if mode in MODES else DEFAULT_MODE
    for mode_key, label in MODE_LABELS.items():
        selected = " selected" if mode_key == chosen_mode else ""
        mode_options.append(
            f'<option value="{mode_key}"{selected}>{html.escape(label)}</option>'
        )

    notation_options = []
    for notation_key, label in (("sharps", "Sharps (C#)"), ("flats", "Flats (Db)")):
        selected = " selected" if notation_key == display_notation else ""
        notation_options.append(
            f'<option value="{notation_key}"{selected}>{label}</option>'
        )

    error_html = ""
    if error:
        error_html = f'<p class="error" role="alert">Error: {html.escape(error)}</p>'
    svg_html = render_svg(data) if data is not None else ""
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Guitar Fretboard Scale Visualizer</title>
  <style>
    body {{ max-width: 1100px; margin: 2rem auto; padding: 0 1rem; color: #111; font-family: system-ui, sans-serif; }}
    form {{ display: flex; flex-wrap: wrap; align-items: end; gap: 0.8rem; margin: 1rem 0; }}
    label {{ display: grid; gap: 0.3rem; font-size: 0.95rem; }}
    input, select, button {{ padding: 0.45rem; font: inherit; }}
    input[name="tuning"], input[name="frets"] {{ font-family: monospace; }}
    input[name="tuning"] {{ width: min(28rem, 80vw); }}
    .error {{ padding: 0.7rem; border: 1px solid #555; background: #f5f5f5; }}
    .svg-wrap {{ max-width: 100%; overflow-x: auto; border: 1px solid #777; padding: 0.5rem; }}
    .svg-wrap svg {{ display: block; max-width: 100%; height: auto; }}
    footer {{ margin-top: 1.5rem; }}
  </style>
</head>
<body>
  <h1>Guitar Fretboard Scale Visualizer</h1>
  <p>Задайте строй по струнам, выберите тональность — увидите гриф с подсвеченными нотами.</p>
  {error_html}
  <form method="get" action="/">
    <label>Строй (от низкой струны к высокой)
      <input name="tuning" value="{safe_tuning}" required>
    </label>
    <label>Тоника
      <select name="root">{''.join(root_options)}</select>
    </label>
    <label>Лад / гамма
      <select name="mode">{''.join(mode_options)}</select>
    </label>
    <label>Количество ладов
      <input type="number" name="frets" min="1" max="24" value="{safe_frets}" required>
    </label>
    <label>Обозначение нот
      <select name="notation">{''.join(notation_options)}</select>
    </label>
    <button type="submit">Показать</button>
  </form>
  <div class="svg-wrap">{svg_html}</div>
  <footer><a href="/docs">API: /docs</a></footer>
</body>
</html>"""


def api_bad_request(exc: InputValidationError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
async def version() -> dict[str, str]:
    return {"version": APP_VERSION, "app": "guitar-fretboard"}


@app.get("/tunings")
async def tunings() -> dict[str, Any]:
    presets = {}
    for key, value in TUNING_PRESETS.items():
        notes = [parse_tuning_note(note.strip())["display"] for note in value.split(",")]
        presets[key] = {"notes": notes, "strings": len(notes)}
    return {"default": "standard", "presets": presets}


@app.get("/fretboard")
async def fretboard(
    tuning: str = DEFAULT_TUNING,
    root: str = DEFAULT_ROOT,
    mode: str = DEFAULT_MODE,
    frets: str = str(DEFAULT_FRETS),
    notation: str = DEFAULT_NOTATION,
) -> dict[str, Any]:
    _log_board_request("/fretboard", tuning, root, mode, frets)
    try:
        return build_fretboard_data(tuning, root, mode, frets, notation)
    except InputValidationError as exc:
        raise api_bad_request(exc) from exc


@app.get("/note")
async def note_position(
    tuning: str = DEFAULT_TUNING,
    string: str = "0",
    fret: str = "0",
    notation: str = DEFAULT_NOTATION,
) -> dict[str, Any]:
    _log_board_request("/note", tuning, "-", "-", fret)
    try:
        validated_notation = validate_notation(notation)
        tuning_notes = parse_tuning(tuning)
        string_index = parse_int(string, "string", 0, len(tuning_notes) - 1)
        fret_index = parse_int(fret, "fret", 0, 24)
        open_note = tuning_notes[string_index]
        pitch_class = (open_note["pitch_class"] + fret_index) % 12
        return {
            "string": string_index,
            "fret": fret_index,
            "note": note_name(pitch_class, validated_notation),
            "pitch_class": pitch_class,
            "open_note": open_note["display"],
        }
    except InputValidationError as exc:
        raise api_bad_request(exc) from exc


@app.get("/fretboard.svg")
async def fretboard_svg(
    tuning: str = DEFAULT_TUNING,
    root: str = DEFAULT_ROOT,
    mode: str = DEFAULT_MODE,
    frets: str = str(DEFAULT_FRETS),
    notation: str = DEFAULT_NOTATION,
) -> Response:
    _log_board_request("/fretboard.svg", tuning, root, mode, frets)
    try:
        data = build_fretboard_data(tuning, root, mode, frets, notation)
    except InputValidationError as exc:
        raise api_bad_request(exc) from exc
    svg = render_svg(data)
    return Response(content=svg, media_type="image/svg+xml; charset=utf-8")


@app.get("/", response_class=HTMLResponse)
async def home(
    tuning: str | None = None,
    root: str | None = None,
    mode: str | None = None,
    frets: str | None = None,
    notation: str | None = None,
) -> HTMLResponse:
    tuning_value = DEFAULT_TUNING if tuning is None else tuning
    root_value = DEFAULT_ROOT if root is None else root
    mode_value = DEFAULT_MODE if mode is None else mode
    frets_value = str(DEFAULT_FRETS) if frets is None else frets
    notation_value = DEFAULT_NOTATION if notation is None else notation
    _log_board_request("/", tuning_value, root_value, mode_value, frets_value)

    error: str | None = None
    try:
        data = build_fretboard_data(
            tuning_value, root_value, mode_value, frets_value, notation_value
        )
    except InputValidationError as exc:
        error = str(exc)
        try:
            data = build_fretboard_data(
                DEFAULT_TUNING, DEFAULT_ROOT, DEFAULT_MODE, DEFAULT_FRETS, DEFAULT_NOTATION
            )
        except InputValidationError:
            # Environment values were checked during startup; this is defensive only.
            logger.exception("Could not render the default fretboard")
            data = None
    page = html_page(
        tuning_value,
        root_value,
        mode_value,
        frets_value,
        notation_value,
        error=error,
        data=data,
    )
    return HTMLResponse(content=page, status_code=200)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception for %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
