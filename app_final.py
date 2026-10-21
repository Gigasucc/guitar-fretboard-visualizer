"""Initial FastAPI project skeleton."""
from fastapi import FastAPI

app = FastAPI(title="Guitar Fretboard Scale Visualizer", version="0.1.0")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/version")
async def version():
    return {"version": "0.1.0", "app": "guitar-fretboard"}
