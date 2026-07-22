//+------------------------------------------------------------------+
//|                                   ForexAI_Signal_Receiver.mq4   |
//|               Copyright 2026, Taxi77777 Forex AI Bot             |
//|    Expert Advisor MT4 d'exécution automatique via signals.json   |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Taxi77777 Forex AI"
#property link      "https://github.com/Taxi77777/forex-signals-timesfm"
#property version   "1.00"
#property strict

//--- Inputs Utilisateur
input string   InpJsonUrl        = "https://raw.githubusercontent.com/Taxi77777/forex-signals-timesfm/main/signals.json"; // URL du fichier signals.json sur GitHub
input double   InpRiskPercent    = 1.0;             // Risque % par trade (ex: 1.0 = 1%)
input double   InpFixedLot       = 0.0;             // Lot Fixe (si 0.0 -> utilise InpRiskPercent)
input int      InpMaxOpenTrades  = 3;               // Nombre max de positions ouvertes en même temps
input int      InpMagicNumber    = 77777;           // Magic Number identifiant le Bot
input int      InpCheckInterval  = 10;              // Fréquence de vérification GitHub (en secondes)
input bool     InpUseTrailing    = true;            // Activer le Trailing Stop automatique
input int      InpTrailingPips   = 15;              // Pips de Trailing Stop

//--- Variables Globales
datetime g_lastCheckTime = 0;
string   g_processedTimestamp = "";

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("🤖 ForexAI Signal Receiver initialisé avec succès !");
   Print("🌐 Surveillance de l'URL : ", InpJsonUrl);
   EventSetTimer(InpCheckInterval);
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   Comment("");
}

//+------------------------------------------------------------------+
//| Timer event function                                             |
//+------------------------------------------------------------------+
void OnTimer()
{
   CheckAndExecuteSignals();
   if(InpUseTrailing) ApplyTrailingStop();
}

//+------------------------------------------------------------------+
//| OnTick function                                                  |
//+------------------------------------------------------------------+
void OnTick()
{
   if(InpUseTrailing) ApplyTrailingStop();
}

//+------------------------------------------------------------------+
//| Télécharge et exécute les signaux depuis GitHub                  |
//+------------------------------------------------------------------+
void CheckAndExecuteSignals()
{
   string jsonContent = FetchJsonFromUrl(InpJsonUrl);
   if(jsonContent == "") return;

   string lastUpdate = ExtractJsonValue(jsonContent, "last_update");
   if(lastUpdate == "" || lastUpdate == g_processedTimestamp) return;

   g_processedTimestamp = lastUpdate;
   Print("⚡ Nouveau scan détecté depuis GitHub (Mise à jour : ", lastUpdate, ")");

   // Compter les positions ouvertes par notre Bot
   int currentOpen = CountOpenTrades();
   if(currentOpen >= InpMaxOpenTrades)
   {
      Print("⚠️ Limite max de trades atteinte (", currentOpen, "/", InpMaxOpenTrades, ").");
      return;
   }

   // Parser les signaux dans le JSON
   int pos = 0;
   while((pos = StringFind(jsonContent, "pair_name", pos)) != -1)
   {
      int endPos = StringFind(jsonContent, "}", pos);
      if(endPos == -1) break;

      string block = StringSubstr(jsonContent, pos, endPos - pos + 1);
      pos = endPos + 1;

      string pairName  = ExtractJsonValue(block, "pair_name");
      string signal    = ExtractJsonValue(block, "signal");
      string priceStr  = ExtractJsonValue(block, "current_price");
      string tpStr     = ExtractJsonValue(block, "take_profit");
      string slStr     = ExtractJsonValue(block, "stop_loss");

      if(signal != "BUY" && signal != "SELL") continue;

      string symbolMT4 = ConvertPairToMT4Symbol(pairName);
      if(symbolMT4 == "") continue;

      double tp = StringToDouble(tpStr);
      double sl = StringToDouble(slStr);

      if(!HasOpenTradeForSymbol(symbolMT4))
      {
         ExecuteTrade(symbolMT4, signal, sl, tp);
      }
   }
   
   UpdateHUD(lastUpdate);
}

