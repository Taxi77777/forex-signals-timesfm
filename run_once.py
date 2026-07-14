"""
run_once.py — Version single-run pour GitHub Actions
Lance UNE analyse complète, envoie les signaux sur Telegram, puis quitte.
"""

import logging
import os
import sys

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

    # Analyse de chaque paire
    signals = []
    for symbol, df in all_data.items():
        pair_name = config.PAIR_NAMES.get(symbol, symbol)
        try:
            df_ind = compute_all_indicators(df)
            if df_ind.empty:
                continue
            price_series = prepare_timesfm_input(df)
            predictions  = predict_timesfm(price_series)
            signal = generate_signal(symbol, df_ind, predictions)
            if signal:
                signals.append(signal)
        except Exception as e:
            logger.error(f"Erreur {pair_name}: {e}")
            continue

    # Envoi Telegram (uniquement les signaux forts)
    strong_signals = [s for s in signals if s.is_strong and s.signal != "HOLD"]
    
    if strong_signals:
        logger.info(f"Envoi de {len(strong_signals)} signaux forts sur Telegram...")
        for s in strong_signals:
            send_signal(s)
            time.sleep(0.5)
        logger.info(f"OK — {len(strong_signals)} signaux forts envoyés !")
    else:
        logger.info("Aucun signal fort détecté pour cette heure-ci.")

    logger.info("=== Analyse terminée ===")

if __name__ == "__main__":
    main()
