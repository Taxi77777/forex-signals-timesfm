"""
interactive_bot.py — Bot Telegram interactif fonctionnant 24h/24.
Répond aux commandes :
/start - Message d'accueil
/liste - Liste des devises disponibles
/predit [PAIRE] - Lance une prédiction TimesFM immédiate (ex: /predit EURUSD)
"""

import logging
import os
import sys
import io
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Configuration du logging en UTF-8
os.makedirs("logs", exist_ok=True)
console_handler = logging.StreamHandler(
    io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
)
console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s"))
file_handler = logging.FileHandler("logs/interactive.log", encoding="utf-8")
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s"))

logging.basicConfig(level=logging.INFO, handlers=[console_handler, file_handler])
logger = logging.getLogger(__name__)

import config
from src.data_fetcher     import fetch_forex_data, prepare_timesfm_input
from src.indicators       import compute_all_indicators
from src.timesfm_predictor import predict_timesfm
from src.signal_generator  import generate_signal
from src.telegram_bot      import format_signal_message


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start"""
    welcome_text = (
        "🤖 *Bot Forex Interactif - Google TimesFM*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Bienvenue ! Tu peux me demander des prédictions en direct.\n\n"
        "⚙️ *Commandes disponibles :*\n"
        "👉 `/liste` : Voir toutes les devises disponibles\n"
        "👉 `/predit EURUSD` : Prédire une devise immédiatement\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "_Propulsé par Google TimesFM 2.5_"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


async def liste_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /liste"""
    pairs = [config.PAIR_NAMES.get(p, p) for p in config.FOREX_PAIRS]
    pairs_text = "\n".join([f"• `{p}`" for p in pairs])
    
    msg = (
        "📊 *Devises disponibles pour prédiction :*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{pairs_text}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 _Tape par exemple :_ `/predit EURUSD`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def predit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /predit [PAIRE]"""
    # Vérifier l'argument
    if not context.args:
        await update.message.reply_text(
            "⚠️ *Usage correct :* `/predit EURUSD` ou `/predit GBPUSD`",
            parse_mode="Markdown"
        )
        return

    raw_pair = context.args[0].upper().replace("/", "").replace("-", "")
    
    # Trouver le symbole Yahoo correspondant
    symbol = None
    if raw_pair + "=X" in config.FOREX_PAIRS:
        symbol = raw_pair + "=X"
    elif raw_pair == "JPY" or raw_pair == "USDJPY":
        symbol = "JPY=X"
    elif raw_pair == "MXN" or raw_pair == "USDMXN":
        symbol = "MXN=X"
    elif raw_pair == "CAD" or raw_pair == "USDCAD":
        symbol = "CAD=X"
    elif raw_pair == "CHF" or raw_pair == "USDCHF":
        symbol = "CHF=X"
    else:
        # Recherche par correspondance partielle
        for p in config.FOREX_PAIRS:
            clean_p = p.replace("=X", "")
            if raw_pair in clean_p or clean_p in raw_pair:
                symbol = p
                break

    if not symbol:
        await update.message.reply_text(
            f"❌ Paire `{raw_pair}` inconnue.\nTape `/liste` pour voir les devises disponibles.",
            parse_mode="Markdown"
        )
        return

    pair_name = config.PAIR_NAMES.get(symbol, symbol)
    loading_msg = await update.message.reply_text(
        f"⏳ *Analyse et prédiction IA en cours pour {pair_name}...*\n_(Cela peut prendre 10-15 secondes)_",
        parse_mode="Markdown"
    )

    try:
        # 1. Télécharger données
        df = fetch_forex_data(symbol, period="60d", interval="1h")
        if df.empty:
            await loading_msg.edit_text("❌ Impossible de récupérer les données du marché.")
            return

        # 2. Indicateurs
        df_ind = compute_all_indicators(df)
        if df_ind.empty:
            await loading_msg.edit_text("❌ Erreur lors du calcul des indicateurs.")
            return

        # 3. Prédiction TimesFM
        price_series = prepare_timesfm_input(df)
        predictions = predict_timesfm(price_series)

        # 4. Signal
        signal = generate_signal(symbol, df_ind, predictions)
        if not signal:
            await loading_msg.edit_text("❌ Impossible de générer le signal de trading.")
            return

        # 5. Formater et renvoyer le message
        response_msg = format_signal_message(signal)
        await loading_msg.delete()
        await update.message.reply_text(response_msg, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Erreur commande /predit pour {pair_name}: {e}", exc_info=True)
        await loading_msg.edit_text(f"❌ Une erreur est survenue lors de l'analyse : `{str(e)[:100]}`")


def main():
    token = config.TELEGRAM_BOT_TOKEN
    if not token or token == "METS_TON_TOKEN_ICI":
        logger.error("Token Telegram manquant dans .env !")
        sys.exit(1)

    logger.info("Démarrage du bot Telegram Interactif...")
    
    # Création de l'application Telegram
    app = Application.builder().token(token).build()

    # Ajout des gestionnaires de commandes
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("liste", liste_command))
    app.add_handler(CommandHandler("predit", predit_command))

    logger.info("Bot en ligne et à l'écoute des commandes !")
    app.run_polling()


if __name__ == "__main__":
    main()
