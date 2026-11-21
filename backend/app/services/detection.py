def normalize_moments(moments: list[dict], duration: float, config: dict) -> list[dict]:
    """Validate, score-filter, deduplicate, rank, and bound model suggestions."""
    cleaned = []
    threshold = {"relaxed": 72, "balanced": 58, "sensitive": 42}.get(config.get("sensitivity"), 58)
    clip_duration = int(config.get("duration", 45))
    for moment in moments:
        try:
            at = max(0.0, min(duration, float(moment["timestamp"])))
            score = max(0, min(100, int(moment["score"])))
            category = str(moment.get("category", "Action and combat"))[:80]
            if score < threshold or category not in config["categories"]:
                continue
            if any(abs(at - old["at"]) < min(clip_duration * .6, 20) for old in cleaned):
                continue
            start = max(0.0, at - 20)
            end = min(duration, max(start + 1, start + clip_duration))
            cleaned.append({"at": at, "start": start, "end": end, "score": score,
                "category": category, "title": str(moment.get("title") or "Gameplay highlight")[:160],
                "explanation": str(moment.get("explanation") or "")[:500],
                "description": str(moment.get("description") or moment.get("explanation") or "")[:2000],
                "hashtags": [str(tag)[:60] for tag in moment.get("hashtags", [])[:12] if isinstance(tag, str)]})
        except (ValueError, TypeError, KeyError):
            continue
    cleaned.sort(key=lambda value: value["score"], reverse=True)
    return cleaned[:int(config.get("count", 5))]

