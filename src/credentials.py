"""`.env` 에서 네이버 API 자격증명을 읽는다."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import ENV_PATH  # noqa: E402


@dataclass(frozen=True)
class Credentials:
    client_id: str
    client_secret: str

    @property
    def is_complete(self) -> bool:
        return bool(self.client_id) and bool(self.client_secret)


def load_credentials() -> Credentials:
    """루트 `.env` 를 읽어 Credentials 를 돌려준다. 값이 없으면 빈 문자열."""
    load_dotenv(ENV_PATH, override=False)
    return Credentials(
        client_id=(os.getenv("NAVER_CLIENT_ID") or "").strip(),
        client_secret=(os.getenv("NAVER_CLIENT_SECRET") or "").strip(),
    )
