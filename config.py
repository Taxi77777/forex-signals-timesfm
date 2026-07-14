"""
config.py — Configuration globale du bot de signaux Forex
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ─── Paires Forex majeures ─────────────────────────────────────────────────────
FOREX_PAIRS = [
    "EURUSD=X",   # EUR/USD
    "GBPUSD=X",   # GBP/USD
    "JPY=X",      # USD/JPY
    "AUDUSD=X",   # AUD/USD
    "CAD=X",      # USD/CAD
    "CHF=X",      # USD/CHF
    "NZDUSD=X",   # NZD/USD
]

PAIR_NAMES = {
    "EURUSD=X": "EUR/USD",
    "GBPUSD=X": "GBP/USD",
    "JPY=X":    "USD/JPY",
    "AUDUSD=X": "AUD/USD",
    "CAD=X":    "USD/CAD",
    "CHF=X":    "USD/CHF",
    "NZDUSD=X": "NZD/USD",
}

# ─── Données ───────────────────────────────────────────────────────────────────
DATA_INTERVAL       = os.getenv("DATA_INTERVAL", "1h")         # intervalle des bougies
DATA_PERIOD         = "60d"                                     # historique à télécharger
FORECAST_HORIZON    = 24                                        # heures de prédiction
CONTEXT_LENGTH      = 512                                       # points de contexte TimesFM

# ─── Fréquence des signaux ─────────────────────────────────────────────────────
SIGNAL_FREQUENCY_HOURS = int(os.getenv("SIGNAL_FREQUENCY_HOURS", "1"))

# ─── Indicateurs techniques ────────────────────────────────────────────────────
RSI_PERIOD          = 14
RSI_OVERSOLD        = 30
RSI_OVERBOUGHT      = 70
MACD_FAST           = 12
MACD_SLOW           = 26
MACD_SIGNAL         = 9
BB_PERIOD           = 20
BB_STD              = 2
ATR_PERIOD          = 14

# ─── Gestion du risque ─────────────────────────────────────────────────────────
TAKE_PROFIT_FACTOR  = 1.5     # TP = 1.5x l'ATR
STOP_LOSS_FACTOR    = 1.0     # SL = 1.0x l'ATR

# ─── Seuils de confiance ───────────────────────────────────────────────────────
MIN_CONFIDENCE      = 55      # Signal ignoré si confiance < 55%
STRONG_SIGNAL       = 70      # Signal fort si confiance >= 70%

# ─── TimesFM ───────────────────────────────────────────────────────────────────
USE_TIMESFM         = os.getenv("USE_TIMESFM", "true").lower() == "true"
TIMESFM_MODEL_ID    = "google/timesfm-1.0-200m-pytorch"
TIMESFM_BACKEND     = "cpu"   # "cpu" ou "gpu"

# ─── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL           = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE            = "logs/signals.log"
