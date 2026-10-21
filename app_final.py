"""FastAPI service with tuning presets and fretboard calculation."""
import re
import html
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

app = FastAPI(title="Guitar Fretboard Scale Visualizer", version="0.1.0")
NOTE_BASE_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
SHARPS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLATS = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
MODES = {"major": [0, 2, 4, 5, 7, 9, 11], "minor": [0, 2, 3, 5, 7, 8, 10],
         "pentatonic_major": [0, 2, 4, 7, 9], "pentatonic_minor": [0, 3, 5, 7, 10],
         "blues": [0, 3, 5, 6, 7, 10], "dorian": [0, 2, 3, 5, 7, 9, 10],
         "mixolydian": [0, 2, 4, 5, 7, 9, 10]}
TUNING_PRESETS = {"standard": "E2,A2,D3,G3,B3,E4", "drop_d": "D2,A2,D3,G3,B3,E4",
    "drop_c": "C2,G2,C3,F3,A3,D4", "dadgad": "D2,A2,D3,G3,A3,D4", "open_g": "D2,G2,D3,G3,B3,D4",
    "open_d": "D2,A2,D3,F#3,A3,D4", "half_step_down": "D#2,G#2,C#3,F#3,A#3,D#4",
    "bass_4": "E1,A1,D2,G2", "bass_5": "B0,E1,A1,D2,G2", "ukulele": "G4,C4,E4,A4"}
NOTE_RE = re.compile(r"^([A-Ga-g])([#b]?)(-?\d+)$")
ROOT_RE = re.compile(r"^([A-Ga-g])([#b]?)$")


def parse_tuning_note(value):
    match = NOTE_RE.fullmatch(value.strip())
    if not match:
        raise ValueError(f"Invalid tuning note '{value}'.")
    letter, accidental, octave_text = match.groups()
    pc = (NOTE_BASE_PC[letter.upper()] + (1 if accidental == "#" else -1 if accidental == "b" else 0)) % 12
    octave = int(octave_text)
    return {"display": f"{letter.upper()}{accidental}{octave}", "pitch_class": pc, "octave": octave}


def parse_tuning(value):
    value = TUNING_PRESETS.get(value.strip(), value.strip())
    if not value:
        raise ValueError("Tuning must not be empty.")
    parts = [part.strip() for part in value.split(",")]
    if any(not part for part in parts):
        raise ValueError("Tuning contains an empty note.")
    notes = [parse_tuning_note(part) for part in parts]
    if not 4 <= len(notes) <= 8:
        raise ValueError("Tuning must contain between 4 and 8 strings.")
    return notes


def parse_root(value):
    match = ROOT_RE.fullmatch(value.strip())
    if not match:
        raise ValueError(f"Invalid root note '{value}'.")
    letter, accidental = match.groups()
    return (NOTE_BASE_PC[letter.upper()] + (1 if accidental == "#" else -1 if accidental == "b" else 0)) % 12


def note_name(pc, notation):
    if notation not in {"sharps", "flats"}:
        raise ValueError("Notation must be 'sharps' or 'flats'.")
    return (SHARPS if notation == "sharps" else FLATS)[pc % 12]


def fretboard_data(tuning, root, mode, frets, notation):
    notes = parse_tuning(tuning)
    root_pc = parse_root(root)
    if mode not in MODES:
        raise ValueError(f"Unknown mode '{mode}'.")
    try:
        frets = int(frets)
    except (ValueError, TypeError):
        raise ValueError("frets must be an integer between 1 and 24.")
    if not 1 <= frets <= 24:
        raise ValueError("frets must be between 1 and 24.")
    scale = sorted({(root_pc + interval) % 12 for interval in MODES[mode]})
    grid = []
    for opened in notes:
        row = []
        for fret in range(frets + 1):
            pc = (opened["pitch_class"] + fret) % 12
            row.append({"fret": fret, "note": note_name(pc, notation), "pitch_class": pc,
                        "is_root": pc == root_pc, "in_scale": pc in scale})
        grid.append(row)
    return {"tuning": [note["display"] for note in notes], "root": note_name(root_pc, notation),
            "mode": mode, "frets": frets, "notation": notation, "scale_pitch_classes": scale,
            "root_pitch_class": root_pc, "grid": grid}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/version")
async def version():
    return {"version": "0.1.0", "app": "guitar-fretboard"}


@app.get("/tunings")
async def tunings():
    presets = {}
    for key, value in TUNING_PRESETS.items():
        notes = [parse_tuning_note(item)["display"] for item in value.split(",")]
        presets[key] = {"notes": notes, "strings": len(notes)}
    return {"default": "standard", "presets": presets}


@app.get("/fretboard")
async def fretboard(tuning: str = "E2,A2,D3,G3,B3,E4", root: str = "C", mode: str = "major",
                    frets: str = "12", notation: str = "sharps"):
    try:
        return fretboard_data(tuning, root, mode, frets, notation)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/note")
async def note_position(tuning: str = "E2,A2,D3,G3,B3,E4", string: str = "0", fret: str = "0", notation: str = "sharps"):
    try:
        notes = parse_tuning(tuning)
        string_index = int(string)
        fret_index = int(fret)
        if not 0 <= string_index < len(notes):
            raise ValueError("string is outside the tuning range.")
        if not 0 <= fret_index <= 24:
            raise ValueError("fret must be between 0 and 24.")
        pc = (notes[string_index]["pitch_class"] + fret_index) % 12
        return {"string": string_index, "fret": fret_index, "note": note_name(pc, notation),
                "pitch_class": pc, "open_note": notes[string_index]["display"]}
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def render_svg(data):
    string_count = len(data["grid"])
    margin_x, top, cell, spacing = 18, 29, 34, 22
    right = margin_x + cell * (data["frets"] + 1)
    width = right + margin_x
    height = top + spacing * (string_count - 1) + 20
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
             f'<rect width="{width}" height="{height}" fill="white"/>']
    for fret in range(data["frets"] + 1):
        x = margin_x + cell * (fret + 0.5)
        parts.append(f'<text x="{x}" y="16" font-family="monospace" font-size="9" text-anchor="middle">{fret}</text>')
        line_x = margin_x + cell * (fret + 1)
        parts.append(f'<line x1="{line_x}" y1="26" x2="{line_x}" y2="{height-17}" stroke="black" stroke-width="{3 if fret == 0 else 1}"/>')
    for index, row in enumerate(data["grid"]):
        y = top + (string_count - 1 - index) * spacing
        parts.append(f'<line x1="{margin_x}" y1="{y}" x2="{right}" y2="{y}" stroke="black" stroke-width="{max(0.8,2.5-index*0.25)}"/>')
        for note in row:
            x = margin_x + cell * (note["fret"] + 0.5)
            fill = "black" if note["is_root"] else "#d0d0d0" if note["in_scale"] else "white"
            parts.append(f'<circle cx="{x}" cy="{y}" r="8" fill="{fill}" stroke="black"/>')
            if note["in_scale"]:
                color = "white" if note["is_root"] else "black"
                parts.append(f'<text x="{x}" y="{y+3}" font-family="monospace" font-size="9" text-anchor="middle" fill="{color}">{html.escape(note["note"])}</text>')
    parts.append('</svg>')
    return ''.join(parts)


@app.get("/fretboard.svg")
async def fretboard_svg(tuning: str = "E2,A2,D3,G3,B3,E4", root: str = "C", mode: str = "major",
                       frets: str = "12", notation: str = "sharps"):
    try:
        data = fretboard_data(tuning, root, mode, frets, notation)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(content=render_svg(data), media_type="image/svg+xml; charset=utf-8")
