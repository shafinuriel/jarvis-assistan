"""Speaker ID — MFCC fingerprint. Personal / All mode."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

VOICE_DIR = Path(__file__).resolve().parent.parent / "memory" / "voiceprints"
VOICE_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_PATH = VOICE_DIR / "config.json"
OWNER_EMB_PATH = VOICE_DIR / "owner.npy"
DEFAULT_THRESHOLD = 0.80


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {"mode": "all", "threshold": DEFAULT_THRESHOLD}


def _save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def get_mode() -> str:
    return _load_config().get("mode", "all")


def set_mode(mode: str) -> str:
    mode = (
        "personal"
        if str(mode).lower() in ("personal", "person", "private", "мой", "personal voice")
        else "all"
    )
    cfg = _load_config()
    cfg["mode"] = mode
    _save_config(cfg)
    return mode


def has_owner_voice() -> bool:
    return OWNER_EMB_PATH.exists()


def _embed(audio: np.ndarray, sr: int = 16000) -> np.ndarray:
    import librosa

    y = np.asarray(audio, dtype=np.float32).flatten()
    if y.size < sr // 5:
        raise ValueError("too short")
    y = y - y.mean()
    y = y / (np.max(np.abs(y)) + 1e-8)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20)
    emb = mfcc.mean(axis=1)
    return (emb / (np.linalg.norm(emb) + 1e-8)).astype(np.float32)


def enroll_from_numpy(audio: np.ndarray, sample_rate: int = 16000) -> str:
    emb = _embed(audio, sample_rate)
    np.save(OWNER_EMB_PATH, emb)
    return "Голос владельца сохранён."


def verify_numpy(audio: np.ndarray, sample_rate: int = 16000) -> tuple[bool, float]:
    if get_mode() != "personal":
        return True, 1.0
    if not has_owner_voice():
        return False, 0.0
    try:
        emb = _embed(audio, sample_rate)
    except ValueError:
        return False, 0.0
    owner = np.load(OWNER_EMB_PATH)
    sim = float(np.dot(owner, emb))
    thr = float(_load_config().get("threshold", DEFAULT_THRESHOLD))
    return sim >= thr, sim