//+------------------------------------------------------------------+
//| Effectue la requête WebRequest HTTP GET sur GitHub               |
//+------------------------------------------------------------------+
string FetchJsonFromUrl(string url)
{
   char result[];
   string resultHeaders;
   int res;
   
   ResetLastError();
   res = WebRequest("GET", url, NULL, NULL, 5000, result, 0, result, resultHeaders);

   if(res == 200)
   {
      return CharArrayToString(result);
   }
   else
   {
      if(res == -1)
      {
         Print("❌ WebRequest Erreur ", GetLastError(), ". Assurez-vous d'avoir ajouté l'URL 'https://raw.githubusercontent.com' dans MT4 (Outils -> Options -> Expert Advisors -> Autoriser WebRequest).");
      }
      return "";
   }
}

//+------------------------------------------------------------------+
//| Convertit 'EUR/USD' -> 'EURUSD' ou 'EURUSD.m' selon le courtier |
//+------------------------------------------------------------------+
string ConvertPairToMT4Symbol(string pairName)
{
   string clean = pairName;
   StringReplace(clean, "/", "");
   StringReplace(clean, "=X", "");
   
   if(SymbolSelect(clean, true)) return clean;
   if(SymbolSelect(clean + ".m", true)) return clean + ".m";
   if(SymbolSelect(clean + "m", true)) return clean + "m";
   if(SymbolSelect(clean + ".ecn", true)) return clean + ".ecn";
   if(SymbolSelect("r" + clean, true)) return "r" + clean;
   
   Print("⚠️ Symbole MT4 non trouvé pour la paire : ", pairName);
   return "";
}

//+------------------------------------------------------------------+
//| Ouvre un ordre Market (BUY / SELL) sur MT4                      |
//+------------------------------------------------------------------+
void ExecuteTrade(string symbol, string signal, double sl, double tp)
{
   int type = (signal == "BUY") ? OP_BUY : OP_SELL;
   double price = (type == OP_BUY) ? MarketInfo(symbol, MODE_ASK) : MarketInfo(symbol, MODE_BID);
   double lot = CalculateLotSize(symbol, price, sl);

   int ticket = OrderSend(symbol, type, lot, price, 3, sl, tp, "ForexAI GitHub Bot", InpMagicNumber, 0, (type == OP_BUY) ? clrGreen : clrRed);
   if(ticket > 0)
   {
      Print("✅ ORDRE OUVERT AVEC SUCCÈS ! Ticket: #", ticket, " | ", symbol, " ", signal, " ", lot, " Lots à ", price);
   }
   else
   {
      Print("❌ Échec d'ouverture d'ordre sur ", symbol, ". Erreur MT4: ", GetLastError());
   }
}

//+------------------------------------------------------------------+
//| Calcul dynamique de la taille de lot selon le risque %           |
//+------------------------------------------------------------------+
double CalculateLotSize(string symbol, double entryPrice, double slPrice)
{
   if(InpFixedLot > 0.0) return InpFixedLot;

   double riskAmount = AccountEquity() * (InpRiskPercent / 100.0);
   double pipsRisk = MathAbs(entryPrice - slPrice) / MarketInfo(symbol, MODE_POINT);
   if(pipsRisk <= 0) pipsRisk = 200; // Fallback 20 pips

   double tickValue = MarketInfo(symbol, MODE_TICKVALUE);
   if(tickValue <= 0) tickValue = 1.0;

   double lot = riskAmount / (pipsRisk * tickValue);
   double minLot = MarketInfo(symbol, MODE_MINLOT);
   double maxLot = MarketInfo(symbol, MODE_MAXLOT);
   double lotStep = MarketInfo(symbol, MODE_LOTSTEP);

   lot = MathFloor(lot / lotStep) * lotStep;
   if(lot < minLot) lot = minLot;
   if(lot > maxLot) lot = maxLot;

   return lot;
}

