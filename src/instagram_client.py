import time
from typing import Any

import requests

from src.config import Settings


class InstagramAPIError(Exception):
    def __init__(self, message: str, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.payload = payload or {}


class InstagramClient:
    POLL_INTERVAL_SECONDS = 5
    MAX_POLL_ATTEMPTS = 12

    def __init__(self, settings: Settings):
        self.settings = settings
        self.session = requests.Session()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.settings.base_url}/{path.lstrip('/')}"
        request_params = {"access_token": self.settings.access_token}
        if params:
            request_params.update(params)

        response = self.session.request(
            method=method,
            url=url,
            params=request_params,
            json=json_body,
            timeout=60,
        )

        try:
            payload = response.json()
        except ValueError as exc:
            raise InstagramAPIError(
                f"Resposta inválida da API ({response.status_code})",
                {"status_code": response.status_code, "text": response.text},
            ) from exc

        if not response.ok or "error" in payload:
            error = payload.get("error", {})
            message = error.get("message", response.text)
            raise InstagramAPIError(message, payload)

        return payload

    def create_image_container(
        self,
        image_url: str,
        caption: str | None = None,
        *,
        is_carousel_item: bool = False,
        alt_text: str | None = None,
    ) -> str:
        body: dict[str, Any] = {"image_url": image_url}
        if caption:
            body["caption"] = caption
        if is_carousel_item:
            body["is_carousel_item"] = True
        if alt_text:
            body["alt_text"] = alt_text

        payload = self._request(
            "POST",
            f"{self.settings.ig_user_id}/media",
            json_body=body,
        )
        return payload["id"]

    def create_video_container(
        self,
        video_url: str,
        *,
        caption: str | None = None,
        media_type: str = "REELS",
        is_carousel_item: bool = False,
        share_to_feed: bool = True,
    ) -> str:
        body: dict[str, Any] = {
            "video_url": video_url,
            "media_type": media_type,
        }
        if caption:
            body["caption"] = caption
        if is_carousel_item:
            body["is_carousel_item"] = True
        if media_type == "REELS":
            body["share_to_feed"] = share_to_feed

        payload = self._request(
            "POST",
            f"{self.settings.ig_user_id}/media",
            json_body=body,
        )
        return payload["id"]

    def create_carousel_container(
        self,
        children_ids: list[str],
        caption: str | None = None,
    ) -> str:
        if not 2 <= len(children_ids) <= 10:
            raise ValueError("Carrossel deve ter entre 2 e 10 itens")

        body: dict[str, Any] = {
            "media_type": "CAROUSEL",
            "children": ",".join(children_ids),
        }
        if caption:
            body["caption"] = caption

        payload = self._request(
            "POST",
            f"{self.settings.ig_user_id}/media",
            json_body=body,
        )
        return payload["id"]

    def get_container_status(self, container_id: str) -> str:
        payload = self._request(
            "GET",
            container_id,
            params={"fields": "status_code"},
        )
        return payload.get("status_code", "UNKNOWN")

    def wait_until_ready(self, container_id: str) -> None:
        for attempt in range(1, self.MAX_POLL_ATTEMPTS + 1):
            status = self.get_container_status(container_id)
            print(f"  Status do container: {status} (tentativa {attempt})")

            if status == "FINISHED":
                return
            if status in {"ERROR", "EXPIRED"}:
                raise InstagramAPIError(
                    f"Container falhou com status {status}",
                    {"container_id": container_id, "status": status},
                )
            if status == "PUBLISHED":
                return

            time.sleep(self.POLL_INTERVAL_SECONDS)

        raise InstagramAPIError(
            "Tempo esgotado aguardando processamento do container",
            {"container_id": container_id},
        )

    def publish(self, container_id: str) -> str:
        payload = self._request(
            "POST",
            f"{self.settings.ig_user_id}/media_publish",
            json_body={"creation_id": container_id},
        )
        return payload["id"]

    def get_publishing_limit(self) -> dict[str, Any]:
        return self._request(
            "GET",
            f"{self.settings.ig_user_id}/content_publishing_limit",
        )

    def post_image(self, image_url: str, caption: str | None = None) -> str:
        print("Criando container da imagem...")
        container_id = self.create_image_container(image_url, caption)
        print(f"Container criado: {container_id}")

        print("Aguardando processamento...")
        self.wait_until_ready(container_id)

        print("Publicando...")
        media_id = self.publish(container_id)
        print(f"Publicado com sucesso! Media ID: {media_id}")
        return media_id

    def post_reel(self, video_url: str, caption: str | None = None) -> str:
        print("Criando container do Reel...")
        container_id = self.create_video_container(
            video_url,
            caption=caption,
            media_type="REELS",
        )
        print(f"Container criado: {container_id}")

        print("Aguardando processamento do vídeo...")
        self.wait_until_ready(container_id)

        print("Publicando Reel...")
        media_id = self.publish(container_id)
        print(f"Reel publicado! Media ID: {media_id}")
        return media_id

    def post_carousel(
        self,
        media_urls: list[str],
        caption: str | None = None,
    ) -> str:
        children_ids: list[str] = []

        for index, url in enumerate(media_urls, start=1):
            print(f"Criando item {index}/{len(media_urls)} do carrossel...")
            lower_url = url.lower()
            if lower_url.endswith((".mp4", ".mov", ".avi", ".webm")):
                child_id = self.create_video_container(
                    url,
                    is_carousel_item=True,
                    media_type="VIDEO",
                )
            else:
                child_id = self.create_image_container(
                    url,
                    is_carousel_item=True,
                )
            children_ids.append(child_id)
            self.wait_until_ready(child_id)

        print("Montando carrossel...")
        carousel_id = self.create_carousel_container(children_ids, caption)
        self.wait_until_ready(carousel_id)

        print("Publicando carrossel...")
        media_id = self.publish(carousel_id)
        print(f"Carrossel publicado! Media ID: {media_id}")
        return media_id
