"""Ponto de entrada do Postagem IG (app desktop com instagrapi)."""
from core.video_deps import bootstrap_video_deps
from ui.app import App


def main():
    bootstrap_video_deps()
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