//+------------------------------------------------------------------+
//| Nombre de trades ouverts par ce bot                              |
//+------------------------------------------------------------------+
int CountOpenTrades()
{
   int count = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
      {
         if(OrderMagicNumber() == InpMagicNumber) count++;
      }
   }
   return count;
}

//+------------------------------------------------------------------+
//| Vérifie si un symbole est déjà en cours de trade                 |
//+------------------------------------------------------------------+
bool HasOpenTradeForSymbol(string symbol)
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
      {
         if(OrderMagicNumber() == InpMagicNumber && OrderSymbol() == symbol) return true;
      }
   }
   return false;
}

//+------------------------------------------------------------------+
//| Trailing Stop automatique                                        |
//+------------------------------------------------------------------+
void ApplyTrailingStop()
{
   double point = Point;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
      {
         if(OrderMagicNumber() == InpMagicNumber)
         {
            point = MarketInfo(OrderSymbol(), MODE_POINT);
            int digits = (int)MarketInfo(OrderSymbol(), MODE_DIGITS);
            double pipsMult = (digits == 3 || digits == 5) ? 10.0 : 1.0;
            double trailDist = InpTrailingPips * pipsMult * point;

            if(OrderType() == OP_BUY)
            {
               double bid = MarketInfo(OrderSymbol(), MODE_BID);
               if(bid - OrderOpenPrice() > trailDist)
               {
                  if(OrderStopLoss() < bid - trailDist)
                  {
                     OrderModify(OrderTicket(), OrderOpenPrice(), NormalizeDouble(bid - trailDist, digits), OrderTakeProfit(), 0, clrBlue);
                  }
               }
            }
            else if(OrderType() == OP_SELL)
            {
               double ask = MarketInfo(OrderSymbol(), MODE_ASK);
               if(OrderOpenPrice() - ask > trailDist)
               {
                  if(OrderStopLoss() == 0 || OrderStopLoss() > ask + trailDist)
                  {
                     OrderModify(OrderTicket(), OrderOpenPrice(), NormalizeDouble(ask + trailDist, digits), OrderTakeProfit(), 0, clrBlue);
                  }
               }
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Parse une valeur JSON par clé (ex: "pair_name")                 |
//+------------------------------------------------------------------+
string ExtractJsonValue(string json, string key)
{
   string searchKey = "\"" + key + "\":";
   int pos = StringFind(json, searchKey);
   if(pos == -1)
   {
      searchKey = "\"" + key + "\": ";
      pos = StringFind(json, searchKey);
      if(pos == -1) return "";
   }

   int start = pos + StringLen(searchKey);
   while(start < StringLen(json) && (StringSubstr(json, start, 1) == " " || StringSubstr(json, start, 1) == "\""))
   {
      start++;
   }

   int end = start;
   while(end < StringLen(json))
   {
      string c = StringSubstr(json, end, 1);
      if(c == "\"" || c == "," || c == "}" || c == "\n" || c == "\r") break;
      end++;
   }

   return StringSubstr(json, start, end - start);
}

//+------------------------------------------------------------------+
//| Affichage HUD sur le graphique                                   |
//+------------------------------------------------------------------+
void UpdateHUD(string lastUpdate)
{
   string hud = "🤖 === FOREX AI GITHUB EXECUTOR === 🤖\n";
   hud += "--------------------------------------\n";
   hud += "💼 Solde Compte   : " + DoubleToStr(AccountBalance(), 2) + " " + AccountCurrency() + "\n";
   hud += "📊 Équité Compte  : " + DoubleToStr(AccountEquity(), 2) + " " + AccountCurrency() + "\n";
   hud += "🎯 Open Trades    : " + IntegerToString(CountOpenTrades()) + " / " + IntegerToString(InpMaxOpenTrades) + "\n";
   hud += "📡 Dernier Scan   : " + lastUpdate + "\n";
   hud += "--------------------------------------\n";
   hud += "🌐 Status : CONNECTÉ À GITHUB ✅\n";
   Comment(hud);
}
