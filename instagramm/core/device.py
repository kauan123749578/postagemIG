"""Fingerprint Samsung SM-E045F — só no login novo (sem settings de 2FA)."""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("instagram.device")

BLOKS_VERSIONING_ID = "7189b949425f9bf80ea8bd880cf5a3080b292d9b1c4b38a18d112f7c4b71e7a8"

SAMSUNG_DEVICE: dict[str, Any] = {
    "app_version": "434.0.0.44.74",
    "android_version": 33,
    "android_release": "13",
    "dpi": "300dpi",
    "resolution": "720x1600",
    "manufacturer": "samsung",
    "device": "m04",
    "model": "SM-E045F",
    "cpu": "mt6765",
    "version_code": "996255552",
    "bloks_versioning_id": BLOKS_VERSIONING_ID,
}

SAMSUNG_USER_AGENT = (
    "Instagram 434.0.0.44.74 Android "
    "(33/13; 300dpi; 720x1600; samsung; SM-E045F; m04; mt6765; pt_BR; 996255552)"
)


def apply_samsung_device(cl) -> bool:
    """Aplica Samsung. NÃO chamar depois de set_settings no fluxo 2FA."""
    try:
        device = dict(SAMSUNG_DEVICE)
        if hasattr(cl, "set_device"):
            cl.set_device(device)
        else:
            cl.device_settings = dict(device)
        if hasattr(cl, "device_settings") and isinstance(cl.device_settings, dict):
            cl.device_settings["bloks_versioning_id"] = BLOKS_VERSIONING_ID
            cl.device_settings["app_version"] = device["app_version"]
            cl.device_settings["version_code"] = device["version_code"]
            cl.device_settings["model"] = device["model"]
            cl.device_settings["manufacturer"] = device["manufacturer"]
        if hasattr(cl, "bloks_versioning_id"):
            cl.bloks_versioning_id = BLOKS_VERSIONING_ID
        if hasattr(cl, "set_user_agent"):
            try:
                cl.set_user_agent(SAMSUNG_USER_AGENT)
            except TypeError:
                cl.user_agent = SAMSUNG_USER_AGENT
        else:
            cl.user_agent = SAMSUNG_USER_AGENT
        log.info("Device = Samsung SM-E045F (app %s)", device["app_version"])
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("Falha ao aplicar Samsung: %s", exc)
        return False
