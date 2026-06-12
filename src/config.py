import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    access_token: str
    ig_user_id: str
    graph_api_version: str = "v21.0"
    graph_host: str = "graph.facebook.com"

    @property
    def base_url(self) -> str:
        return f"https://{self.graph_host}/{self.graph_api_version}"

    @classmethod
    def from_env(cls) -> "Settings":
        access_token = os.getenv("ACCESS_TOKEN", "").strip()
        ig_user_id = os.getenv("IG_USER_ID", "").strip()

        if not access_token:
            raise ValueError("ACCESS_TOKEN não configurado no arquivo .env")
        if not ig_user_id:
            raise ValueError("IG_USER_ID não configurado no arquivo .env")

        return cls(
            access_token=access_token,
            ig_user_id=ig_user_id,
            graph_api_version=os.getenv("GRAPH_API_VERSION", "v21.0").strip(),
            graph_host=os.getenv("GRAPH_HOST", "graph.facebook.com").strip(),
        )
