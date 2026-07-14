"""
src/data_fetcher.py — Récupération des données Forex via yfinance
"""

import logging
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import config

logger = logging.getLogger(__name__)


def fetch_forex_data(symbol: str, period: str = None, interval: str = None) -> pd.DataFrame:
    """
    Télécharge les données OHLCV pour une paire Forex.
    
    Args:
        symbol:   Symbole Yahoo Finance (ex: 'EURUSD=X')
        period:   Période historique (ex: '60d')
        interval: Intervalle des bougies (ex: '1h')
    
    Returns:
        DataFrame avec colonnes: Open, High, Low, Close, Volume
    """
    period   = period   or config.DATA_PERIOD
    interval = interval or config.DATA_INTERVAL

    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)

        if df.empty:
            logger.warning(f"⚠️  Pas de données pour {symbol}")
            return pd.DataFrame()

        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.dropna(inplace=True)

        logger.info(f"✅ {symbol}: {len(df)} bougies récupérées")
        return df

    except Exception as e:
        logger.error(f"❌ Erreur récupération {symbol}: {e}")
        return pd.DataFrame()


def fetch_all_pairs() -> dict[str, pd.DataFrame]:
    """
    Télécharge les données pour toutes les paires configurées.
    
    Returns:
        Dictionnaire {symbole: DataFrame}
    """
    data = {}
    for symbol in config.FOREX_PAIRS:
        df = fetch_forex_data(symbol)
        if not df.empty:
            data[symbol] = df
    return data


def get_current_price(symbol: str) -> float | None:
    """
    Retourne le dernier prix disponible pour une paire.
    
    Args:
        symbol: Symbole Yahoo Finance
    
    Returns:
        Prix de clôture le plus récent ou None
    """
    try:
        ticker = yf.Ticker(symbol)
        info   = ticker.fast_info
        price  = info.last_price
        if price and not np.isnan(price):
            return float(price)
        # Fallback: dernier prix historique
        df = fetch_forex_data(symbol, period="2d", interval="1h")
        return float(df["Close"].iloc[-1]) if not df.empty else None
    except Exception as e:
        logger.error(f"❌ Erreur prix {symbol}: {e}")
        return None


def prepare_timesfm_input(df: pd.DataFrame, context_len: int = None) -> np.ndarray:
    """
    Prépare les données au format attendu par TimesFM.
    
    Args:
        df:          DataFrame OHLCV
        context_len: Nombre de points de contexte
    
    Returns:
        Array numpy des prix de clôture normalisés
    """
    context_len = context_len or config.CONTEXT_LENGTH
    closes = df["Close"].values.astype(np.float32)

    # Tronquer / compléter au context_length
    if len(closes) >= context_len:
        return closes[-context_len:]
    else:
        # Padding par répétition du premier élément
        pad_len = context_len - len(closes)
        padding = np.full(pad_len, closes[0], dtype=np.float32)
        return np.concatenate([padding, closes])
