"""
src/telegram_bot.py — Envoi des signaux de trading sur Telegram
"""

import logging
import asyncio
from datetime import datetime, timezone
import pytz
from telegram import Bot
from telegram.constants import ParseMode
import config
from src.signal_generator import TradingSignal

logger = logging.getLogger(__name__)

PARIS_TZ = pytz.timezone("Europe/Paris")


def _signal_emoji(signal: str) -> str:
    """Retourne l'emoji correspondant au signal."""
    return {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}.get(signal, "⚪")


def _confidence_bar(confidence: int) -> str:
    """Génère une barre de progression ASCII pour la confiance."""
    filled = int(confidence / 10)
    empty  = 10 - filled
    return "█" * filled + "░" * empty


def format_signal_message(signal: TradingSignal) -> str:
    """
    Formate un signal de trading en message Telegram stylisé.
    
    Args:
        signal: TradingSignal généré
    
    Returns:
        Message Telegram formaté (Markdown)
    """
    emoji      = _signal_emoji(signal.signal)
    conf_bar   = _confidence_bar(signal.confidence)
    now_paris  = datetime.now(PARIS_TZ)
    time_str   = now_paris.strftime("%d/%m/%Y %H:%M")
    strong_tag = " 🔥 *SIGNAL FORT*" if signal.is_strong else ""

    if signal.signal == "HOLD":
        tf_tag = f" ({signal.timeframe.upper()})" if hasattr(signal, "timeframe") else ""
        return (
            f"⏸️ *SIGNAL FOREX — {signal.pair_name}{tf_tag}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Signal     : {emoji} *HOLD* — Pas d'entrée recommandée\n"
            f"💰 Prix actuel: `{signal.current_price}`\n"
            f"📉 Confiance  : `{conf_bar}` {signal.confidence}%\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"RSI     : `{signal.rsi}` {signal.rsi_status}\n"
            f"MACD    : {signal.macd_trend}\n"
            f"Tendance IA: Neutre ↔️\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ {time_str} (Paris)\n"
            f"⚠️ _Usage éducatif uniquement_"
        )

    tp_sign = "+" if signal.signal == "BUY" else "-"
    sl_sign = "-" if signal.signal == "BUY" else "+"
    sl_text = "Aucun" if signal.stop_loss == "Aucun" else f"`{signal.stop_loss}` ({sl_sign}{signal.sl_pct}%)"

    tf_tag = f" ({signal.timeframe.upper()})" if hasattr(signal, "timeframe") else ""
    return (
        f"{emoji} *SIGNAL FOREX — {signal.pair_name}{tf_tag}*{strong_tag}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Signal     : {emoji} *{signal.signal}*\n"
        f"💰 Prix actuel: `{signal.current_price}`\n"
        f"🎯 Take Profit: `{signal.take_profit}` ({tp_sign}{signal.tp_pct}%)\n"
        f"🛑 Stop Loss  : {sl_text}\n"
        f"📈 Confiance  : `{conf_bar}` {signal.confidence}%\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"RSI     : `{signal.rsi}` {signal.rsi_status}\n"
        f"Fisher  : `{signal.fisher:+.2f}` {signal.fisher_status}\n"
        f"MACD    : {signal.macd_trend}\n"
        f"EMA 20/50: {signal.ema_trend}\n"
        f"Bollinger : {signal.bb_position}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ {time_str} (Paris)\n"
        f"⚠️ _Usage éducatif uniquement_"
    )


