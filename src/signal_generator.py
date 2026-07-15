"""
src/signal_generator.py — Génération des signaux de trading (BUY/SELL/HOLD)
Combine les prédictions TimesFM + indicateurs techniques
"""

import logging
import numpy as np
from dataclasses import dataclass
import config
from src.indicators import get_indicator_summary
from src.timesfm_predictor import get_forecast_direction

logger = logging.getLogger(__name__)


@dataclass
class TradingSignal:
    """Représente un signal de trading complet."""
    symbol:        str
    pair_name:     str
    signal:        str            # BUY / SELL / HOLD
    confidence:    int            # 0-100
    current_price: float
    take_profit:   float
    stop_loss:     float
    tp_pct:        float
    sl_pct:        float
    rsi:           float
    rsi_status:    str
    macd_trend:    str
    ema_trend:     str
    bb_position:   str
    atr:           float
    forecast_dir:  str
    forecast_4h:   float
    forecast_24h:  float
    is_strong:     bool           # Confiance >= seuil fort


def generate_signal(
    symbol: str,
    df_with_indicators,
    timesfm_predictions: np.ndarray | None,
    chronos_predictions: np.ndarray | None,
) -> TradingSignal | None:
    """
    Génère un signal de trading en combinant :
    - Indicateurs techniques (RSI, MACD, EMA, BB)
    - Prédictions Google TimesFM
    - Prédictions Amazon Chronos
    
    Système de vote pondéré et filtre de double consensus strict.
    """
    if df_with_indicators is None or df_with_indicators.empty:
        logger.warning(f"⚠️  {symbol}: données insuffisantes pour générer un signal")
        return None

    pair_name = config.PAIR_NAMES.get(symbol, symbol)
    ind = get_indicator_summary(df_with_indicators)
    current_price = ind["close"]

    # ─── Système de vote ────────────────────────────────────────────────────────
    votes = []          # liste de tuples (signal, poids)

    # ── RSI ──────────────────────────────────────────────────────────────────
    if ind["rsi"] < config.RSI_OVERSOLD:
        votes.append(("BUY",  2))   # survente
    elif ind["rsi"] > config.RSI_OVERBOUGHT:
        votes.append(("SELL", 2))   # surachat
    else:
        votes.append(("HOLD", 1))

    # ── MACD ─────────────────────────────────────────────────────────────────
    if ind["macd_hist"] > 0:
        votes.append(("BUY",  2))
    elif ind["macd_hist"] < 0:
        votes.append(("SELL", 2))
    else:
        votes.append(("HOLD", 1))

    # ── EMA 20 / 50 (tendance) ────────────────────────────────────────────────
    if ind["ema20"] > ind["ema50"]:
        votes.append(("BUY",  1))
    elif ind["ema20"] < ind["ema50"]:
        votes.append(("SELL", 1))

    # ── Bollinger Bands ───────────────────────────────────────────────────────
    if current_price < ind["bb_lower"] * 1.002:
        votes.append(("BUY",  1))
    elif current_price > ind["bb_upper"] * 0.998:
        votes.append(("SELL", 1))

    # ── Stochastique ─────────────────────────────────────────────────────────
    if ind["stoch_k"] < 20:
        votes.append(("BUY",  1))
    elif ind["stoch_k"] > 80:
        votes.append(("SELL", 1))

    # ── TimesFM (poids triple) ────────────────────────────────────────────────
    forecast = get_forecast_direction(current_price, timesfm_predictions)
    timesfm_dir = forecast["direction"]
    if timesfm_dir == "BUY":
        votes.append(("BUY",  3))
    elif timesfm_dir == "SELL":
        votes.append(("SELL", 3))
    else:
        votes.append(("HOLD", 1))

    # ── Amazon Chronos (poids triple) ─────────────────────────────────────────
    from src.chronos_predictor import get_chronos_direction, predict_chronos
    chronos_dir = get_chronos_direction(current_price, chronos_predictions)
    if chronos_dir == "BUY":
        votes.append(("BUY",  3))
    elif chronos_dir == "SELL":
        votes.append(("SELL", 3))
    else:
        votes.append(("HOLD", 1))

    # ─── Comptage pondéré ───────────────────────────────────────────────────────
    score_buy  = sum(w for sig, w in votes if sig == "BUY")
    score_sell = sum(w for sig, w in votes if sig == "SELL")
    total_weight = sum(w for _, w in votes)

    if score_buy > score_sell:
        final_signal = "BUY"
        confidence = int((score_buy / total_weight) * 100)
    elif score_sell > score_buy:
        final_signal = "SELL"
        confidence = int((score_sell / total_weight) * 100)
    else:
        final_signal = "HOLD"
        confidence = 50

    # ─── FILTRE DE DOUBLE CONSENSUS STRICT ─────────────────────────────────────
    # Si le signal final est un BUY ou un SELL, il faut impérativement que
    # Google TimesFM ET Amazon Chronos soient d'accord sur cette direction.
    if final_signal in ["BUY", "SELL"]:
        if timesfm_dir != chronos_dir:
            logger.info(
                f"⚖️ Désaccord IA sur {pair_name} (TimesFM: {timesfm_dir} vs Chronos: {chronos_dir}) "
                f"→ Signal filtré et forcé à HOLD pour sécurité"
            )
            final_signal = "HOLD"
            confidence = 50

    # Ignorer les signaux sous le seuil minimum
    if confidence < config.MIN_CONFIDENCE and final_signal != "HOLD":
        final_signal = "HOLD"

    # ─── Niveaux TP / SL basés sur l'ATR ───────────────────────────────────────
    atr = ind["atr"]
    if final_signal == "BUY":
        take_profit = round(current_price + atr * config.TAKE_PROFIT_FACTOR, 5)
        stop_loss   = round(current_price - atr * config.STOP_LOSS_FACTOR, 5)
    elif final_signal == "SELL":
        take_profit = round(current_price - atr * config.TAKE_PROFIT_FACTOR, 5)
        stop_loss   = round(current_price + atr * config.STOP_LOSS_FACTOR, 5)
    else:
        take_profit = current_price
        stop_loss   = current_price

    tp_pct = round(abs(take_profit - current_price) / current_price * 100, 3)
    sl_pct = round(abs(stop_loss   - current_price) / current_price * 100, 3)

    signal = TradingSignal(
        symbol=        symbol,
        pair_name=     pair_name,
        signal=        final_signal,
        confidence=    confidence,
        current_price= round(current_price, 5),
        take_profit=   take_profit,
        stop_loss=     stop_loss,
        tp_pct=        tp_pct,
        sl_pct=        sl_pct,
        rsi=           round(ind["rsi"], 1),
        rsi_status=    ind["rsi_status"],
        macd_trend=    ind["macd_trend"],
        ema_trend=     ind["ema_trend"],
        bb_position=   ind["bb_position"],
        atr=           round(atr, 5),
        forecast_dir=  f"TFM:{timesfm_dir}/CHO:{chronos_dir}",
        forecast_4h=   forecast.get("target_4h", current_price),
        forecast_24h=  forecast.get("target_24h", current_price),
        is_strong=     confidence >= config.STRONG_SIGNAL and final_signal != "HOLD",
    )

    logger.info(
        f"📊 {pair_name}: {final_signal} | Confiance: {confidence}% "
        f"| RSI: {ind['rsi']:.1f} | TFM: {timesfm_dir} | CHO: {chronos_dir}"
    )
    return signal
