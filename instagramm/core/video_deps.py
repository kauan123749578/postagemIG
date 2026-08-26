"""Configura ffmpeg para publicar vídeos — essencial no .exe (PyInstaller)."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from core.config import LOCAL_FFMPEG

_BOOTSTRAPPED = False


def resolve_ffmpeg_exe() -> str:
    """Localiza o ffmpeg empacotado ou do sistema."""
    # 1) ffmpeg.exe ao lado do programa (prioridade — o que o usuário colocou na pasta)
    if LOCAL_FFMPEG.is_file():
        os.environ["IMAGEIO_FFMPEG_EXE"] = str(LOCAL_FFMPEG)
        return str(LOCAL_FFMPEG)

    env = os.environ.get("IMAGEIO_FFMPEG_EXE", "").strip()
    if env and Path(env).is_file():
        return env

    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if Path(exe).is_file():
            os.environ["IMAGEIO_FFMPEG_EXE"] = exe
            return exe
    except Exception:
        pass

    # Fallback no executável PyInstaller (onedir)
    if getattr(sys, "frozen", False):
        bases = [
            Path(getattr(sys, "_MEIPASS", "")),
            Path(sys.executable).resolve().parent / "_internal",
        ]
        for base in bases:
            if not base.is_dir():
                continue
            for candidate in sorted(base.rglob("ffmpeg-win*.exe")):
                if candidate.is_file():
                    os.environ["IMAGEIO_FFMPEG_EXE"] = str(candidate)
                    return str(candidate)

    raise RuntimeError(
        "ffmpeg não encontrado. Use uma versão atualizada do Postagem IG ou informe uma capa (imagem) no vídeo."
    )


def bootstrap_video_deps() -> None:
    """Chame no início do app para garantir ffmpeg disponível."""
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    resolve_ffmpeg_exe()
    _BOOTSTRAPPED = True


def make_video_thumbnail(video_path: str | Path) -> Path:
    """Gera capa JPG via ffmpeg (não depende de MoviePy)."""
    bootstrap_video_deps()
    video_path = Path(video_path)
    ffmpeg = resolve_ffmpeg_exe()

    ss = 1.0
    try:
        from instagrapi.utils.video import read_video_metadata

        meta = read_video_metadata(video_path)
        ss = max(0.1, min(meta.duration / 2, max(meta.duration - 0.1, 0.1)))
    except Exception:
        pass

    fd, tmp = tempfile.mkstemp(suffix=".jpg", prefix="postagemig_thumb_")
    os.close(fd)
    thumb = Path(tmp)
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{ss:.3f}",
        "-i",
        str(video_path),
        "-vframes",
        "1",
        "-q:v",
        "2",
        str(thumb),
    ]
    proc = subprocess.run(cmd, capture_output=True, timeout=180)
    if proc.returncode != 0 or not thumb.is_file() or thumb.stat().st_size == 0:
        err = proc.stderr.decode(errors="ignore").strip() or "erro desconhecido"
        raise RuntimeError(err)
    return thumb


def strip_video_metadata(video_path: str | Path, *, dest: Path | None = None) -> Path:
    """Gera cópia do vídeo sem metadados/chapters (stream copy, sem reencode).

    Equivalente a:
      ffmpeg -y -i video.mp4 -map_metadata -1 -map_chapters -1 -c:v copy -c:a copy limpo.mp4
    """
    bootstrap_video_deps()
    src = Path(video_path)
    if not src.is_file():
        raise FileNotFoundError(f"Vídeo não encontrado: {src}")

    ffmpeg = resolve_ffmpeg_exe()
    if dest is None:
        fd, tmp = tempfile.mkstemp(suffix=src.suffix or ".mp4", prefix="postagemig_clean_")
        os.close(fd)
        out = Path(tmp)
    else:
        out = Path(dest)
        out.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(src),
        "-map_metadata",
        "-1",
        "-map_chapters",
        "-1",
        "-c:v",
        "copy",
        "-c:a",
        "copy",
        str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, timeout=600)
    if proc.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
        if out.is_file():
            try:
                out.unlink()
            except OSError:
                pass
        err = proc.stderr.decode(errors="ignore").strip() or "erro desconhecido"
        raise RuntimeError(f"Falha ao limpar metadados: {err}")
    return out
