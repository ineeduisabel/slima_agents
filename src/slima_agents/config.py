"""設定檔：讀取環境變數與 ~/.slima/credentials.json。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_BASE_URL = "https://api.slima.ai"
DEFAULT_MODEL = "claude-opus-4-6"
CREDENTIALS_PATH = Path.home() / ".slima" / "credentials.json"


@dataclass
class Config:
    slima_api_token: str
    slima_base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL

    @classmethod
    def load(cls, model_override: str | None = None) -> Config:
        """從環境變數載入設定，未設定時自動讀取 ~/.slima/credentials.json。"""
        try:
            load_dotenv()
        except UnicodeDecodeError:
            # Nuitka onefile 或 Windows 環境可能找到 UTF-16 BOM 的 .env，跳過即可
            # Electron 已透過 env var 傳入 SLIMA_API_TOKEN
            pass

        slima_token = os.getenv("SLIMA_API_TOKEN", "")
        slima_base_url = os.getenv("SLIMA_BASE_URL", "")

        # 自動讀取 ~/.slima/credentials.json
        if not slima_token:
            slima_token, cred_base_url = _load_credentials()
            if not slima_base_url and cred_base_url:
                slima_base_url = cred_base_url

        if not slima_token:
            raise ConfigError(
                "找不到 Slima API Token。請先執行 `slima-mcp auth` 或設定 SLIMA_API_TOKEN 環境變數"
            )

        return cls(
            slima_api_token=slima_token,
            slima_base_url=slima_base_url or DEFAULT_BASE_URL,
            model=model_override or os.getenv("SLIMA_AGENTS_MODEL", DEFAULT_MODEL),
        )


class ConfigError(Exception):
    pass


def _load_credentials() -> tuple[str, str]:
    """從 ~/.slima/credentials.json 讀取 apiToken 和 baseUrl。"""
    try:
        data = json.loads(CREDENTIALS_PATH.read_text())
        return data.get("apiToken", ""), data.get("baseUrl", "")
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return "", ""
