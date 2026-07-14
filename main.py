"""
main.py — Point d'entrée principal du bot de signaux Forex
Lance la boucle de génération et d'envoi des signaux sur Telegram.
"""

import logging
import os
import sys
import time
import schedule
from datetime import datetime

# ─── Configuration du logging ───────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/signals.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ─── Imports modules ────────────────────────────────────────────────────────────
import config
from src.data_fetcher     import fetch_all_pairs, prepare_timesfm_input
from src.indicators       import compute_all_indicators
from src.timesfm_predictor import predict_timesfm
from src.signal_generator  import generate_signal
from src.telegram_bot      import (
    send_signals_summary,
    send_signal,
    send_startup_message,
    send_error_message,
)


def run_analysis() -> None:
    """
    Boucle principale d'analyse :
    1. Télécharge les données Forex
    2. Calcule les indicateurs techniques
    3. Génère les prédictions TimesFM
    4. Crée les signaux de trading
    5. Envoie le résumé sur Telegram
    """
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info(f"🚀 Analyse démarrée — {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    try:
        # ── 1. Récupération des données ───────────────────────────────────────
        logger.info("📥 Téléchargement des données Forex…")
        all_data = fetch_all_pairs()

        if not all_data:
            logger.error("❌ Aucune donnée récupérée")
            send_error_message("Impossible de récupérer les données Forex")
            return

        # ── 2-4. Traitement par paire ─────────────────────────────────────────
        signals = []
        for symbol, df in all_data.items():
            pair_name = config.PAIR_NAMES.get(symbol, symbol)
            logger.info(f"\n📊 Traitement de {pair_name}…")

            try:
                # Indicateurs techniques
                df_ind = compute_all_indicators(df)
                if df_ind.empty:
                    logger.warning(f"⚠️  {pair_name}: pas assez de données pour les indicateurs")
                    continue

                # Prédiction TimesFM
                price_series = prepare_timesfm_input(df)
                predictions  = predict_timesfm(price_series)

                # Génération du signal
                signal = generate_signal(symbol, df_ind, predictions)
                if signal:
                    signals.append(signal)

            except Exception as e:
                logger.error(f"❌ Erreur {pair_name}: {e}")
                continue

        # ── 5. Envoi Telegram ─────────────────────────────────────────────────
        if signals:
            logger.info(f"\n📲 Envoi de {len(signals)} signaux sur Telegram…")
            
            # Résumé global
            send_signals_summary(signals)
            time.sleep(1)

            # Signaux forts individuels
            strong_signals = [s for s in signals if s.is_strong and s.signal != "HOLD"]
            for s in strong_signals:
                send_signal(s)
                time.sleep(0.5)

            logger.info(f"✅ {len(signals)} signaux envoyés ({len(strong_signals)} forts)")
        else:
            logger.warning("⚠️  Aucun signal généré pour cette itération")

    except Exception as e:
        logger.error(f"❌ Erreur critique: {e}", exc_info=True)
        try:
            send_error_message(f"Erreur critique: {str(e)}")
        except Exception:
            pass

    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")


def main():
    """Point d'entrée principal."""
    logger.info("╔══════════════════════════════════════════════╗")
    logger.info("║     🤖 BOT SIGNAUX FOREX — TimesFM + AI      ║")
    logger.info("║         github.com/Taxi77777                 ║")
    logger.info("╚══════════════════════════════════════════════╝")

    # Vérification configuration
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN manquant dans .env — arrêt du bot")
        sys.exit(1)
    if not config.TELEGRAM_CHAT_ID:
        logger.error("❌ TELEGRAM_CHAT_ID manquant dans .env — arrêt du bot")
        sys.exit(1)

    logger.info(f"✅ Configuration OK")
    logger.info(f"📊 Paires: {', '.join(config.PAIR_NAMES.values())}")
    logger.info(f"🔄 Fréquence: toutes les {config.SIGNAL_FREQUENCY_HOURS}h")
    logger.info(f"🧠 TimesFM: {'activé' if config.USE_TIMESFM else 'désactivé (fallback)'}")

    # Notification de démarrage
    send_startup_message()

    # Première analyse immédiate
    logger.info("\n▶️  Première analyse en cours…")
    run_analysis()

    # Planification des analyses récurrentes
    freq = config.SIGNAL_FREQUENCY_HOURS
    schedule.every(freq).hours.do(run_analysis)
    logger.info(f"⏱️  Prochaine analyse dans {freq}h — boucle active")

    # Boucle infinie
    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        logger.info("\n🛑 Bot arrêté par l'utilisateur")
        send_message_safe("🛑 *Bot Forex arrêté*\n_À bientôt !_")


def send_message_safe(text: str):
    """Envoi de message sans lever d'exception."""
    try:
        from src.telegram_bot import send_message
        send_message(text)
    except Exception:
        pass


if __name__ == "__main__":
    main()
