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

    # ── ADX (force de la tendance) ───────────────────────────────────────────
    df["adx"] = ta.trend.ADXIndicator(
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        window=14,
    ).adx()

    # Fisher Transform (10) — vraie recursion d'Ehlers (lissage progressif)
    # value = 0.33*brut + 0.67*prec ; fisher = 0.5*ln((1+v)/(1-v)) + 0.5*fisher_prec
    # -> montee progressive, asymptote ±7.6 : les paliers ±1.5/2/3/4 deviennent significatifs
    period = 9
    highest_high = df["High"].rolling(window=period).max()
    lowest_low   = df["Low"].rolling(window=period).min()
    range_hl     = (highest_high - lowest_low).replace(0, 1e-10)
    raw          = (2 * ((df["Close"] - lowest_low) / range_hl) - 1).fillna(0.0)
    fishers      = []
    v_prev, f_prev = 0.0, 0.0
    for x in raw:
        v = 0.33 * float(x) + 0.67 * v_prev
        v = max(min(v, 0.999), -0.999)
        f = 0.5 * np.log((1 + v) / (1 - v)) + 0.5 * f_prev
        fishers.append(f)
        v_prev, f_prev = v, f
    df["fisher"] = fishers
    df["fisher_trigger"] = pd.Series(fishers, index=df.index).shift(1)  # ligne signal (Fisher decale de 1)

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
    fisher      = round(float(last["fisher"]), 2) if "fisher" in last else 0.0

    # ── Interpretations ──────────────────────────────────────────────────────
    rsi_status = (
        "Survente 🟢"    if rsi_value < config.RSI_OVERSOLD
        else "Surachat 🔴" if rsi_value > config.RSI_OVERBOUGHT
        else "Neutre ⚖️"
    )

    macd_trend = "Haussier 📈" if macd_hist > 0 else "Baissier 📉"
    ema_trend  = "Haussier 📈"    if ema20 > ema50  else "Baissier 📉"

    bb_position = (
        "Proche Borne Haute ⚠️"  if close > bb_upper * 0.999
        else "Proche Borne Basse ⚠️" if close < bb_lower * 1.001
        else "Dans les Bandes ✅"
    )

    # Fisher Transform — CROISEMENT en zone extreme (style TradingView : Fisher vs ligne signal)
    f1 = float(df.iloc[-1]["fisher"])
    f2 = float(df.iloc[-2]["fisher"]) if len(df) > 1 else f1
    f3 = float(df.iloc[-3]["fisher"]) if len(df) > 2 else f2
    fisher_cross_up   = f1 > f2 and f2 <= f3   # retournement haussier (creux)
    fisher_cross_down = f1 < f2 and f2 >= f3   # retournement baissier (sommet)
    depth = f2  # profondeur du creux/sommet au moment du croisement

    fisher_status = "Neutre"
    if fisher_cross_up and depth <= -1.5:
        if depth <= -4.0:   fisher_status = "💎💎 CROISEMENT EXTREME MAX — Retournement BUY tres fort"
        elif depth <= -3.0: fisher_status = "💎 Croisement tres extreme (BUY fort)"
        elif depth <= -2.0: fisher_status = "⚠️ Croisement extreme bas (BUY)"
        else:               fisher_status = "📉 Croisement zone basse (BUY leger)"
    elif fisher_cross_down and depth >= 1.5:
        if depth >= 4.0:    fisher_status = "🔥🔥 CROISEMENT EXTREME MAX — Retournement SELL tres fort"
        elif depth >= 3.0:  fisher_status = "🔥 Croisement tres extreme (SELL fort)"
        elif depth >= 2.0:  fisher_status = "⚠️ Croisement extreme haut (SELL)"
        else:               fisher_status = "📈 Croisement zone haute (SELL leger)"

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
        "fisher":      fisher,
        "fisher_status": fisher_status,
        "fisher_cross_up":   fisher_cross_up,
        "fisher_cross_down": fisher_cross_down,
        "fisher_depth":      depth,
    }
