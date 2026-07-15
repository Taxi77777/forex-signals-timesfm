"""
run_once.py — Version single-run pour GitHub Actions
Lance UNE analyse complète, envoie les signaux sur Telegram, puis quitte.
"""

import logging
import os
import sys

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
from src.signal_generator  import generate_signal
from src.telegram_bot      import send_signals_summary, send_signal

import time

def main():
    logger.info("=== GitHub Actions — Analyse Forex démarrée ===")

    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.error("TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID manquant !")
        sys.exit(1)

    # Récupération des données
    logger.info("Téléchargement des données Forex...")
    all_data = fetch_all_pairs()

    if not all_data:
        logger.error("Aucune donnée récupérée")
        sys.exit(1)

    # Récupérer les devises bloquées par le calendrier économique
    from src.economic_calendar import get_blocked_currencies
    blocked_currencies = get_blocked_currencies(window_minutes=60)
    logger.info(f"Devises actuellement bloquées par les annonces écon.: {blocked_currencies}")

    # Analyse de chaque paire
    signals = []
    for symbol, df in all_data.items():
        pair_name = config.PAIR_NAMES.get(symbol, symbol)
        
        # Extraire les devises impliquées dans la paire
        clean_sym = symbol.replace("=X", "")
        currencies = [clean_sym[:3], clean_sym[3:]] if len(clean_sym) == 6 else ["USD", clean_sym]
        
        # Vérifier si l'une des devises est bloquée par le calendrier économique
        is_blocked = False
        for cur in currencies:
            if cur.upper() in blocked_currencies:
                logger.info(f"🚫 Analyse suspendue pour {pair_name} : la devise {cur} est impactée par une annonce économique forte.")
                is_blocked = True
                break
                
        if is_blocked:
            continue

        try:
            df_ind = compute_all_indicators(df)
            if df_ind.empty:
                continue
            price_series = prepare_timesfm_input(df)
            
            # Prédictions Google TimesFM
            tfm_predictions = predict_timesfm(price_series)
            
            # Prédictions Amazon Chronos
            from src.chronos_predictor import predict_chronos
            chronos_predictions = predict_chronos(price_series)
            
            signal = generate_signal(symbol, df_ind, tfm_predictions, chronos_predictions)
            if signal:
                signals.append(signal)
        except Exception as e:
            logger.error(f"Erreur {pair_name}: {e}")
            continue

    # Envoi Telegram (uniquement les signaux forts)
    strong_signals = [s for s in signals if s.is_strong and s.signal != "HOLD"]
    
    # Exporter au format JSON pour le site web (GitHub Pages)
    import json
    from datetime import datetime, timezone
    
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
                "forecast_dir": s.forecast_dir
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
        from src.telegram_bot import send_message
        send_message(
            f"🔍 *Scan Forex terminé*\n"
            f"📊 {len(all_data)} paires analysées\n"
            f"🤖 {len(signals)} signaux évalués — 0 signal fort\n"
            f"⚖️ Filtre double consensus IA actif\n"
            f"_Prochain scan dans 30 min_"
        )

    logger.info("=== Analyse terminée ===")

if __name__ == "__main__":
    main()
