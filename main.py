import argparse
import json
import sys

from src.config import Settings
from src.instagram_client import InstagramAPIError, InstagramClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publicar conteúdo no Instagram via API oficial da Meta",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    image_parser = subparsers.add_parser("post-image", help="Publicar uma foto")
    image_parser.add_argument("--url", required=True, help="URL pública da imagem (JPEG)")
    image_parser.add_argument("--caption", default="", help="Legenda do post")

    reel_parser = subparsers.add_parser("post-reel", help="Publicar um Reel")
    reel_parser.add_argument("--url", required=True, help="URL pública do vídeo")
    reel_parser.add_argument("--caption", default="", help="Legenda do Reel")

    carousel_parser = subparsers.add_parser("post-carousel", help="Publicar carrossel")
    carousel_parser.add_argument(
        "--urls",
        required=True,
        nargs="+",
        help="URLs públicas das imagens/vídeos (2 a 10 itens)",
    )
    carousel_parser.add_argument("--caption", default="", help="Legenda do carrossel")

    subparsers.add_parser("limit", help="Ver limite de publicações nas últimas 24h")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        settings = Settings.from_env()
        client = InstagramClient(settings)

        if args.command == "post-image":
            client.post_image(args.url, args.caption or None)
        elif args.command == "post-reel":
            client.post_reel(args.url, args.caption or None)
        elif args.command == "post-carousel":
            client.post_carousel(args.urls, args.caption or None)
        elif args.command == "limit":
            limit = client.get_publishing_limit()
            print(json.dumps(limit, indent=2, ensure_ascii=False))
        else:
            parser.print_help()
            return 1

    except ValueError as exc:
        print(f"Configuração inválida: {exc}", file=sys.stderr)
        return 1
    except InstagramAPIError as exc:
        print(f"Erro da API do Instagram: {exc}", file=sys.stderr)
        if exc.payload:
            print(json.dumps(exc.payload, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
