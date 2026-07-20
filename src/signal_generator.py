"""
src/signal_generator.py — Génération des signaux de trading (BUY/SELL/HOLD)
Combine les prédictions TimesFM + indicateurs techniques
"""

import logging
import numpy as np
import pandas as pd
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
    stop_loss:     str
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
    fisher:        float          # Fisher Transform value
    fisher_status: str            # Fisher status description
    is_extended:   bool = False
    timeframe:     str = "15m"
    smc_zone:      str = "N/A"
    is_ote:        bool = False


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
    
    if buys >= 4:
        return ("BUY", n, True)
    if sells >= 4:
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
    df_1h: pd.DataFrame | None = None,
    df_4h: pd.DataFrame | None = None,
    timeframe: str = "15m",
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

    # ── Filtre de Volatilité ATR (Anti-Flat / Accélération) ───────────────────
    if "atr" in df_with_indicators.columns and len(df_with_indicators) >= 100:
        atr_series = df_with_indicators["atr"]
        current_atr = float(atr_series.iloc[-1])
        atr_ma = float(atr_series.rolling(window=100).mean().iloc[-1])
        if atr_ma > 0 and current_atr < atr_ma * 0.80:
            logger.info(f"⏳ Filtre Volatilité ATR actif sur {symbol} (ATR actuel: {current_atr:.5f} < 80% de la moyenne 100p: {atr_ma:.5f}) → Signal annulé")
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

    # ── Fisher : croisement en zone extreme (poids gradue selon la profondeur) ────
    fisher = ind["fisher"]
    depth  = ind["fisher_depth"]
    if ind["fisher_cross_up"]:
        if depth <= -4.0:   votes.append(("BUY",  5))
        elif depth <= -3.0: votes.append(("BUY",  4))
        elif depth <= -2.0: votes.append(("BUY",  3))
        elif depth <= -1.5: votes.append(("BUY",  1))
    if ind["fisher_cross_down"]:
        if depth >= 4.0:    votes.append(("SELL", 5))
        elif depth >= 3.0:  votes.append(("SELL", 4))
        elif depth >= 2.0:  votes.append(("SELL", 3))
        elif depth >= 1.5:  votes.append(("SELL", 1))

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

    # ── PONDERATION DYNAMIQUE : chaque IA vote selon son taux de reussite reel ──
    from src.track_record import load_track, get_weight
    _track = load_track()
    ai_weights = {k: get_weight(_track, k, symbol) for k in dirs}
    for k, d in dirs.items():
        w = ai_weights[k]
        if w == 0:
            # IA statistiquement mauvaise sur cette paire (<45%) -> ignoree
            dirs[k] = "N/A" if d != "N/A" else d
            continue
        if d == "BUY":
            votes.append(("BUY",  w))
        elif d == "SELL":
            votes.append(("SELL", w))
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
            logger.info(f"CONSENSUS {n_avail}/5 IA MAJORITAIRE sur {pair_name} : {consensus} | poids: {ai_weights}")

    # Ignorer les signaux sous le seuil minimum
    if confidence < config.MIN_CONFIDENCE and final_signal != "HOLD":
        final_signal = "HOLD"

    # FILTRE D'EXTENSION EMA20 (Structure du Chart)
    # Évite d'acheter ou de vendre si le prix s'est déjà trop éloigné de la moyenne (EMA20 15m).
    is_extended = False
    if final_signal in ["BUY", "SELL"]:
        ema20 = ind.get("ema20")
        if ema20 and ema20 > 0:
            extension_pct = (current_price - ema20) / ema20 * 100
            # Limite d'extension EMA20 adaptative selon le comportement de la devise
            clean_sym = symbol.replace("=X", "").upper()
            if any(ex in clean_sym for ex in ["MXN", "ZAR"]):
                limit_pct = 0.15  # Exotiques très volatiles (15 pips environ)
            elif any(cr in clean_sym for cr in ["AUD", "NZD"]):
                limit_pct = 0.08  # Crosses de volatilité moyenne (8 pips environ)
            else:
                limit_pct = 0.04  # Majeures peu volatiles (EUR, GBP, JPY, CHF) (4 pips environ)
                
            if final_signal == "BUY" and extension_pct > limit_pct:
                logger.info(f"⏳ Filtre Extension actif sur {symbol} (Prix trop haut par rapport à EMA20 : +{extension_pct:.3f}% > {limit_pct}%) -> Signal BUY marqué comme étendu (en attente de pullback)")
                is_extended = True
            elif final_signal == "SELL" and extension_pct < -limit_pct:
                logger.info(f"⏳ Filtre Extension actif sur {symbol} (Prix trop bas par rapport à EMA20 : {extension_pct:.3f}% < -{limit_pct}%) -> Signal SELL marqué comme étendu (en attente de pullback)")
                is_extended = True

    # FILTRE MULTI-TIMEFRAME (TENDANCE EMA 1H + SUPERTREND 1H)
    if getattr(config, "ENABLE_MTF_FILTER", True) and final_signal in ["BUY", "SELL"] and df_1h is not None and not df_1h.empty:
        from src.indicators import compute_all_indicators
        df_1h_ind = compute_all_indicators(df_1h)
        if not df_1h_ind.empty:
            last_1h = df_1h_ind.iloc[-1]
            ema20_1h = float(last_1h["ema20"])
            ema50_1h = float(last_1h["ema50"])
            st_dir_1h = int(last_1h["supertrend_dir"])  # 1=haussier, -1=baissier
            
            # 1. Validation EMA Tendance 1h
            if final_signal == "BUY" and ema20_1h < ema50_1h:
                logger.info(f"⏳ Filtre Tendance 1H actif sur {symbol} (1h EMA20 < EMA50) -> Signal BUY annule")
                final_signal = "HOLD"
                confidence = 50
            elif final_signal == "SELL" and ema20_1h > ema50_1h:
                logger.info(f"⏳ Filtre Tendance 1H actif sur {symbol} (1h EMA20 > EMA50) -> Signal SELL annule")
                final_signal = "HOLD"
                confidence = 50
            
            # 2. Validation Supertrend 1h
            elif final_signal == "BUY" and st_dir_1h == -1:
                logger.info(f"⏳ Filtre Supertrend 1H actif sur {symbol} (tendance 1h baissiere) -> Signal BUY annule")
                final_signal = "HOLD"
                confidence = 50
            elif final_signal == "SELL" and st_dir_1h == 1:
                logger.info(f"⏳ Filtre Supertrend 1H actif sur {symbol} (tendance 1h haussiere) -> Signal SELL annule")
                final_signal = "HOLD"
                confidence = 50
            
            if final_signal != "HOLD":
                logger.info(f"✅ Filtre Multi-Timeframe valide sur {symbol} (1h EMA alignee & 1h Supertrend en phase)")

    # FILTRE MULTI-TIMEFRAME LONG TERME (TENDANCE EMA 4H + SUPERTREND 4H)
    if getattr(config, "ENABLE_MTF_FILTER", True) and final_signal in ["BUY", "SELL"] and df_4h is not None and not df_4h.empty:
        from src.indicators import compute_all_indicators
        df_4h_ind = compute_all_indicators(df_4h)
        if not df_4h_ind.empty:
            last_4h = df_4h_ind.iloc[-1]
            ema20_4h = float(last_4h["ema20"])
            ema50_4h = float(last_4h["ema50"])
            st_dir_4h = int(last_4h["supertrend_dir"])  # 1=haussier, -1=baissier
            
            # 1. Validation EMA Tendance 4h
            if final_signal == "BUY" and ema20_4h < ema50_4h:
                logger.info(f"⏳ Filtre Tendance 4H actif sur {symbol} (4h EMA20 < EMA50) -> Signal BUY annule")
                final_signal = "HOLD"
                confidence = 50
            elif final_signal == "SELL" and ema20_4h > ema50_4h:
                logger.info(f"⏳ Filtre Tendance 4H actif sur {symbol} (4h EMA20 > EMA50) -> Signal SELL annule")
                final_signal = "HOLD"
                confidence = 50
            
            # 2. Validation Supertrend 4h
            elif final_signal == "BUY" and st_dir_4h == -1:
                logger.info(f"⏳ Filtre Supertrend 4H actif sur {symbol} (tendance 4h baissiere) -> Signal BUY annule")
                final_signal = "HOLD"
                confidence = 50
            elif final_signal == "SELL" and st_dir_4h == 1:
                logger.info(f"⏳ Filtre Supertrend 4H actif sur {symbol} (tendance 4h haussiere) -> Signal SELL annule")
                final_signal = "HOLD"
                confidence = 50
            
            if final_signal != "HOLD":
                logger.info(f"✅ Filtre Multi-Timeframe H4 valide sur {symbol} (4h EMA alignee & 4h Supertrend en phase)")

    # ─── Niveaux TP / SL basés sur l'ATR ───────────────────────────────────────
    atr = ind["atr"]
    
    # Nombre exact de modèles d'IA en accord avec la direction du consensus
    votes_count = list(dirs.values()).count(final_signal) if final_signal in ["BUY", "SELL"] else 0
    
    if final_signal in ["BUY", "SELL"]:
        if votes_count >= 5:
            tp_mult_factor = 4.0
            tp_desc = "Consensus 5/5 IA (Max)"
        elif votes_count == 4:
            tp_mult_factor = 3.5
            tp_desc = "Consensus 4/5 IA (Standard)"
        else:
            tp_mult_factor = 2.5
            tp_desc = "Consensus 3/5 IA (Prudent)"
            
        logger.info(f"🎯 {pair_name} | TP Adaptatif choisi : {tp_mult_factor}x ATR ({tp_desc})")
        
        if final_signal == "BUY":
            take_profit = round(current_price + atr * tp_mult_factor, 5)
        else:
            take_profit = round(current_price - atr * tp_mult_factor, 5)
    else:
        take_profit = current_price

    stop_loss   = "Aucun"
    tp_pct      = round(abs(take_profit - current_price) / current_price * 100, 3)
    sl_pct      = 0.0

    # Calcul structure SMC & OTE
    from src.smc_filter import get_smc_ote_status
    smc = get_smc_ote_status(df_with_indicators, final_signal)
    smc_zone = "N/A"
    is_ote = False
    if smc:
        smc_zone = smc["zone"]
        is_ote = smc["is_ote"]

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
        fisher=        ind["fisher"],
        fisher_status= ind["fisher_status"],
        is_extended=   is_extended,
        timeframe=     timeframe,
        smc_zone=      smc_zone,
        is_ote=        is_ote,
    )

    logger.info(
        f"📊 {pair_name}: {final_signal} | Confiance: {confidence}% "
        f"| RSI: {ind['rsi']:.1f} | {_fmt_dirs(dirs)}"
    )
    return signal
