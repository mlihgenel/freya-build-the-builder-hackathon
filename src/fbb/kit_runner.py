"""Kitin run_cases.py'sini aynı süreçte çalıştırır; önce kitin `freya.api`'sine GET tekrarı ekler (kit dosyası değişmez).

11 Eki: simülasyon durum sorgusu (`GET /api/v2/simulations/<id>`) geçici 504 verince kitin koşucusu çöküyor, simülasyon
platformda tamamlansa da sonuç kayboluyordu.

    python -m fbb.kit_runner <run_cases argümanları>
"""
from __future__ import annotations

import runpy
import sys

from fbb import config, kitapi


def main() -> None:
    kitapi.freya()  # yolları ekler ve api'yi sarar
    sys.argv = [str(config.KIT / "tools" / "run_cases.py"), *sys.argv[1:]]
    runpy.run_path(sys.argv[0], run_name="__main__")


if __name__ == "__main__":
    main()