def format_summary_message(signals: list[TradingSignal]) -> str:
    """
    Formate un résumé de tous les signaux en un seul message.
    
    Args:
        signals: Liste de TradingSignal
    
    Returns:
        Message Telegram de résumé
    """
    now_paris = datetime.now(PARIS_TZ)
    time_str  = now_paris.strftime("%d/%m/%Y %H:%M")

    lines = [
        f"📊 *RÉSUMÉ FOREX — {time_str}*",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    for s in signals:
        emoji = _signal_emoji(s.signal)
        strong = " 🔥" if s.is_strong else ""
        tf_tag = f" ({s.timeframe.upper()})" if hasattr(s, "timeframe") else ""
        if s.signal != "HOLD":
            lines.append(
                f"{emoji} *{s.pair_name}{tf_tag}* — {s.signal}{strong} | "
                f"`{s.current_price}` → TP `{s.take_profit}` | Conf: {s.confidence}%"
            )
        else:
            lines.append(f"⏸️ *{s.pair_name}{tf_tag}* — HOLD | {s.confidence}%")

    buy_count  = sum(1 for s in signals if s.signal == "BUY")
    sell_count = sum(1 for s in signals if s.signal == "SELL")
    hold_count = sum(1 for s in signals if s.signal == "HOLD")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🟢 BUY: {buy_count}  🔴 SELL: {sell_count}  🟡 HOLD: {hold_count}",
        f"🤖 _Propulsé par Google TimesFM_",
        f"⚠️ _Éducatif — Pas de conseil financier_",
    ]

    return "\n".join(lines)


async def send_message_async(text: str, chat_id: str = None) -> bool:
    """
    Envoie un message Telegram de manière asynchrone.
    
    Args:
        text: Texte du message (Markdown)
        chat_id: ID du canal ou groupe ciblé (sinon config.TELEGRAM_CHAT_ID par défaut)
    
    Returns:
        True si succès, False sinon
    """
    target_chat = chat_id if chat_id else config.TELEGRAM_CHAT_ID
    if not config.TELEGRAM_BOT_TOKEN or not target_chat:
        logger.error("❌ Telegram: TOKEN ou CHAT_ID manquant")
        return False

    try:
        bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
        await bot.send_message(
            chat_id=target_chat,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
        )
        logger.info("✅ Message Telegram envoyé")
        return True
    except Exception as e:
        logger.error(f"❌ Erreur envoi Telegram: {e}")
        return False


def send_message(text: str, chat_id: str = None) -> bool:
    """
    Wrapper synchrone pour envoyer un message Telegram.
    
    Args:
        text: Texte du message
        chat_id: ID du canal ou groupe ciblé
    
    Returns:
        True si succès, False sinon
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, send_message_async(text, chat_id=chat_id))
                return future.result()
        else:
            return loop.run_until_complete(send_message_async(text, chat_id=chat_id))
    except Exception:
        return asyncio.run(send_message_async(text, chat_id=chat_id))


def send_signal(signal: TradingSignal) -> bool:
    """
    Envoie un signal individuel sur Telegram.
    
    Args:
        signal: TradingSignal à envoyer
    
    Returns:
        True si succès, False sinon
    """
    msg = format_signal_message(signal)
    return send_message(msg)


def send_signals_summary(signals: list[TradingSignal]) -> bool:
    """
    Envoie un résumé de tous les signaux sur Telegram.
    
    Args:
        signals: Liste de signaux
    
    Returns:
        True si succès, False sinon
    """
    if not signals:
        return False
    msg = format_summary_message(signals)
    return send_message(msg)


def send_startup_message() -> bool:
    """Envoie une notification de démarrage du bot."""
    now_paris = datetime.now(PARIS_TZ).strftime("%d/%m/%Y %H:%M")
    msg = (
        "🤖 *Bot Forex Signals — Démarrage*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ Bot démarré avec succès !\n"
        f"⏰ {now_paris} (Paris)\n"
        f"📊 Paires surveillées: {len(config.FOREX_PAIRS)}\n"
        f"🔄 Fréquence: toutes les {config.SIGNAL_FREQUENCY_HOURS}h\n"
        f"🧠 TimesFM: {'Activé ✅' if config.USE_TIMESFM else 'Désactivé ❌'}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "_Premier signal dans quelques instants…_"
    )
    return send_message(msg)


def send_error_message(error: str) -> bool:
    """Envoie une notification d'erreur sur Telegram."""
    msg = (
        f"⚠️ *Erreur Bot Forex*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"`{error[:500]}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"_Le bot continue de fonctionner…_"
    )
    return send_message(msg)
