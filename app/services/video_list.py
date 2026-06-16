import json


def parse_videos_json(videos_json: str) -> list[dict]:
    try:
        data = json.loads(videos_json or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []

    seen: set[str] = set()
    unique: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        url = (item.get("video_url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        cover = (item.get("cover_url") or "").strip()
        unique.append({"video_url": url, "cover_url": cover})
    return unique


def video_urls(videos_json: str) -> list[str]:
    return [v["video_url"] for v in parse_videos_json(videos_json)]


def normalize_video_payload(videos: list) -> list[dict]:
    result: list[dict] = []
    seen: set[str] = set()
    for item in videos:
        if hasattr(item, "model_dump"):
            data = item.model_dump()
        elif isinstance(item, dict):
            data = item
        else:
            continue
        url = (data.get("video_url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        cover = (data.get("cover_url") or "").strip()
        result.append({"video_url": url, "cover_url": cover})
    return result
