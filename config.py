"""
config.py — Configuration globale du bot de signaux Forex
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ─── Paires Forex (majeures + mineures + exotiques) ───────────────────────────
FOREX_PAIRS = [
    # ── Majeures ──────────────────────────────────────────────────────────────
    "EURUSD=X",   # EUR/USD
    "GBPUSD=X",   # GBP/USD
    "JPY=X",      # USD/JPY
    "AUDUSD=X",   # AUD/USD
    "CAD=X",      # USD/CAD
    "CHF=X",      # USD/CHF
    "NZDUSD=X",   # NZD/USD
    # ── Croisées EUR ──────────────────────────────────────────────────────────
    "EURGBP=X",   # EUR/GBP
    "EURJPY=X",   # EUR/JPY
    "EURAUD=X",   # EUR/AUD
    "EURCAD=X",   # EUR/CAD
    "EURCHF=X",   # EUR/CHF
    "EURNZD=X",   # EUR/NZD
    # ── Croisées GBP ──────────────────────────────────────────────────────────
    "GBPJPY=X",   # GBP/JPY
    "GBPAUD=X",   # GBP/AUD
    "GBPCAD=X",   # GBP/CAD
    "GBPCHF=X",   # GBP/CHF
    "GBPNZD=X",   # GBP/NZD
    # ── Croisées AUD ──────────────────────────────────────────────────────────
    "AUDJPY=X",   # AUD/JPY
    "AUDCAD=X",   # AUD/CAD
    "AUDCHF=X",   # AUD/CHF
    "AUDNZD=X",   # AUD/NZD
    # ── Croisées NZD / CAD / CHF ──────────────────────────────────────────────
    "NZDJPY=X",   # NZD/JPY
    "CADJPY=X",   # CAD/JPY
    "CHFJPY=X",   # CHF/JPY
    # ── Exotiques ─────────────────────────────────────────────────────────────
    "MXN=X",      # USD/MXN
    "USDTRY=X",   # USD/TRY
    "USDZAR=X",   # USD/ZAR
    "USDSEK=X",   # USD/SEK
    "USDNOK=X",   # USD/NOK
    "USDDKK=X",   # USD/DKK
    "USDSGD=X",   # USD/SGD
    "USDHKD=X",   # USD/HKD
]

PAIR_NAMES = {
    # Majeures
    "EURUSD=X": "EUR/USD",
    "GBPUSD=X": "GBP/USD",
    "JPY=X":    "USD/JPY",
    "AUDUSD=X": "AUD/USD",
    "CAD=X":    "USD/CAD",
    "CHF=X":    "USD/CHF",
    "NZDUSD=X": "NZD/USD",
    # Croisées EUR
    "EURGBP=X": "EUR/GBP",
    "EURJPY=X": "EUR/JPY",
    "EURAUD=X": "EUR/AUD",
    "EURCAD=X": "EUR/CAD",
    "EURCHF=X": "EUR/CHF",
    "EURNZD=X": "EUR/NZD",
    # Croisées GBP
    "GBPJPY=X": "GBP/JPY",
    "GBPAUD=X": "GBP/AUD",
    "GBPCAD=X": "GBP/CAD",
    "GBPCHF=X": "GBP/CHF",
    "GBPNZD=X": "GBP/NZD",
    # Croisées AUD
    "AUDJPY=X": "AUD/JPY",
    "AUDCAD=X": "AUD/CAD",
    "AUDCHF=X": "AUD/CHF",
    "AUDNZD=X": "AUD/NZD",
    # Croisées NZD / CAD / CHF
    "NZDJPY=X": "NZD/JPY",
    "CADJPY=X": "CAD/JPY",
    "CHFJPY=X": "CHF/JPY",
    # Exotiques
    "MXN=X":    "USD/MXN",
    "USDTRY=X": "USD/TRY",
    "USDZAR=X": "USD/ZAR",
    "USDSEK=X": "USD/SEK",
    "USDNOK=X": "USD/NOK",
    "USDDKK=X": "USD/DKK",
    "USDSGD=X": "USD/SGD",
    "USDHKD=X": "USD/HKD",
}

# ─── Données ───────────────────────────────────────────────────────────────────
DATA_INTERVAL       = os.getenv("DATA_INTERVAL", "5m")         # intervalle des bougies (5 min)
DATA_PERIOD         = "30d"                                     # historique à télécharger
FORECAST_HORIZON    = 4                                         # 4 bougies de 5min = 20min de prédiction
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
TAKE_PROFIT_FACTOR  = 3.5     # TP = 3.5x l'ATR (laisse respirer en 15m)
STOP_LOSS_FACTOR    = 3.0     # SL = 3.0x l'ATR (laisse respirer en 15m)

# ─── Seuils de confiance ───────────────────────────────────────────────────────
MIN_CONFIDENCE      = 65      # Signal ignoré si confiance < 65%
STRONG_SIGNAL       = 65      # Signal fort si confiance >= 65%
MAX_EMA_EXTENSION_PCT = 0.15   # Écart max toléré avec EMA20 15m (%)

# ─── Guards de Marché (Filtres de Tendance) ───────────────────────────────────
ENABLE_DXY_GUARD         = False   # Bloque les BUY si Dollar Index est haussier (désactivé car très restrictif)
ENABLE_YIELD_GUARD       = False   # Bloque les BUY si les taux US10Y sont haussiers (désactivé car très restrictif)
ENABLE_SESSION_FILTER    = True    # Ne trade que durant les sessions de Londres/NY (07h-21h UTC)
ENABLE_MTF_FILTER        = False   # Bloque les signaux si la tendance 1H/4H est adverse (Désactivé pour avoir plus de signaux)

# ─── TimesFM ───────────────────────────────────────────────────────────────────
USE_TIMESFM         = os.getenv("USE_TIMESFM", "true").lower() == "true"
TIMESFM_MODEL_ID    = "google/timesfm-1.0-200m-pytorch"
TIMESFM_BACKEND     = "cpu"   # "cpu" ou "gpu"

# ─── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL           = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE            = "logs/signals.log"
