# 📊 Forex Trading Signals with TimesFM + Telegram

> Bot de signaux de trading Forex utilisant le modèle IA **Google TimesFM** envoyant des alertes automatiques sur **Telegram**.

---

## 🚀 Fonctionnalités

- 📈 **Prédiction** des paires majeures EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CAD, USD/CHF, NZD/USD
- 🤖 **Signaux automatiques** : BUY / SELL / HOLD
- 📲 **Alertes Telegram** toutes les heures
- 📊 **Indicateurs techniques** : RSI, MACD, ATR, Bollinger Bands
- 🧠 **IA TimesFM** de Google Research pour la prédiction
- ⚡ **Déploiement facile** sur serveur ou localement

---

## 📋 Paires surveillées

| Paire | Description |
|-------|-------------|
| EUR/USD | Euro / Dollar US |
| GBP/USD | Livre Sterling / Dollar US |
| USD/JPY | Dollar US / Yen Japonais |
| AUD/USD | Dollar Australien / Dollar US |
| USD/CAD | Dollar US / Dollar Canadien |
| USD/CHF | Dollar US / Franc Suisse |
| NZD/USD | Dollar Néo-Zélandais / Dollar US |

---

## ⚙️ Installation

### 1. Cloner le dépôt
```bash
git clone https://github.com/Taxi77777/forex-signals-timesfm.git
cd forex-signals-timesfm
```

### 2. Installer les dépendances
```bash
pip install -r requirements.txt
```

### 3. Configurer les variables d'environnement
```bash
cp .env.example .env
```
Édite `.env` avec tes credentials :
```
TELEGRAM_BOT_TOKEN=ton_token_ici
TELEGRAM_CHAT_ID=ton_chat_id_ici
```

### 4. Lancer le bot
```bash
python main.py
```

---

## 🗂️ Structure du projet

```
forex-signals-timesfm/
├── main.py                 # Point d'entrée principal
├── config.py               # Configuration globale
├── requirements.txt        # Dépendances Python
├── .env.example            # Template variables d'environnement
├── .env                    # Variables privées (non commité)
├── .gitignore
├── src/
│   ├── data_fetcher.py     # Récupération données Forex (yfinance)
│   ├── timesfm_predictor.py # Prédictions TimesFM
│   ├── indicators.py       # Indicateurs techniques (RSI, MACD...)
│   ├── signal_generator.py # Génération des signaux BUY/SELL
│   └── telegram_bot.py     # Envoi messages Telegram
├── logs/
│   └── signals.log         # Historique des signaux
└── README.md
```

---

## 📲 Format des signaux Telegram

```
🔔 SIGNAL FOREX — EUR/USD
━━━━━━━━━━━━━━━━━━━━━━━━
📊 Signal    : 🟢 BUY
💰 Prix actuel: 1.08542
🎯 Take Profit: 1.09120 (+0.54%)
🛑 Stop Loss  : 1.08200 (-0.32%)
📈 Confiance  : 78%
━━━━━━━━━━━━━━━━━━━━━━━━
RSI    : 42.3 (Survente)
MACD   : Haussier ↑
Tendance IA: Hausse sur 4h
━━━━━━━━━━━━━━━━━━━━━━━━
⏰ 14/07/2026 19:00 UTC
⚠️ Usage éducatif uniquement
```

---

## ⚠️ Avertissement

> Ce bot est développé à des fins **éducatives et de recherche**. Les signaux ne constituent pas des conseils financiers. Le trading Forex comporte des risques significatifs de perte en capital. Utilisez toujours votre propre jugement.

---

## 📄 Licence

MIT License — © 2026 Taxi77777
