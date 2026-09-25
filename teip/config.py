"""config.toml, then TEIP_<FIELD> environment overrides."""

import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass
class Config:
    backend: str = "mock"  # mock | usb
    printer: str = "PT-E560BT"
    tape_mm: int = 9  # what the mock reports; UI default
    data_dir: str = "data"  # mock output, templates, recent labels
    font: str = ""  # TTF path; empty = Pillow's bundled Aileron
    icon_dir: str = "icons"
    margin_mm: float = 2.0  # feed before and after each label (ESC i d); printer floor is 2 mm
    gridfinity_base_mm: float = 37.0  # label length for a 1-unit bin; calibrate to your bins
    gridfinity_unit_mm: float = 42.0  # added per extra grid unit
    host: str = "127.0.0.1"
    port: int = 8014
    root_path: str = ""  # e.g. "/labels" behind a reverse proxy that serves teip under a path


def load(path: str | None = None) -> Config:
    path = path or os.environ.get("TEIP_CONFIG", "config.toml")
    data = tomllib.loads(Path(path).read_text()) if Path(path).exists() else {}
    cfg = Config()
    for f in fields(Config):
        v = os.environ.get(f"TEIP_{f.name.upper()}", data.get(f.name))
        if v is not None:
            setattr(cfg, f.name, f.type(v))
    return cfg
