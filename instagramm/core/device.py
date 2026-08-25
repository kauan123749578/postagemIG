"""Pool de fingerprints Android — um modelo por conta (fixo após o login).

Samsung SM-E045F permanece (já validado no Meta).
Contas novas recebem modelo diferente; 2FA/sessão salva NÃO troca device.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("instagram.device")

BLOKS_VERSIONING_ID = "7189b949425f9bf80ea8bd880cf5a3080b292d9b1c4b38a18d112f7c4b71e7a8"

APP_VERSION = "434.0.0.44.74"
VERSION_CODE = "996255552"


def _dev(
    *,
    key: str,
    label: str,
    manufacturer: str,
    device: str,
    model: str,
    cpu: str,
    dpi: str = "300dpi",
    resolution: str = "720x1600",
    android_version: int = 33,
    android_release: str = "13",
) -> dict[str, Any]:
    ua = (
        f"Instagram {APP_VERSION} Android "
        f"({android_version}/{android_release}; {dpi}; {resolution}; "
        f"{manufacturer}; {model}; {device}; {cpu}; pt_BR; {VERSION_CODE})"
    )
    return {
        "key": key,
        "label": label,
        "app_version": APP_VERSION,
        "android_version": android_version,
        "android_release": android_release,
        "dpi": dpi,
        "resolution": resolution,
        "manufacturer": manufacturer,
        "device": device,
        "model": model,
        "cpu": cpu,
        "version_code": VERSION_CODE,
        "bloks_versioning_id": BLOKS_VERSIONING_ID,
        "user_agent": ua,
    }


# Ordem = preferência de atribuição em contas novas (Samsung primeiro, já validado)
DEVICE_POOL: list[dict[str, Any]] = [
    _dev(
        key="samsung_m04",
        label="Samsung Galaxy F04 (SM-E045F)",
        manufacturer="samsung",
        device="m04",
        model="SM-E045F",
        cpu="mt6765",
    ),
    _dev(
        key="motorola_g54",
        label="Motorola Moto G54",
        manufacturer="motorola",
        device="cancun",
        model="moto g54 5G",
        cpu="mt6833",
        dpi="400dpi",
        resolution="1080x2400",
        android_version=34,
        android_release="14",
    ),
    _dev(
        key="xiaomi_redmi_12",
        label="Xiaomi Redmi 12",
        manufacturer="Xiaomi",
        device="fire",
        model="23053RN02A",
        cpu="mt6768",
        dpi="400dpi",
        resolution="1080x2400",
        android_version=33,
        android_release="13",
    ),
    _dev(
        key="realme_c55",
        label="Realme C55",
        manufacturer="realme",
        device="RMX3710",
        model="RMX3710",
        cpu="mt6789",
        dpi="400dpi",
        resolution="1080x2400",
        android_version=33,
        android_release="13",
    ),
    _dev(
        key="samsung_a15",
        label="Samsung Galaxy A15",
        manufacturer="samsung",
        device="a15",
        model="SM-A155F",
        cpu="mt6835",
        dpi="450dpi",
        resolution="1080x2340",
        android_version=34,
        android_release="14",
    ),
    _dev(
        key="motorola_e13",
        label="Motorola Moto E13",
        manufacturer="motorola",
        device="maine",
        model="moto e13",
        cpu="unisoc",
        dpi="280dpi",
        resolution="720x1600",
        android_version=33,
        android_release="13",
    ),
]

DEVICE_BY_KEY = {d["key"]: d for d in DEVICE_POOL}

# Compat: fingerprint Samsung original
SAMSUNG_DEVICE = {k: v for k, v in DEVICE_BY_KEY["samsung_m04"].items() if k not in ("key", "label", "user_agent")}
SAMSUNG_USER_AGENT = DEVICE_BY_KEY["samsung_m04"]["user_agent"]


def get_device_profile(key: str | None) -> dict[str, Any]:
    if key and key in DEVICE_BY_KEY:
        return dict(DEVICE_BY_KEY[key])
    return dict(DEVICE_BY_KEY["samsung_m04"])


def device_key_from_settings(settings: dict | None) -> str:
    """Infere a chave do pool a partir dos settings da sessão."""
    if not isinstance(settings, dict):
        return ""
    ds = settings.get("device_settings") or {}
    if not isinstance(ds, dict):
        return ""
    model = str(ds.get("model") or "").strip()
    manufacturer = str(ds.get("manufacturer") or "").strip().lower()
    device = str(ds.get("device") or "").strip().lower()
    for prof in DEVICE_POOL:
        if model and model == prof["model"]:
            return prof["key"]
        if device and device == str(prof["device"]).lower() and manufacturer == str(prof["manufacturer"]).lower():
            return prof["key"]
    return ""


def used_device_keys_from_accounts(accounts: list) -> list[str]:
    """Lista keys já usadas (campo device_key ou sessão)."""
    used: list[str] = []
    for acc in accounts:
        key = (getattr(acc, "device_key", None) or "").strip()
        if not key:
            try:
                import json

                raw = getattr(acc, "session_json", "") or ""
                settings = json.loads(raw) if raw else None
                key = device_key_from_settings(settings)
            except Exception:  # noqa: BLE001
                key = ""
        if key:
            used.append(key)
    return used


def pick_device_key_for_new_account(used_keys: list[str] | None = None) -> str:
    """Escolhe o próximo modelo menos usado (conta nova). Preferência: ainda não usado."""
    used = list(used_keys or [])
    counts = {d["key"]: 0 for d in DEVICE_POOL}
    for k in used:
        if k in counts:
            counts[k] += 1
    # primeiro os com menor uso; empate → ordem do pool (Samsung primeiro se todos 0)
    ordered = sorted(DEVICE_POOL, key=lambda d: (counts[d["key"]], DEVICE_POOL.index(d)))
    return ordered[0]["key"]


def apply_device(cl, profile: dict[str, Any] | str | None = None) -> bool:
    """Aplica fingerprint. NÃO chamar depois de set_settings no fluxo 2FA."""
    try:
        if isinstance(profile, str):
            prof = get_device_profile(profile)
        elif isinstance(profile, dict) and profile.get("model"):
            prof = dict(profile)
        else:
            prof = get_device_profile("samsung_m04")

        existing = getattr(cl, "device_settings", None) or {}
        bloks = (
            (existing.get("bloks_versioning_id") or "").strip()
            or (prof.get("bloks_versioning_id") or "").strip()
            or BLOKS_VERSIONING_ID
        )
        device = {
            "app_version": prof["app_version"],
            "android_version": prof["android_version"],
            "android_release": prof["android_release"],
            "dpi": prof["dpi"],
            "resolution": prof["resolution"],
            "manufacturer": prof["manufacturer"],
            "device": prof["device"],
            "model": prof["model"],
            "cpu": prof["cpu"],
            "version_code": prof["version_code"],
            "bloks_versioning_id": bloks,
        }
        ua = prof.get("user_agent") or (
            f"Instagram {device['app_version']} Android "
            f"({device['android_version']}/{device['android_release']}; {device['dpi']}; "
            f"{device['resolution']}; {device['manufacturer']}; {device['model']}; "
            f"{device['device']}; {device['cpu']}; pt_BR; {device['version_code']})"
        )

        if hasattr(cl, "set_device"):
            cl.set_device(device)
        else:
            cl.device_settings = dict(device)

        if hasattr(cl, "device_settings") and isinstance(cl.device_settings, dict):
            cl.device_settings["bloks_versioning_id"] = bloks
            cl.device_settings["app_version"] = device["app_version"]
            cl.device_settings["version_code"] = device["version_code"]
            cl.device_settings["model"] = device["model"]
            cl.device_settings["manufacturer"] = device["manufacturer"]
        if hasattr(cl, "bloks_versioning_id"):
            cl.bloks_versioning_id = bloks

        if hasattr(cl, "set_user_agent"):
            try:
                cl.set_user_agent(ua)
            except TypeError:
                cl.user_agent = ua
        else:
            cl.user_agent = ua

        if hasattr(cl, "_header_builder"):
            cl._header_builder = None

        log.info(
            "Device = %s (%s) app=%s",
            prof.get("label") or device["model"],
            device["model"],
            device["app_version"],
        )
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("Falha ao aplicar device: %s", exc)
        return False


def apply_samsung_device(cl) -> bool:
    """Compat: aplica Samsung SM-E045F."""
    return apply_device(cl, "samsung_m04")
