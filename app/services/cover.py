from app.services.instagram import InstagramAPIError


def resolve_cover_url(*sources: str | None, video_index: int | None = None) -> str:
    for source in sources:
        if source and str(source).strip():
            return str(source).strip()
    suffix = f" no vídeo {video_index}" if video_index else ""
    raise InstagramAPIError(
        f"Capa obrigatória{suffix}: configure a capa do lote ou a capa individual do vídeo"
    )


def require_batch_cover(cover_url: str | None, *, context: str = "lote") -> str:
    url = (cover_url or "").strip()
    if not url:
        raise ValueError(f"Capa do {context} é obrigatória")
    return url
