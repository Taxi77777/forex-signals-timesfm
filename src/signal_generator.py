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


def _ai_direction(current_price: float, predictions, threshold_pct: float = 0.02) -> str:
    """Direction prédite par un modèle IA. 'N/A' = modèle indisponible."""
    if predictions is None or len(predictions) == 0:
        return "N/A"
    idx = min(config.FORECAST_HORIZON - 1, len(predictions) - 1)
    target = float(predictions[idx])
    var = (target - current_price) / current_price * 100
    if var > threshold_pct:
        return "BUY"
    if var < -threshold_pct:
        return "SELL"
    return "HOLD"


def _majority_consensus(dirs: dict) -> tuple:
    """
    Consensus MAJORITE IA : au moins 3 IA disponibles doivent etre d'accord.
    Minimum 3 modeles disponibles requis.
    Retourne (direction, nb_disponibles, consensus_atteint: bool).
    """
    avail = {k: v for k, v in dirs.items() if v != "N/A"}
    n = len(avail)
    if n < 3:
        return ("HOLD", n, False)
    
    buys = list(avail.values()).count("BUY")
    sells = list(avail.values()).count("SELL")
    
    if buys >= 3:
        return ("BUY", n, True)
    if sells >= 3:
        return ("SELL", n, True)
        
    return ("HOLD", n, False)


def _fmt_dirs(dirs: dict) -> str:
    return "/".join(f"{k}:{v}" for k, v in dirs.items())


def generate_signal(
    symbol: str,
    df_with_indicators,
    timesfm_predictions: np.ndarray | None,
    chronos_predictions: np.ndarray | None,
    moirai_predictions: np.ndarray | None = None,
    lagllama_predictions: np.ndarray | None = None,
    granite_predictions: np.ndarray | None = None,
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

    # ── Filtre de Tendance Forte ADX (Anti-Range) ───────────────────────────
    last_row = df_with_indicators.iloc[-1]
    if "adx" in last_row:
        adx = float(last_row["adx"])
        if adx < 15:
            logger.info(f"⏳ Filtre Range actif sur {symbol} (ADX: {adx:.1f} < 15) → Signal annulé")
            return None

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

    # ── Les 5 IA (poids triple chacune) ──────────────────────────────────────
    forecast = get_forecast_direction(current_price, timesfm_predictions)

    timesfm_dir  = _ai_direction(current_price, timesfm_predictions)
    chronos_dir  = _ai_direction(current_price, chronos_predictions)
    moirai_dir   = _ai_direction(current_price, moirai_predictions)
    lagllama_dir = _ai_direction(current_price, lagllama_predictions)
    granite_dir  = _ai_direction(current_price, granite_predictions)

    dirs = {
        "TFM": timesfm_dir, "CHO": chronos_dir, "MOI": moirai_dir,
        "LLA": lagllama_dir, "GRA": granite_dir,
    }
    for d in dirs.values():
        if d == "BUY":
            votes.append(("BUY",  3))
        elif d == "SELL":
            votes.append(("SELL", 3))
        elif d == "HOLD":
            votes.append(("HOLD", 1))
        # 'N/A' : modèle indisponible → aucun vote

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

    # FILTRE DE CONSENSUS MAJORITAIRE IA
    # Au moins 3 IA disponibles doivent etre d'accord sur la direction.
    consensus, n_avail, has_consensus = _majority_consensus(dirs)
    if final_signal in ["BUY", "SELL"]:
        if not has_consensus or consensus != final_signal:
            logger.info(
                f"Pas de consensus majoritaire sur {pair_name} ({_fmt_dirs(dirs)}, "
                f"{n_avail}/5 modeles actifs) -> Signal force a HOLD"
            )
            final_signal = "HOLD"
            confidence = 50
        else:
            logger.info(f"CONSENSUS {n_avail}/5 IA MAJORITAIRE sur {pair_name} : {consensus}")

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
        forecast_dir=  _fmt_dirs(dirs),
        forecast_4h=   forecast.get("target_4h", current_price),
        forecast_24h=  forecast.get("target_24h", current_price),
        is_strong=     confidence >= config.MIN_CONFIDENCE and final_signal != "HOLD",
    )

    logger.info(
        f"📊 {pair_name}: {final_signal} | Confiance: {confidence}% "
        f"| RSI: {ind['rsi']:.1f} | {_fmt_dirs(dirs)}"
    )
    return signal
