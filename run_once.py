"""
run_once.py — Version single-run pour GitHub Actions
Lance UNE analyse complète, envoie les signaux sur Telegram, puis quitte.
"""

import logging
import os
import sys
import json
import gc
import time
from datetime import datetime, timezone
import yfinance as yf

# Forcer l'encodage utf-8 pour éviter les erreurs d'affichage d'emojis sous Windows
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/signals.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

import config
from src.data_fetcher      import fetch_all_pairs, prepare_timesfm_input
from src.indicators        import compute_all_indicators
from src.timesfm_predictor import predict_timesfm
from src.signal_generator  import generate_signal, TradingSignal
from src.telegram_bot      import send_signals_summary, send_signal, send_message

def get_period_for_interval(interval_str: str) -> str:
    if interval_str == "5m":
        return "5d"
    elif interval_str == "15m":
        return "10d"
    elif interval_str == "30m":
        return "20d"
    return "30d"

def main():
    logger.info("=== GitHub Actions — Analyse Forex Multi-Timeframe démarrée ===")

    # Le Forex est fermé le week-end (samedi=5, dimanche=6 en UTC)
    now_utc = datetime.now(timezone.utc)
    if now_utc.weekday() >= 5:
        logger.info("💤 Marché Forex fermé le week-end (UTC). Arrêt de l'analyse.")
        sys.exit(0)

    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.error("TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID manquant !")
        sys.exit(1)

    # Récupération des données trend guards
    logger.info("Téléchargement des données Forex 1h pour le filtre de tendance...")
    all_data_1h = fetch_all_pairs(period="30d", interval="1h")
    logger.info("Téléchargement des données 4h pour le filtre de tendance majeure...")
    all_data_4h = fetch_all_pairs(period="60d", interval="4h")

    # Définition des intervalles à analyser
    intervals = ["5m", "15m", "30m"]
    all_data_by_interval = {}

    for interval in intervals:
        logger.info(f"Téléchargement des données Forex pour l'intervalle {interval}...")
        period = get_period_for_interval(interval)
        all_data_by_interval[interval] = fetch_all_pairs(period=period, interval=interval)

    # ── APPRENTISSAGE CONTINU : vérifier les prédictions d'il y a 1h ──────────
    from src.track_record import (load_track, save_track, record_result,
                                  load_pending, save_pending, accuracy_summary)
    track   = load_track(force=True)
    pending = load_pending()
    now_ts  = time.time()
    matured = [pr for pr in pending if now_ts - pr["ts"] >= 3600]   # horizon 1h atteint
    waiting = [pr for pr in pending if now_ts - pr["ts"] < 3600]
    verified = 0
    for pr in matured:
        interval_p = pr.get("timeframe", "15m")
        df_p = all_data_by_interval.get(interval_p, {}).get(pr["symbol"])
        if df_p is None or df_p.empty:
            continue
        cur = float(df_p["Close"].iloc[-1])
        var = (cur - pr["price"]) / pr["price"] * 100
        actual = "BUY" if var > 0.02 else "SELL" if var < -0.02 else "HOLD"
        if pr["dir"] in ("BUY", "SELL"):
            record_result(track, pr["model"], pr["symbol"], pr["dir"] == actual)
            verified += 1
    if verified:
        save_track(track)
        logger.info(f"📚 Apprentissage continu : {verified} prédictions vérifiées | {accuracy_summary(track)}")

    # Récupérer les devises bloquées par le calendrier économique
    from src.economic_calendar import get_blocked_currencies
    blocked_currencies = get_blocked_currencies(window_minutes=60)
    logger.info(f"Devises actuellement bloquées par les annonces écon.: {blocked_currencies}")

    # ── Phase A : filtre calendrier + indicateurs + séries de prix ────────────
    series_map_multi = {}
    ind_map_multi = {}

    for interval in intervals:
        all_data = all_data_by_interval[interval]
        for symbol, df in all_data.items():
            pair_name = config.PAIR_NAMES.get(symbol, symbol)

            # Extraire les devises impliquées dans la paire
            clean_sym = symbol.replace("=X", "")
            currencies = [clean_sym[:3], clean_sym[3:]] if len(clean_sym) == 6 else ["USD", clean_sym]

            # Vérifier si l'une des devises est bloquée par le calendrier économique
            is_blocked = False
            for cur in currencies:
                if cur.upper() in blocked_currencies:
                    logger.info(f"🚫 Analyse suspendue pour {pair_name} ({interval}) : la devise {cur} est impactée par une annonce économique forte.")
                    is_blocked = True
                    break

            if is_blocked:
                continue

            try:
                df_ind = compute_all_indicators(df)
                if df_ind.empty:
                    continue
                ind_map_multi[(interval, symbol)] = df_ind
                series_map_multi[(interval, symbol)] = prepare_timesfm_input(df)
            except Exception as e:
                logger.error(f"Erreur indicateurs {pair_name} ({interval}): {e}")
                continue

    # ── Phase B : 5 passes IA séquentielles (chargement → prédictions → libération RAM) ──
    ai_preds = {
        "tfm": {}, "cho": {}, "moi": {}, "lla": {}, "gra": {}
    }

    logger.info("── Passe 1/5 : Google TimesFM 2.5 ──")
    from src.timesfm_predictor import unload_timesfm
    for (interval, sym), series in series_map_multi.items():
        ai_preds["tfm"][(interval, sym)] = predict_timesfm(series)
    unload_timesfm()
    gc.collect()

    logger.info("── Passe 2/5 : Amazon Chronos ──")
    from src.chronos_predictor import predict_chronos, unload_chronos
    for (interval, sym), series in series_map_multi.items():
        ai_preds["cho"][(interval, sym)] = predict_chronos(series)
    unload_chronos()
    gc.collect()

    logger.info("── Passe 3/5 : Salesforce Moirai 2.0 ──")
    from src.moirai_predictor import predict_moirai, unload_moirai
    for (interval, sym), series in series_map_multi.items():
        ai_preds["moi"][(interval, sym)] = predict_moirai(series)
    unload_moirai()
    gc.collect()

    logger.info("── Passe 4/5 : Lag-Llama ──")
    from src.lagllama_predictor import predict_lagllama, unload_lagllama
    for (interval, sym), series in series_map_multi.items():
        ai_preds["lla"][(interval, sym)] = predict_lagllama(series)
    unload_lagllama()
    gc.collect()

    logger.info("── Passe 5/5 : IBM Granite TTM ──")
    from src.granite_predictor import predict_granite, unload_granite
    for (interval, sym), series in series_map_multi.items():
        ai_preds["gra"][(interval, sym)] = predict_granite(series)
    unload_granite()
    gc.collect()

    # ── Enregistrer les prédictions du scan pour vérification future ─────────
    from src.signal_generator import _ai_direction
    for (interval, sym), series in series_map_multi.items():
        cur_price = float(series[-1])
        for key, mp in (("TFM", "tfm"), ("CHO", "cho"), ("MOI", "moi"), ("LLA", "lla"), ("GRA", "gra")):
            d = _ai_direction(cur_price, ai_preds[mp].get((interval, sym)))
            if d in ("BUY", "SELL"):
                waiting.append({
                    "ts": now_ts, "model": key, "symbol": sym, "dir": d,
                    "price": cur_price, "timeframe": interval
                })
    save_pending(waiting)
    save_track(track)   # garantit l'existence du fichier pour le commit

    # ── Phase C : génération des signaux (consensus strict 5 IA) ─────────────
    signals = []
    for (interval, symbol), df_ind in ind_map_multi.items():
        pair_name = config.PAIR_NAMES.get(symbol, symbol)
        try:
            signal = generate_signal(
                symbol, df_ind,
                ai_preds["tfm"].get((interval, symbol)),
                ai_preds["cho"].get((interval, symbol)),
                ai_preds["moi"].get((interval, symbol)),
                ai_preds["lla"].get((interval, symbol)),
                ai_preds["gra"].get((interval, symbol)),
                df_1h=all_data_1h.get(symbol) if all_data_1h else None,
                df_4h=all_data_4h.get(symbol) if all_data_4h else None,
                timeframe=interval,
            )
            if signal:
                signals.append(signal)
        except Exception as e:
            logger.error(f"Erreur {pair_name} ({interval}): {e}")
            continue

    # ── 1. Filtre de Session Majeure ──
    current_hour_utc = now_utc.hour
    is_weekend = now_utc.weekday() >= 5
    
    # Session de Londres + New York (07:00 UTC à 21:00 UTC)
    is_session_active = (7 <= current_hour_utc <= 21)
    
    # ── DXY (US Dollar Index) Guard pour le Forex ──
    dxy_trend = "NEUTRAL"
    if not is_weekend and is_session_active:
        try:
            ticker_dxy = yf.Ticker("DX-Y.NYB")
            dxy_df = ticker_dxy.history(period="10d", interval="1h")
            if dxy_df is not None and not dxy_df.empty:
                dxy_df.columns = [c.capitalize() for c in dxy_df.columns]
                dxy_df_ind = compute_all_indicators(dxy_df)
                if not dxy_df_ind.empty:
                    dxy_last = dxy_df_ind.iloc[-1]
                    dxy_ema20 = float(dxy_last["ema20"])
                    dxy_ema50 = float(dxy_last["ema50"])
                    dxy_st_dir = int(dxy_last["supertrend_dir"])
                    
                    if dxy_ema20 > dxy_ema50 and dxy_st_dir == 1:
                        dxy_trend = "BULLISH"
                    elif dxy_ema20 < dxy_ema50 and dxy_st_dir == -1:
                        dxy_trend = "BEARISH"
            logger.info(f"📊 Macro Guard | Dollar Index (DXY 1H) : {dxy_trend}")
        except Exception as e:
            logger.error(f"Erreur calcul DXY Guard : {e}")

    # ── US 10Y Yield Guard ──
    yield_trend = "NEUTRAL"
    if not is_weekend and is_session_active:
        try:
            ticker_tnx = yf.Ticker("^TNX")
            tnx_df = ticker_tnx.history(period="10d", interval="1h")
            if tnx_df is not None and not tnx_df.empty:
                tnx_df.columns = [c.capitalize() for c in tnx_df.columns]
                tnx_df_ind = compute_all_indicators(tnx_df)
                if not tnx_df_ind.empty:
                    tnx_last = tnx_df_ind.iloc[-1]
                    tnx_ema20 = float(tnx_last["ema20"])
                    tnx_ema50 = float(tnx_last["ema50"])
                    tnx_st_dir = int(tnx_last["supertrend_dir"])
                    
                    if tnx_ema20 > tnx_ema50 and tnx_st_dir == 1:
                        yield_trend = "BULLISH"
                    elif tnx_ema20 < tnx_ema50 and tnx_st_dir == -1:
                        yield_trend = "BEARISH"
            logger.info(f"📊 Macro Guard | US 10Y Yield (^TNX 1H) : {yield_trend}")
        except Exception as e:
            logger.error(f"Erreur calcul Yield Guard : {e}")

    # Envoi Telegram (uniquement les signaux forts triés par confiance décroissante)
    strong_signals = [s for s in signals if s.is_strong and s.signal != "HOLD"]

    # ── Gestionnaire de Pullback (Wait for Pullback logic) ───────────────────
    pullbacks_file = "pending_pullbacks.json"
    pending_pullbacks = []
    if os.path.exists(pullbacks_file):
        try:
            with open(pullbacks_file, "r", encoding="utf-8") as f:
                pending_pullbacks = json.load(f)
        except Exception as e:
            logger.error(f"Erreur chargement pullbacks : {e}")

    active_pullbacks = []
    completed_signals = []
    limit_pct = getattr(config, "MAX_EMA_EXTENSION_PCT", 0.15)

    # 1. Vérifier les pullbacks existants dans la file
    for p in pending_pullbacks:
        p_tf = p.get("timeframe", "15m")
        # Expiration (2h = 7200s)
        if time.time() - p["timestamp"] >= 7200:
            logger.info(f"⏳ Pullback expiré pour {p['pair_name']} ({p_tf}) {p['signal']}")
            send_message(f"⏳ *Pullback expiré (Timeout 2h)*\nSignal {p['pair_name']} ({p_tf}) {p['signal']} annulé.")
            continue

        # Invalidation par un nouveau signal inverse dans la passe actuelle (même timeframe)
        inverse_detected = False
        for s in signals:
            if s.symbol == p["symbol"] and s.timeframe == p_tf and s.is_strong and s.signal != "HOLD" and s.signal != p["signal"]:
                inverse_detected = True
                break
        if inverse_detected:
            logger.info(f"⏳ Pullback invalidé pour {p['pair_name']} ({p_tf}) par un signal inverse")
            send_message(f"❌ *Pullback invalidé*\nLe signal d'origine {p['pair_name']} ({p_tf}) {p['signal']} est annulé suite à une inversion de tendance.")
            continue

        # Vérification du pullback réel
        df_ind = ind_map_multi.get((p_tf, p["symbol"]))
        if df_ind is not None and not df_ind.empty:
            last_row = df_ind.iloc[-1]
            cur_price = float(last_row["Close"])
            ema20 = float(last_row["ema20"])
            ema50 = float(last_row["ema50"])
            extension_pct = (cur_price - ema20) / ema20 * 100

            triggered = False
            invalidated = False
            reason = ""

            if p["signal"] == "BUY":
                if cur_price < ema50:
                    invalidated = True
                    reason = "cassure de l'EMA50 (tendance baissière)"
                elif extension_pct <= limit_pct:
                    triggered = True
            elif p["signal"] == "SELL":
                if cur_price > ema50:
                    invalidated = True
                    reason = "cassure de l'EMA50 (tendance haussière)"
                elif extension_pct >= -limit_pct:
                    triggered = True

            if invalidated:
                logger.info(f"⏳ Pullback invalidé pour {p['pair_name']} ({p_tf}) : {reason}")
                send_message(f"❌ *Pullback invalidé*\nSignal {p['pair_name']} ({p_tf}) {p['signal']} annulé : {reason}.")
                continue

            if triggered:
                logger.info(f"🎯 Pullback complété pour {p['pair_name']} ({p_tf}) {p['signal']} à {cur_price}")
                send_message(
                    f"📥 *Pullback validé - Signal Forex actif* 📥\n"
                    f"Pair : *{p['pair_name']} ({p_tf.upper()})* | Direction : *{p['signal']}*\n"
                    f"Entrée au pullback : {cur_price:.5f} (EMA20: {ema20:.5f})\n"
                    f"Confiance d'origine : {p['confidence']}%\n"
                    f"TP : {p['take_profit']:.5f}"
                )
                
                triggered_sig = TradingSignal(
                    symbol=p["symbol"],
                    pair_name=p["pair_name"],
                    signal=p["signal"],
                    confidence=p["confidence"],
                    current_price=round(cur_price, 5),
                    take_profit=p["take_profit"],
                    stop_loss=p["stop_loss"],
                    tp_pct=p["tp_pct"],
                    sl_pct=p["sl_pct"],
                    rsi=p["rsi"],
                    rsi_status=p["rsi_status"],
                    macd_trend=p["macd_trend"],
                    ema_trend=p["ema_trend"],
                    bb_position=p["bb_position"],
                    atr=p["atr"],
                    forecast_dir=p["forecast_dir"],
                    forecast_4h=p["forecast_4h"],
                    forecast_24h=p["forecast_24h"],
                    is_strong=True,
                    fisher=p["fisher"],
                    fisher_status=p["fisher_status"],
                    is_extended=False,
                    timeframe=p_tf
                )
                completed_signals.append(triggered_sig)
            else:
                active_pullbacks.append(p)
        else:
            active_pullbacks.append(p)

    # 2. Traiter les nouveaux signaux de la passe actuelle
    immediate_signals = []
    for s in strong_signals:
        if s.is_extended:
            if not any(p["symbol"] == s.symbol and p.get("timeframe", "15m") == s.timeframe for p in active_pullbacks):
                df_ind = ind_map_multi.get((s.timeframe, s.symbol))
                last_row = df_ind.iloc[-1] if df_ind is not None else None
                ema20_val = float(last_row["ema20"]) if last_row is not None else 0.0
                
                new_p = {
                    "symbol": s.symbol,
                    "pair_name": s.pair_name,
                    "signal": s.signal,
                    "confidence": s.confidence,
                    "current_price": s.current_price,
                    "take_profit": s.take_profit,
                    "stop_loss": s.stop_loss,
                    "tp_pct": s.tp_pct,
                    "sl_pct": s.sl_pct,
                    "rsi": s.rsi,
                    "rsi_status": s.rsi_status,
                    "macd_trend": s.macd_trend,
                    "ema_trend": s.ema_trend,
                    "bb_position": s.bb_position,
                    "atr": s.atr,
                    "forecast_dir": s.forecast_dir,
                    "forecast_4h": s.forecast_4h,
                    "forecast_24h": s.forecast_24h,
                    "fisher": s.fisher,
                    "fisher_status": s.fisher_status,
                    "timestamp": time.time(),
                    "timeframe": s.timeframe
                }
                active_pullbacks.append(new_p)
                logger.info(f"⏳ Nouveau signal {s.pair_name} ({s.timeframe}) {s.signal} mis en attente de pullback")
                send_message(
                    f"⏳ *Signal Forex détecté (En attente de Pullback - {s.timeframe.upper()})* ⏳\n"
                    f"Pair : *{s.pair_name}* | Direction : *{s.signal}* (Confiance: {s.confidence}%)\n"
                    f"Prix actuel : {s.current_price:.5f} (Trop étendu par rapport à l'EMA20)\n"
                    f"Seuil d'entrée souhaité : <= +{limit_pct}% de l'EMA20 (EMA20 actuelle : {ema20_val:.5f})"
                )
        else:
            immediate_signals.append(s)

    # Sauvegarder la file d'attente des pullbacks
    try:
        with open(pullbacks_file, "w", encoding="utf-8") as f:
            json.dump(active_pullbacks, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Erreur sauvegarde pullbacks : {e}")

    # strong_signals contient maintenant uniquement les signaux immédiats + les pullbacks complétés de ce scan
    strong_signals = immediate_signals + completed_signals
    
    # Si hors session, on vide les signaux forts
    if getattr(config, "ENABLE_SESSION_FILTER", True) and not is_session_active:
        logger.info(f"⏳ Session Filter | Hors sessions majeures (Heure UTC : {now_utc.strftime('%H:%M')}). Filtre actif.")
        strong_signals = []
    
    # Filtrer avec le DXY et Yield Correlation Guards
    filtered_strong_signals = []
    for s in strong_signals:
        clean_sym = s.symbol.replace("=X", "")
        is_usd_base = clean_sym.startswith("USD")
        is_usd_quote = clean_sym.endswith("USD")
        
        block = False
        reasons = []
        
        # Validation DXY
        if getattr(config, "ENABLE_DXY_GUARD", False):
            if dxy_trend == "BULLISH":
                if is_usd_quote and s.signal == "BUY":
                    block = True
                    reasons.append("Dollar (DXY) haussier")
                elif is_usd_base and s.signal == "SELL":
                    block = True
                    reasons.append("Dollar (DXY) haussier")
            elif dxy_trend == "BEARISH":
                if is_usd_quote and s.signal == "SELL":
                    block = True
                    reasons.append("Dollar (DXY) baissier")
                elif is_usd_base and s.signal == "BUY":
                    block = True
                    reasons.append("Dollar (DXY) baissier")
                
        # Validation Yield Guard
        if getattr(config, "ENABLE_YIELD_GUARD", False):
            if yield_trend == "BULLISH":
                if is_usd_quote and s.signal == "BUY":
                    block = True
                    reasons.append("Taux US10Y haussiers")
                elif is_usd_base and s.signal == "SELL":
                    block = True
                    reasons.append("Taux US10Y haussiers")
            elif yield_trend == "BEARISH":
                if is_usd_quote and s.signal == "SELL":
                    block = True
                    reasons.append("Taux US10Y baissiers")
                elif is_usd_base and s.signal == "BUY":
                    block = True
                    reasons.append("Taux US10Y baissiers")
                
        if block:
            block_msg = " + ".join(reasons)
            logger.info(f"🛡️ DXY/Yield Guard Block | Signal {s.pair_name} ({s.timeframe}) {s.signal} bloqué car : {block_msg}")
            send_message(f"🛡️ *DXY/Yield Guard*\nSignal {s.pair_name} ({s.timeframe}) {s.signal} bloqué car :\n_{block_msg}_", chat_id="375129602")
        else:
            filtered_strong_signals.append(s)
            
    strong_signals = filtered_strong_signals
 
    # ── Filtre de Corrélation Croisée ──
    # Si deux paires très corrélées (ex EURUSD et GBPUSD) ont des signaux opposés sur le même timeframe, on annule les deux !
    correlated_pairs = [
        ("EURUSD=X", "GBPUSD=X"),
    ]
    blocked_by_correlation = set()
    for p1, p2 in correlated_pairs:
        # Check by timeframe
        for tf in intervals:
            s1 = next((s for s in strong_signals if s.symbol == p1 and s.timeframe == tf), None)
            s2 = next((s for s in strong_signals if s.symbol == p2 and s.timeframe == tf), None)
            if s1 and s2:
                if s1.signal != s2.signal:
                    logger.info(f"🛡️ Cross-Correlation | Signaux opposés sur {s1.pair_name} ({s1.signal}) et {s2.pair_name} ({s2.signal}) en {tf.upper()} -> Annulation mutuelle.")
                    send_message(f"🛡️ *Cross-Correlation Guard*\nSignaux opposés sur {s1.pair_name} ({s1.signal}) et {s2.pair_name} ({s2.signal}) en {tf.upper()} -> Les deux signaux sont annulés par sécurité.", chat_id="375129602")
                    blocked_by_correlation.add((tf, p1))
                    blocked_by_correlation.add((tf, p2))
                
    strong_signals = [s for s in strong_signals if (s.timeframe, s.symbol) not in blocked_by_correlation]
    strong_signals.sort(key=lambda s: s.confidence, reverse=True)
    
    # Exporter au format JSON pour le site web (GitHub Pages)
    web_data = {
        "last_update": datetime.now(timezone.utc).isoformat(),
        "signals": [
            {
                "pair_name": s.pair_name,
                "signal": s.signal,
                "current_price": s.current_price,
                "take_profit": s.take_profit,
                "stop_loss": s.stop_loss,
                "confidence": s.confidence,
                "rsi": s.rsi,
                "macd_trend": s.macd_trend,
                "forecast_dir": s.forecast_dir,
                "timeframe": s.timeframe
            } for s in strong_signals
        ]
    }
    
    with open("signals.json", "w", encoding="utf-8") as f:
        json.dump(web_data, f, indent=2, ensure_ascii=False)
    logger.info("Fichier signals.json mis à jour pour le site web.")
    
    if strong_signals:
        logger.info(f"Envoi de {len(strong_signals)} signaux forts sur Telegram...")
        for s in strong_signals:
            send_signal(s)
            time.sleep(0.5)
        logger.info(f"OK — {len(strong_signals)} signaux forts envoyés !")
    else:
        logger.info("Aucun signal fort détecté pour cette heure-ci.")
        # Heartbeat : confirme que le bot tourne même sans signal
        total_paires = sum(len(all_data_by_interval[tf]) for tf in intervals)
        send_message(
            f"🔍 *Scan Forex terminé*\n"
            f"📊 Paires analysées sur 5m, 15m et 30m ({total_paires} séries)\n"
            f"🤖 {len(signals)} signaux évalués — 0 signal fort\n"
            f"Consensus majoritaire (>=3/5) IA actif\n"
            f"_Prochain scan dans 30 min_"
        )

    logger.info("=== Analyse terminée ===")

if __name__ == "__main__":
    main()
