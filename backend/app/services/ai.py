import json
import httpx

DEFAULT_MODELS = ["gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]

async def generate_titles(key: str, model: str, candidates: list[dict]) -> list[dict]:
    """Write optional clip copy for already-detected moments; Gemini never selects moments."""
    model = model if model in DEFAULT_MODELS else DEFAULT_MODELS[0]
    parts = [{"text": "Write concise, accurate short-video metadata for each already-detected gaming highlight. Use the provided frame and measured audio/chat evidence only. Do not infer a specific game, character, weapon, speech, or event when not visible. Return JSON only as {\"items\":[{\"index\":0,\"title\":\"...\",\"description\":\"...\",\"hashtags\":[\"#...\"]}]} ."}]
    for i, item in enumerate(candidates[:20]):
        parts.extend([{"text": f"Highlight {i}: time={item['timestamp']:.1f}s; score={item['score']}; category={item['category']}; signal={item['explanation']}"},
                      {"inline_data": {"mime_type": "image/jpeg", "data": item["frame"]}}])
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", headers={"x-goog-api-key": key}, json={"contents": [{"parts": parts}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3}})
        response.raise_for_status()
    text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text).get("items", [])

async def analyze_frames(key: str, model: str, frames: list[dict], duration: float, config: dict) -> list[dict]:
    model = model if model in DEFAULT_MODELS else DEFAULT_MODELS[0]
    prompt = f"Analyze these timestamped frames sampled from gameplay lasting {duration:.1f} seconds. Return JSON only: {{\"moments\":[{{\"timestamp\":number,\"score\":integer 0-100,\"category\":string,\"explanation\":string,\"title\":string,\"description\":string,\"hashtags\":[string]}}]}}. Find up to {config['count']} distinct engaging real events, only from enabled categories {config['categories']}. Write a concise, accurate short-video title and short description grounded only in visible evidence. Hashtags must be relevant and not claim game-specific facts the frames do not support. Do not invent speech, chat, sound, or events. Choose timestamps based only on visible evidence."
    parts = [{"text": prompt}]
    for f in frames[:24]:
        parts.extend([{"text": f"Frame at {f['time']:.2f} seconds:"}, {"inline_data": {"mime_type": "image/jpeg", "data": f["base64"]}}])
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", headers={"x-goog-api-key": key}, json={"contents": [{"parts": parts}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}})
        response.raise_for_status()
    text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    parsed = json.loads(text)
    return parsed.get("moments", [])

