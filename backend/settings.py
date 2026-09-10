import os
import dotenv

dotenv.load_dotenv()

# Active LLM Provider ("OPEN_ZEN" / "OPENCODE_ZEN" or "OPENROUTER" / "OPEN_ROUTER")
API_KEY_PROVIDER: str = os.getenv("API_KEY_PROVIDER", "OPEN_ZEN").strip().upper()

# OpenRouter Configuration
OPEN_ROUTER_API_KEY: str = os.getenv("OPEN_ROUTER_API_KEY", "")
OPEN_ROUTER_MODEL: str = os.getenv("OPEN_ROUTER_MODEL", "nvidia/nemotron-3.5-lightning:free")
OPEN_ROUTER_BASE_URL: str = os.getenv("OPEN_ROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# OpenCode Zen Configuration
OPEN_ZEN_API_KEY: str = os.getenv("OPEN_ZEN_API_KEY") or os.getenv("OPENCODE_ZEN_API_KEY", "")
OPEN_ZEN_MODEL: str = os.getenv("OPEN_ZEN_MODEL") or os.getenv("OPENCODE_ZEN_MODEL", "minimax-m3")
OPEN_ZEN_BASE_URL: str = os.getenv("OPEN_ZEN_BASE_URL") or os.getenv("OPENCODE_ZEN_BASE_URL", "https://opencode.ai/zen/v1")

DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///app.db")
