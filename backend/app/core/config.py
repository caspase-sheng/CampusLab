import os
from pathlib import Path

from dotenv import load_dotenv

# backend/ 目录，用来定位 .env，避免从别的工作目录启动时读不到配置
BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


class Settings:
    """运行期配置。取值优先级：环境变量 > backend/.env > 代码里的默认值。"""

    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./campuslab.db")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change_me")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES") or 1440)
    KV_DATA_DIR: str = os.getenv("KV_DATA_DIR", "data/kv")


settings = Settings()
