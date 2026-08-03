"""情绪连续性：衰减、强度步长限制、熟悉度累计。"""

from __future__ import annotations

from modules.emotion import (
    DEFAULT_MOOD,
    INTENSITY_DECAY_PER_TURN,
    INTENSITY_FLOOR_RESET,
    MAX_INTENSITY_STEP,
)
from modules.emotion.schemas import ALLOWED_MOODS, EmotionState, MindState


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def decay_emotion(emotion: EmotionState) -> EmotionState:
    """无语义事件时的程序衰减；强度过低则回落平静。"""
    intensity = clamp01(emotion.intensity - INTENSITY_DECAY_PER_TURN)
    mood = emotion.mood if emotion.mood in ALLOWED_MOODS else DEFAULT_MOOD
    if intensity < INTENSITY_FLOOR_RESET and mood != DEFAULT_MOOD:
        mood = DEFAULT_MOOD
        intensity = max(intensity, 0.2)
    energy = clamp01(emotion.energy - 0.01)
    # 略微向中性收敛，避免 focus 永久钉死
    focus = emotion.focus
    if focus > 0.55:
        focus = clamp01(focus - 0.02)
    elif focus < 0.45:
        focus = clamp01(focus + 0.02)
    return EmotionState(mood=mood, intensity=intensity, energy=max(energy, 0.25), focus=focus)


def apply_emotion_delta(
    current: EmotionState,
    *,
    mood: str | None,
    intensity: float | None,
    energy: float | None = None,
    focus: float | None = None,
) -> EmotionState:
    """应用 Analyzer 建议，限制单次强度跳变。"""
    next_mood = current.mood
    if mood and mood in ALLOWED_MOODS:
        next_mood = mood

    next_intensity = current.intensity
    if intensity is not None:
        target = clamp01(intensity)
        delta = max(-MAX_INTENSITY_STEP, min(MAX_INTENSITY_STEP, target - current.intensity))
        next_intensity = clamp01(current.intensity + delta)

    next_energy = clamp01(energy) if energy is not None else current.energy
    next_focus = clamp01(focus) if focus is not None else current.focus
    return EmotionState(
        mood=next_mood,
        intensity=next_intensity,
        energy=next_energy,
        focus=next_focus,
    )


def bump_familiarity(state: MindState) -> None:
    rel = state.relationship
    rel.turn_count += 1
    # 约 40 轮接近「较熟」
    rel.familiarity = clamp01(rel.turn_count / 40.0)
