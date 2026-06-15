import time
from dataclasses import dataclass
from typing import Any

import requests

INSTAGRAM_CAPTION_MAX = 2200

META_ERROR_HINTS: dict[int, str] = {
    2207076: (
        "Instagram não conseguiu processar o vídeo. Use MP4 (H.264 + AAC), "
        "máx. ~100MB, URL pública acessível. Arquivos .mov podem falhar — converta para MP4."
    ),
    2207027: "Vídeo muito longo ou formato não suportado para Reels.",
    36003: "Erro de permissão ou token expirado na API da Meta.",
}


def humanize_instagram_error(message: str, payload: dict | None = None) -> str:
    payload = payload or {}
    error = payload.get("error", payload)
    code = error.get("code") if isinstance(error, dict) else None
    subcode = error.get("error_subcode") if isinstance(error, dict) else None
    lookup = subcode or code
    if lookup in META_ERROR_HINTS:
        return f"{message} — {META_ERROR_HINTS[lookup]}"
    if "2207076" in message:
        return f"{message} — {META_ERROR_HINTS[2207076]}"
    return message


class InstagramAPIError(Exception):
    def __init__(self, message: str, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.payload = payload or {}


@dataclass
class AccountCredentials:
    ig_user_id: str
    access_token: str
    graph_api_version: str = "v21.0"
    graph_host: str = "graph.facebook.com"
    proxy_url: str = ""

    @property
    def base_url(self) -> str:
        return f"https://{self.graph_host}/{self.graph_api_version}"


class InstagramClient:
    POLL_INTERVAL_SECONDS = 5
    MAX_POLL_ATTEMPTS = 24

    def __init__(self, creds: AccountCredentials):
        self.creds = creds
        self.session = requests.Session()
        if creds.proxy_url:
            self.session.proxies.update({
                "http": creds.proxy_url,
                "https": creds.proxy_url,
            })

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.creds.base_url}/{path.lstrip('/')}"
        request_params = {"access_token": self.creds.access_token}
        if params:
            request_params.update(params)

        response = self.session.request(
            method=method,
            url=url,
            params=request_params,
            json=json_body,
            timeout=120,
        )

        try:
            payload = response.json()
        except ValueError as exc:
            raise InstagramAPIError(
                f"Resposta inválida ({response.status_code})",
                {"status_code": response.status_code, "text": response.text},
            ) from exc

        if not response.ok or "error" in payload:
            error = payload.get("error", {})
            raw_message = error.get("message", response.text)
            raise InstagramAPIError(humanize_instagram_error(raw_message, payload), payload)

        return payload

    @staticmethod
    def normalize_caption(caption: str | None) -> str | None:
        if not caption:
            return None
        trimmed = caption.strip()
        if not trimmed:
            return None
        return trimmed[:INSTAGRAM_CAPTION_MAX]

    def get_profile(self) -> dict[str, Any]:
        return self._request(
            "GET",
            self.creds.ig_user_id,
            params={"fields": "username,name,profile_picture_url,followers_count,media_count"},
        )

    def get_account_insights(self) -> dict[str, Any]:
        metrics = "impressions,reach,profile_views"
        try:
            return self._request(
                "GET",
                f"{self.creds.ig_user_id}/insights",
                params={"metric": metrics, "period": "day"},
            )
        except InstagramAPIError:
            return self._request(
                "GET",
                f"{self.creds.ig_user_id}/insights",
                params={"metric": "reach,profile_views", "period": "day"},
            )

    def get_media_insights(self, media_id: str) -> dict[str, Any]:
        for metrics in ("plays,reach,impressions", "reach,impressions", "impressions"):
            try:
                return self._request(
                    "GET",
                    f"{media_id}/insights",
                    params={"metric": metrics},
                )
            except InstagramAPIError:
                continue
        return {"data": []}

    def get_publishing_limit(self) -> dict[str, Any]:
        return self._request(
            "GET",
            f"{self.creds.ig_user_id}/content_publishing_limit",
        )

    def create_image_container(
        self,
        image_url: str,
        caption: str | None = None,
        *,
        is_carousel_item: bool = False,
    ) -> str:
        body: dict[str, Any] = {"image_url": image_url}
        if caption:
            body["caption"] = self.normalize_caption(caption)
        if is_carousel_item:
            body["is_carousel_item"] = True
        return self._request("POST", f"{self.creds.ig_user_id}/media", json_body=body)["id"]

    def create_video_container(
        self,
        video_url: str,
        *,
        caption: str | None = None,
        media_type: str = "REELS",
        is_carousel_item: bool = False,
        cover_url: str | None = None,
        thumb_offset: int | None = None,
        share_to_feed: bool = True,
        audio_name: str | None = None,
    ) -> str:
        body: dict[str, Any] = {"video_url": video_url, "media_type": media_type}
        if caption:
            body["caption"] = self.normalize_caption(caption)
        if is_carousel_item:
            body["is_carousel_item"] = True
        if cover_url:
            body["cover_url"] = cover_url
        if thumb_offset is not None:
            body["thumb_offset"] = thumb_offset
        if audio_name and media_type == "REELS":
            body["audio_name"] = audio_name.strip()[:100]
        if media_type == "REELS":
            body["share_to_feed"] = share_to_feed
        return self._request("POST", f"{self.creds.ig_user_id}/media", json_body=body)["id"]

    def create_carousel_container(self, children_ids: list[str], caption: str | None = None) -> str:
        body: dict[str, Any] = {
            "media_type": "CAROUSEL",
            "children": ",".join(children_ids),
        }
        if caption:
            body["caption"] = self.normalize_caption(caption)
        return self._request("POST", f"{self.creds.ig_user_id}/media", json_body=body)["id"]

    def get_container_status(self, container_id: str) -> str:
        payload = self._request("GET", container_id, params={"fields": "status_code,status"})
        return payload.get("status_code", "UNKNOWN")

    def get_container_details(self, container_id: str) -> dict[str, Any]:
        return self._request("GET", container_id, params={"fields": "status_code,status"})

    def wait_until_ready(self, container_id: str) -> None:
        for _ in range(self.MAX_POLL_ATTEMPTS):
            details = self.get_container_details(container_id)
            status = details.get("status_code", "UNKNOWN")
            if status == "FINISHED":
                return
            if status in {"ERROR", "EXPIRED"}:
                detail = details.get("status", status)
                raise InstagramAPIError(detail, details)
            if status == "PUBLISHED":
                return
            time.sleep(self.POLL_INTERVAL_SECONDS)
        raise InstagramAPIError("Timeout aguardando processamento do container")

    def publish(self, container_id: str) -> str:
        return self._request(
            "POST",
            f"{self.creds.ig_user_id}/media_publish",
            json_body={"creation_id": container_id},
        )["id"]

    def post_image(self, image_url: str, caption: str | None = None) -> str:
        container_id = self.create_image_container(image_url, caption)
        self.wait_until_ready(container_id)
        return self.publish(container_id)

    def post_reel(
        self,
        video_url: str,
        caption: str | None = None,
        *,
        cover_url: str | None = None,
        thumb_offset: int | None = None,
        audio_name: str | None = None,
    ) -> str:
        container_id = self.create_video_container(
            video_url,
            caption=caption,
            media_type="REELS",
            cover_url=cover_url,
            thumb_offset=thumb_offset,
            audio_name=audio_name,
        )
        self.wait_until_ready(container_id)
        return self.publish(container_id)

    def create_story_container(
        self,
        *,
        image_url: str | None = None,
        video_url: str | None = None,
    ) -> str:
        if not image_url and not video_url:
            raise ValueError("Story precisa de imagem ou vídeo")
        body: dict[str, Any] = {"media_type": "STORIES"}
        if image_url:
            body["image_url"] = image_url
        if video_url:
            body["video_url"] = video_url
        return self._request("POST", f"{self.creds.ig_user_id}/media", json_body=body)["id"]

    def post_story(self, *, image_url: str | None = None, video_url: str | None = None) -> str:
        container_id = self.create_story_container(image_url=image_url, video_url=video_url)
        self.wait_until_ready(container_id)
        return self.publish(container_id)

    def post_carousel(self, media_urls: list[str], caption: str | None = None) -> str:
        children: list[str] = []
        for url in media_urls:
            lower = url.lower()
            if lower.endswith((".mp4", ".mov", ".avi", ".webm")):
                child = self.create_video_container(url, is_carousel_item=True, media_type="VIDEO")
            else:
                child = self.create_image_container(url, is_carousel_item=True)
            children.append(child)
            self.wait_until_ready(child)
        carousel_id = self.create_carousel_container(children, caption)
        self.wait_until_ready(carousel_id)
        return self.publish(carousel_id)


def client_from_account(account) -> InstagramClient:
    return InstagramClient(
        AccountCredentials(
            ig_user_id=account.ig_user_id,
            access_token=account.access_token,
            graph_api_version=account.graph_api_version,
            graph_host=account.graph_host,
            proxy_url=account.proxy_url or "",
        )
    )
