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

    # ── SUPERTREND (ATR 10, multiplicateur 3) ──
    try:
        st_period, st_mult = 10, 3.0
        atr_st = ta.volatility.AverageTrueRange(
            df["High"], df["Low"], df["Close"], window=st_period
        ).average_true_range()
        hl2 = (df["High"] + df["Low"]) / 2
        upper = hl2 + st_mult * atr_st
        lower = hl2 - st_mult * atr_st
        close_v = df["Close"].values
        up_v, lo_v = upper.values, lower.values
        st_line = [0.0] * len(df)
        st_dir  = [1]   * len(df)   # 1 = haussier, -1 = baissier
        for i in range(len(df)):
            if i == 0:
                st_line[i] = lo_v[i]
                continue
            f_up = up_v[i] if (up_v[i] < st_line[i-1] or close_v[i-1] > st_line[i-1]) else st_line[i-1]
            f_lo = lo_v[i] if (lo_v[i] > st_line[i-1] or close_v[i-1] < st_line[i-1]) else st_line[i-1]
            if close_v[i] > f_up:
                st_dir[i], st_line[i] = 1, f_lo
            elif close_v[i] < f_lo:
                st_dir[i], st_line[i] = -1, f_up
            else:
                st_dir[i] = st_dir[i-1]
                st_line[i] = f_lo if st_dir[i] == 1 else f_up
        df["supertrend"]     = st_line
        df["supertrend_dir"] = st_dir
        # Flip
        df["st_flip_up"]   = (pd.Series(st_dir, index=df.index) == 1)  & (pd.Series(st_dir, index=df.index).shift(1) == -1)
        df["st_flip_down"] = (pd.Series(st_dir, index=df.index) == -1) & (pd.Series(st_dir, index=df.index).shift(1) == 1)
    except Exception as e:
        logger.error(f"Error computing SuperTrend: {e}")

    # ── STOCHASTIQUE RSI & CROISEMENT REVERSAL (Zone 20/80) ──
    try:
        rsi_s = df["rsi"]
        rsi_min = rsi_s.rolling(14).min()
        rsi_max = rsi_s.rolling(14).max()
        stoch_rsi_raw = (rsi_s - rsi_min) / (rsi_max - rsi_min + 1e-8) * 100
        df["stoch_rsi_k"] = stoch_rsi_raw.rolling(3).mean()
        df["stoch_rsi_d"] = df["stoch_rsi_k"].rolling(3).mean()
    except Exception as e:
        df["stoch_rsi_k"] = df["stoch_k"]
        df["stoch_rsi_d"] = df["stoch_k"]

    # ── BOUGIE D'AVALEMENT SUR EMA20 (Engulfing Candle Reversal) ──
    try:
        o = df["Open"].values
        c = df["Close"].values
        h = df["High"].values
        l = df["Low"].values
        ema20_arr = df["ema20"].values
        
        engulf = ["NONE"] * len(df)
        for i in range(1, len(df)):
            if c[i] > o[i] and c[i-1] < o[i-1] and c[i] >= o[i-1] and l[i] <= ema20_arr[i] * 1.002:
                engulf[i] = "BULLISH_ENGULFING"
            elif c[i] < o[i] and c[i-1] > o[i-1] and c[i] <= o[i-1] and h[i] >= ema20_arr[i] * 0.998:
                engulf[i] = "BEARISH_ENGULFING"
        df["engulfing_reversal"] = engulf
    except Exception as e:
        df["engulfing_reversal"] = "NONE"

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

    # ── Divergence RSI (Anticipation Forex) ──────────────────────────────────
    recent_price_max = df["High"].iloc[-5:].max() if len(df) >= 15 else close
    prev_price_max   = df["High"].iloc[-15:-5].max() if len(df) >= 15 else close
    recent_rsi_max   = df["rsi"].iloc[-5:].max() if len(df) >= 15 else rsi_value
    prev_rsi_max     = df["rsi"].iloc[-15:-5].max() if len(df) >= 15 else rsi_value

    recent_price_min = df["Low"].iloc[-5:].min() if len(df) >= 15 else close
    prev_price_min   = df["Low"].iloc[-15:-5].min() if len(df) >= 15 else close
    recent_rsi_min   = df["rsi"].iloc[-5:].min() if len(df) >= 15 else rsi_value
    prev_rsi_min     = df["rsi"].iloc[-15:-5].min() if len(df) >= 15 else rsi_value

    rsi_divergence = "NONE"
    if recent_price_max > prev_price_max and recent_rsi_max < prev_rsi_max - 2.0 and recent_rsi_max > 60:
        rsi_divergence = "BEARISH"  # Divergence Baissière (Signal Vente très fort)
    elif recent_price_min < prev_price_min and recent_rsi_min > prev_rsi_min + 2.0 and recent_rsi_min < 40:
        rsi_divergence = "BULLISH"  # Divergence Haussière (Signal Achat très fort)

    # ── Liquidity Sweep Detection (SMC Rejection Wick - Chasse aux Stops Banques) ──────────
    liquidity_sweep = "NONE"
    if len(df) >= 20:
        prev_swing_low   = float(df["Low"].iloc[-20:-3].min())
        prev_swing_high  = float(df["High"].iloc[-20:-3].max())
        recent_low       = float(df["Low"].iloc[-3:].min())
        recent_high      = float(df["High"].iloc[-3:].max())
        latest_close     = float(close)

        # Bullish Sweep: Mèche sous le creux précédent + réintégration au-dessus du creux
        if recent_low < prev_swing_low and latest_close > prev_swing_low:
            liquidity_sweep = "BULLISH_SWEEP"  # Balayage des stops vendeurs -> Rebond haussier imminent

        # Bearish Sweep: Mèche au-dessus du sommet précédent + réintégration sous le sommet
        elif recent_high > prev_swing_high and latest_close < prev_swing_high:
            liquidity_sweep = "BEARISH_SWEEP"  # Balayage des stops acheteurs -> Chute baissière intelligente

    # ── STOCHASTIQUE RSI REVERSAL CROSS (20/80) ──
    stoch_rsi_cross = "NONE"
    if len(df) >= 3:
        k1 = float(df.iloc[-1].get("stoch_rsi_k", 50))
        d1 = float(df.iloc[-1].get("stoch_rsi_d", 50))
        k2 = float(df.iloc[-2].get("stoch_rsi_k", 50))
        d2 = float(df.iloc[-2].get("stoch_rsi_d", 50))
        
        if k1 > d1 and k2 <= d2 and k2 <= 25:
            stoch_rsi_cross = "BUY_REVERSAL"
        elif k1 < d1 and k2 >= d2 and k2 >= 75:
            stoch_rsi_cross = "SELL_REVERSAL"

    engulfing_reversal = df.iloc[-1].get("engulfing_reversal", "NONE")

    return {
        "close":              close,
        "rsi":                rsi_value,
        "rsi_status":         rsi_status,
        "rsi_divergence":     rsi_divergence,
        "liquidity_sweep":    liquidity_sweep,
        "stoch_rsi_cross":    stoch_rsi_cross,
        "engulfing_reversal": engulfing_reversal,
        "macd_hist":          macd_hist,
        "macd_trend":         macd_trend,
        "ema20":              ema20,
        "ema50":              ema50,
        "ema_trend":          ema_trend,
        "atr":                atr,
        "bb_upper":           bb_upper,
        "bb_lower":           bb_lower,
        "bb_position":        bb_position,
        "stoch_k":            stoch_k,
        "fisher":             fisher,
        "fisher_status":      fisher_status,
        "fisher_cross_up":   fisher_cross_up,
        "fisher_cross_down": fisher_cross_down,
        "fisher_depth":      depth,
    }
