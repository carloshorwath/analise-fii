from pathlib import Path

import yaml


_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"
_config: dict | None = None


def _load() -> dict:
    global _config
    if _config is None:
        if _CONFIG_PATH.exists():
            with open(_CONFIG_PATH, encoding="utf-8") as f:
                _config = yaml.safe_load(f) or {}
        else:
            _config = {}
    return _config


def get(key: str, default=None):
    return _load().get(key, default)


def get_piso_liquidez() -> float:
    return float(get("piso_liquidez_21d", 500_000.0))


def get_cdi_anual_pct() -> float:
    return float(get("cdi_anual_pct", 10.5))


def get_janelas_percentil() -> list[int]:
    return get("janelas_percentil", [252, 504, 756])


def get_janela_dy_meses() -> list[int]:
    return get("janela_dy_meses", [12, 24, 36])


def get_threshold(key: str, default=None):
    thresholds = get("thresholds", {})
    return thresholds.get(key, default)
