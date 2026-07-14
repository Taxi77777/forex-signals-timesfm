"""
src/indicators.py — Calcul des indicateurs techniques (RSI, MACD, BB, ATR)
"""

import logging
import numpy as np
import pandas as pd
import ta
import config

logger = logging.getLogger(__name__)


def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcule tous les indicateurs techniques sur le DataFrame OHLCV.
    
    Indicateurs calculés :
        - RSI (Relative Strength Index)
        - MACD (Moving Average Convergence Divergence)
        - Bollinger Bands
        - ATR (Average True Range)
        - EMA 20 / EMA 50
        - Stochastique
    
    Args:
        df: DataFrame avec colonnes Open, High, Low, Close, Volume
    
    Returns:
        DataFrame enrichi avec tous les indicateurs
    """
    df = df.copy()

    # ── RSI ──────────────────────────────────────────────────────────────────
    df["rsi"] = ta.momentum.RSIIndicator(
        close=df["Close"], window=config.RSI_PERIOD
    ).rsi()

    # ── MACD ─────────────────────────────────────────────────────────────────
    macd_ind = ta.trend.MACD(
        close=df["Close"],
        window_fast=config.MACD_FAST,
        window_slow=config.MACD_SLOW,
        window_sign=config.MACD_SIGNAL,
    )
    df["macd"]        = macd_ind.macd()
    df["macd_signal"] = macd_ind.macd_signal()
    df["macd_hist"]   = macd_ind.macd_diff()

    # ── Bollinger Bands ───────────────────────────────────────────────────────
    bb_ind = ta.volatility.BollingerBands(
        close=df["Close"],
        window=config.BB_PERIOD,
        window_dev=config.BB_STD,
    )
    df["bb_upper"]  = bb_ind.bollinger_hband()
    df["bb_middle"] = bb_ind.bollinger_mavg()
    df["bb_lower"]  = bb_ind.bollinger_lband()
    df["bb_width"]  = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]

    # ── ATR (volatilité) ─────────────────────────────────────────────────────
    df["atr"] = ta.volatility.AverageTrueRange(
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        window=config.ATR_PERIOD,
    ).average_true_range()

    # ── EMA ──────────────────────────────────────────────────────────────────
    df["ema20"] = ta.trend.EMAIndicator(close=df["Close"], window=20).ema_indicator()
    df["ema50"] = ta.trend.EMAIndicator(close=df["Close"], window=50).ema_indicator()

    # ── Stochastique ─────────────────────────────────────────────────────────
    stoch = ta.momentum.StochasticOscillator(
        high=df["High"], low=df["Low"], close=df["Close"],
        window=14, smooth_window=3,
    )
    df["stoch_k"] = stoch.stoch()
    df["stoch_d"] = stoch.stoch_signal()

    df.dropna(inplace=True)
    return df


def get_indicator_summary(df: pd.DataFrame) -> dict:
    """
    Extrait un résumé des dernières valeurs des indicateurs.
    
    Args:
        df: DataFrame avec indicateurs calculés
    
    Returns:
        Dictionnaire avec les valeurs actuelles des indicateurs
    """
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last

    rsi_value   = float(last["rsi"])
    macd_hist   = float(last["macd_hist"])
    close       = float(last["Close"])
    bb_upper    = float(last["bb_upper"])
    bb_lower    = float(last["bb_lower"])
    ema20       = float(last["ema20"])
    ema50       = float(last["ema50"])
    atr         = float(last["atr"])
    stoch_k     = float(last["stoch_k"])

    # ── Interprétations ──────────────────────────────────────────────────────
    rsi_status = (
        "Survente 🔴"    if rsi_value < config.RSI_OVERSOLD
        else "Surachat 🟠" if rsi_value > config.RSI_OVERBOUGHT
        else "Neutre ⚪"
    )

    macd_trend = "Haussier ↑ 🟢" if macd_hist > 0 else "Baissier ↓ 🔴"
    ema_trend  = "Haussier ↑"    if ema20 > ema50  else "Baissier ↓"

    bb_position = (
        "Proche Borne Haute ⚠️"  if close > bb_upper * 0.999
        else "Proche Borne Basse ⚠️" if close < bb_lower * 1.001
        else "Dans les Bandes ✅"
    )

    return {
        "close":       close,
        "rsi":         rsi_value,
        "rsi_status":  rsi_status,
        "macd_hist":   macd_hist,
        "macd_trend":  macd_trend,
        "ema20":       ema20,
        "ema50":       ema50,
        "ema_trend":   ema_trend,
        "atr":         atr,
        "bb_upper":    bb_upper,
        "bb_lower":    bb_lower,
        "bb_position": bb_position,
        "stoch_k":     stoch_k,
    }
