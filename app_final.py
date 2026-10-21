"""FastAPI service with tuning presets and note parsing."""
import re
from fastapi import FastAPI, HTTPException

app = FastAPI(title="Guitar Fretboard Scale Visualizer", version="0.1.0")
NOTE_BASE_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
TUNING_PRESETS = {
    "standard": "E2,A2,D3,G3,B3,E4", "drop_d": "D2,A2,D3,G3,B3,E4",
    "drop_c": "C2,G2,C3,F3,A3,D4", "dadgad": "D2,A2,D3,G3,A3,D4",
    "open_g": "D2,G2,D3,G3,B3,D4", "open_d": "D2,A2,D3,F#3,A3,D4",
    "half_step_down": "D#2,G#2,C#3,F#3,A#3,D#4", "bass_4": "E1,A1,D2,G2",
    "bass_5": "B0,E1,A1,D2,G2", "ukulele": "G4,C4,E4,A4",
}
NOTE_RE = re.compile(r"^([A-Ga-g])([#b]?)(-?\d+)$")
SHARPS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


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
