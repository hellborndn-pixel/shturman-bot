import telebot
import sqlite3
import pickle
import os
import time
from datetime import datetime, timedelta
from collections import defaultdict

# ========== НАСТРОЙКИ ==========
# Токен берется из переменных окружения на Railway
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    # Если нет переменной окружения, используем токен напрямую (для теста)
    BOT_TOKEN = "8388928810:AAGYUzHaKR2K16ywo47DCkfB5AcBiyL51is"

# ========== ХРАНИЛИЩЕ АКТИВНЫХ СДЕЛОК ==========
ACTIVE_TRADES_FILE = 'active_trades.pkl'

if os.path.exists(ACTIVE_TRADES_FILE):
    with open(ACTIVE_TRADES_FILE, 'rb') as f:
        active_trades = pickle.load(f)
else:
    active_trades = {}

def save_active_trades():
    with open(ACTIVE_TRADES_FILE, 'wb') as f:
        pickle.dump(active_trades, f)

# ========== РАБОТА С БАЗОЙ ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect('trading_stats.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS trades
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  date TEXT,
                  type TEXT,
                  entry_price REAL,
                  tp_price REAL,
                  sl_price REAL,
                  result REAL,
                  quality REAL,
                  balance REAL,
                  pnl REAL)''')
    conn.commit()
    conn.close()

def save_trade(trade_data):
    conn = sqlite3.connect('trading_stats.db')
    c = conn.cursor()
    c.execute('''INSERT INTO trades
                 (date, type, entry_price, tp_price, sl_price, result, quality, balance, pnl)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (trade_data['date'], trade_data['type'], trade_data['entry'],
               trade_data.get('tp'), trade_data.get('sl'), trade_data['result'],
               trade_data['quality'], trade_data.get('balance', 0), trade_data['pnl']))
    conn.commit()
    conn.close()

def get_today_stats():
    conn = sqlite3.connect('trading_stats.db')
    c = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')

    c.execute('''SELECT * FROM trades WHERE date LIKE ? ORDER BY id''', (f'{today}%',))
    trades = c.fetchall()

    if not trades:
        conn.close()
        return None

    total_pnl = sum(t[9] for t in trades)
    wins = sum(1 for t in trades if t[9] > 0)
    losses = sum(1 for t in trades if t[9] < 0)

    first_balance = trades[0][8] - trades[0][9]
    last_balance = trades[-1][8]

    best = max(trades, key=lambda x: x[9])
    worst = min(trades, key=lambda x: x[9])

    gross_profit = sum(t[9] for t in trades if t[9] > 0)
    gross_loss = abs(sum(t[9] for t in trades if t[9] < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else gross_profit

    conn.close()

    return {
        'date': today,
        'start_balance': first_balance,
        'end_balance': last_balance,
        'total_pnl': total_pnl,
        'trades': len(trades),
        'wins': wins,
        'losses': losses,
        'winrate': (wins / len(trades)) * 100 if trades else 0,
        'best': best,
        'worst': worst,
        'profit_factor': profit_factor
    }

def get_week_stats():
    conn = sqlite3.connect('trading_stats.db')
    c = conn.cursor()

    week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    c.execute('''SELECT * FROM trades WHERE date >= ? ORDER BY date''', (week_ago,))
    trades = c.fetchall()

    if not trades:
        conn.close()
        return None

    quality_stats = defaultdict(lambda: {'total': 0, 'wins': 0})
    for t in trades:
        quality = int(t[7]) // 10 * 10
        quality_stats[quality]['total'] += 1
        if t[9] > 0:
            quality_stats[quality]['wins'] += 1

    conn.close()

    return {
        'trades': len(trades),
        'wins': sum(1 for t in trades if t[9] > 0),
        'losses': sum(1 for t in trades if t[9] < 0),
        'total_pnl': sum(t[9] for t in trades),
        'quality_stats': quality_stats
    }

# ========== СОЗДАЕМ БОТА ==========
bot = telebot.TeleBot(BOT_TOKEN)

# ========== КОМАНДЫ ==========

@bot.message_handler(commands=['start'])
def start(message):
    text = """
🚀 <b>ШТУРМАН - ТОРГОВАЯ СИСТЕМА</b>

<b>УПРАВЛЕНИЕ СДЕЛКАМИ:</b>
/open [цена] - начать сделку
/close [цена] - закрыть сделку
/status - проверить активную сделку
/cancel - отменить сделку

<b>НАСТРОЙКИ СДЕЛКИ:</b>
/settp [цена] - установить тейк
/setsl [цена] - установить стоп
/setq [процент] - установить качество

<b>СТАТИСТИКА:</b>
/stats - статистика сегодня
/week - статистика за неделю
/balance - текущий баланс
/signals - последние 5 сигналов
/quality [процент] - сделки по качеству

<b>Статус:</b> РАБОТАЕТ 24/7 НА СЕРВЕРЕ 🚀
    """
    bot.reply_to(message, text, parse_mode='HTML')

@bot.message_handler(commands=['open'])
def open_trade(message):
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "❌ Напиши цену входа: /open 98.45")
            return

        entry_price = float(parts[1])

        active_trades[message.chat.id] = {
            'entry': entry_price,
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'quality': None,
            'tp': None,
            'sl': None
        }
        save_active_trades()

        text = f"""
✅ <b>СДЕЛКА ЗАПОМНЕНА!</b>
═══════════════════════
📈 ВХОД: ${entry_price:.4f}
⏰ Время: {active_trades[message.chat.id]['time']}
═══════════════════════
/close [цена] - закрыть сделку
/status - проверить
/settp [цена] - установить тейк
/setsl [цена] - установить стоп
/setq [процент] - качество
        """
        bot.reply_to(message, text, parse_mode='HTML')

    except ValueError:
        bot.reply_to(message, "❌ Неправильная цена. Пример: /open 98.45")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['close'])
def close_trade(message):
    try:
        chat_id = message.chat.id

        if chat_id not in active_trades:
            bot.reply_to(message, "❌ Нет активной сделки. Сначала /open")
            return

        trade = active_trades[chat_id]

        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "❌ Напиши цену закрытия: /close 100.12")
            return

        close_price = float(parts[1])

        entry = trade['entry']
        diff = close_price - entry
        diff_percent = (diff / entry) * 100

        if diff > 0:
            result_type = "✅ ТЕЙК ПРОФИТ"
            emoji = "✅"
        else:
            result_type = "❌ СТОП ЛОСС"
            emoji = "❌"

        # Получаем последний баланс из базы
        conn = sqlite3.connect('trading_stats.db')
        c = conn.cursor()
        c.execute('SELECT balance FROM trades ORDER BY id DESC LIMIT 1')
        last_balance = c.fetchone()
        current_balance = last_balance[0] if last_balance else 60.0
        conn.close()

        new_balance = current_balance + diff

        trade_data = {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'type': 'tp' if diff > 0 else 'sl',
            'entry': entry,
            'tp': close_price if diff > 0 else None,
            'sl': close_price if diff < 0 else None,
            'result': diff,
            'quality': trade.get('quality', 0),
            'balance': new_balance,
            'pnl': diff
        }
        save_trade(trade_data)

        text = f"""
{emoji} <b>{result_type}</b>
═══════════════════════
📈 ВХОД: ${entry:.4f}
📉 ВЫХОД: ${close_price:.4f}
═══════════════════════
💰 РЕЗУЛЬТАТ: {diff:+.2f}$ ({diff_percent:+.2f}%)
💵 НОВЫЙ БАЛАНС: ${new_balance:.2f}
═══════════════════════
📊 КАЧЕСТВО ВХОДА: {trade.get('quality', 'не указано')}%
        """
        bot.reply_to(message, text, parse_mode='HTML')

        del active_trades[chat_id]
        save_active_trades()

    except ValueError:
        bot.reply_to(message, "❌ Неправильная цена. Пример: /close 100.12")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['status'])
def trade_status(message):
    chat_id = message.chat.id

    if chat_id in active_trades:
        trade = active_trades[chat_id]
        text = f"""
📊 <b>АКТИВНАЯ СДЕЛКА</b>
═══════════════════════
📈 ВХОД: ${trade['entry']:.4f}
⏰ ВРЕМЯ: {trade['time']}
═══════════════════════
🎯 ТЕЙК: {f'${trade["tp"]:.4f}' if trade.get('tp') else 'не указан'}
🛑 СТОП: {f'${trade["sl"]:.4f}' if trade.get('sl') else 'не указан'}
📊 КАЧЕСТВО: {f'{trade["quality"]}%' if trade.get('quality') else 'не указано'}
═══════════════════════
/close [цена] - закрыть сделку
/cancel - отменить
        """
        bot.reply_to(message, text, parse_mode='HTML')
    else:
        bot.reply_to(message, "📭 Нет активных сделок. /open [цена]")

@bot.message_handler(commands=['settp'])
def set_tp(message):
    try:
        chat_id = message.chat.id
        if chat_id not in active_trades:
            bot.reply_to(message, "❌ Нет активной сделки")
            return

        tp_price = float(message.text.split()[1])
        active_trades[chat_id]['tp'] = tp_price
        save_active_trades()

        bot.reply_to(message, f"✅ ТЕЙК установлен: ${tp_price:.4f}")

    except:
        bot.reply_to(message, "❌ Используй: /settp 100.12")

@bot.message_handler(commands=['setsl'])
def set_sl(message):
    try:
        chat_id = message.chat.id
        if chat_id not in active_trades:
            bot.reply_to(message, "❌ Нет активной сделки")
            return

        sl_price = float(message.text.split()[1])
        active_trades[chat_id]['sl'] = sl_price
        save_active_trades()

        bot.reply_to(message, f"✅ СТОП установлен: ${sl_price:.4f}")

    except:
        bot.reply_to(message, "❌ Используй: /setsl 97.96")

@bot.message_handler(commands=['setq'])
def set_quality(message):
    try:
        chat_id = message.chat.id
        if chat_id not in active_trades:
            bot.reply_to(message, "❌ Нет активной сделки")
            return

        quality = int(message.text.split()[1])
        if 0 <= quality <= 100:
            active_trades[chat_id]['quality'] = quality
            save_active_trades()
            bot.reply_to(message, f"✅ КАЧЕСТВО установлено: {quality}%")
        else:
            bot.reply_to(message, "❌ Качество должно быть от 0 до 100")

    except:
        bot.reply_to(message, "❌ Используй: /setq 85")

@bot.message_handler(commands=['cancel'])
def cancel_trade(message):
    chat_id = message.chat.id
    if chat_id in active_trades:
        del active_trades[chat_id]
        save_active_trades()
        bot.reply_to(message, "❌ Сделка отменена")
    else:
        bot.reply_to(message, "📭 Нет активной сделки")

@bot.message_handler(commands=['stats'])
def stats(message):
    stats = get_today_stats()
    if stats:
        text = f"""
📊 <b>СТАТИСТИКА ДНЯ - {stats['date']}</b>
═══════════════════════
💰 НАЧАЛЬНЫЙ БАЛАНС: ${stats['start_balance']:.2f}
💵 ТЕКУЩИЙ БАЛАНС: ${stats['end_balance']:.2f}
📈 ПРОФИТ: {stats['total_pnl']:+.2f}$ ({((stats['end_balance']/stats['start_balance'])-1)*100:.1f}%)
═══════════════════════
📊 СДЕЛОК: {stats['trades']}
✅ ТЕЙКОВ: {stats['wins']} ({stats['winrate']:.0f}%)
❌ СТОПОВ: {stats['losses']} ({100-stats['winrate']:.0f}%)
═══════════════════════
🏆 ЛУЧШАЯ: +${stats['best'][9]:.2f} ({stats['best'][7]:.0f}% качество)
💔 ХУДШАЯ: {stats['worst'][9]:+.2f}$ ({stats['worst'][7]:.0f}% качество)
⚖️ ПРОФИТ-ФАКТОР: {stats['profit_factor']:.2f}
        """
        bot.reply_to(message, text, parse_mode='HTML')
    else:
        bot.reply_to(message, "📭 Сегодня еще не было сделок")

@bot.message_handler(commands=['week'])
def week(message):
    stats = get_week_stats()
    if stats:
        text = f"""
📈 <b>СТАТИСТИКА ЗА НЕДЕЛЮ</b>
═══════════════════════
📊 ВСЕГО СДЕЛОК: {stats['trades']}
✅ ПОБЕД: {stats['wins']} ({stats['wins']/stats['trades']*100:.0f}%)
❌ ПОРАЖЕНИЙ: {stats['losses']} ({stats['losses']/stats['trades']*100:.0f}%)
💰 ОБЩИЙ PNL: {stats['total_pnl']:+.2f}$
═══════════════════════
<b>ПО КАЧЕСТВУ:</b>
"""
        for quality, data in sorted(stats['quality_stats'].items()):
            winrate = (data['wins']/data['total'])*100 if data['total'] > 0 else 0
            emoji = '🟢' if winrate > 70 else '🟡' if winrate > 50 else '🔴'
            text += f"{emoji} {quality}-{quality+9}%: {data['wins']}/{data['total']} ({winrate:.0f}%)\n"

        bot.reply_to(message, text, parse_mode='HTML')
    else:
        bot.reply_to(message, "📭 Нет данных за неделю")

@bot.message_handler(commands=['balance'])
def balance(message):
    conn = sqlite3.connect('trading_stats.db')
    c = conn.cursor()
    c.execute('SELECT balance FROM trades ORDER BY id DESC LIMIT 1')
    last = c.fetchone()
    conn.close()

    if last:
        text = f"💰 <b>ТЕКУЩИЙ БАЛАНС:</b> ${last[0]:.2f}"
    else:
        text = "💰 <b>ТЕКУЩИЙ БАЛАНС:</b> $60.00 (начальный)"

    bot.reply_to(message, text, parse_mode='HTML')

@bot.message_handler(commands=['signals'])
def signals(message):
    conn = sqlite3.connect('trading_stats.db')
    c = conn.cursor()
    c.execute('SELECT date, type, entry_price, quality, pnl FROM trades ORDER BY id DESC LIMIT 5')
    trades = c.fetchall()
    conn.close()

    if trades:
        text = "📋 <b>ПОСЛЕДНИЕ 5 СИГНАЛОВ:</b>\n═══════════════════════\n"
        for t in trades:
            emoji = '✅' if t[4] > 0 else '❌'
            text += f"{emoji} {t[0][5:16]} | {t[2]:.4f} | {t[3]:.0f}% | {t[4]:+.2f}$\n"
        bot.reply_to(message, text, parse_mode='HTML')
    else:
        bot.reply_to(message, "📭 Нет данных")

@bot.message_handler(commands=['quality'])
def quality(message):
    try:
        args = message.text.split()[1]
        if '-' in args:
            min_q, max_q = map(int, args.split('-'))
        else:
            min_q = int(args)
            max_q = 100

        conn = sqlite3.connect('trading_stats.db')
        c = conn.cursor()
        c.execute('''SELECT date, entry_price, quality, pnl FROM trades
                     WHERE quality BETWEEN ? AND ? ORDER BY date DESC LIMIT 10''',
                  (min_q, max_q))
        trades = c.fetchall()
        conn.close()

        if trades:
            wins = sum(1 for t in trades if t[3] > 0)
            text = f"📊 <b>СДЕЛКИ {min_q}-{max_q}%:</b>\n═══════════════════════\n"
            text += f"✅ Винрейт: {wins}/{len(trades)} ({wins/len(trades)*100:.0f}%)\n"
            text += f"💰 Средний PNL: {sum(t[3] for t in trades)/len(trades):+.2f}$\n"
            text += "═══════════════════════\n"
            for t in trades[:5]:
                emoji = '✅' if t[3] > 0 else '❌'
                text += f"{emoji} {t[0][5:10]} | {t[1]:.4f} | {t[3]:+.2f}$\n"
        else:
            text = f"📭 Нет сделок с качеством {min_q}-{max_q}%"

        bot.reply_to(message, text, parse_mode='HTML')

    except:
        bot.reply_to(message, "❌ Используй: /quality 80 или /quality 60-80")

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    init_db()
    print("🚀 МАШИНА СМЕРТИ ЗАПУЩЕНА НА RAILWAY!")
    print("✅ Бот работает 24/7!")
    
    # Бесконечный цикл с перезапуском при ошибках
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            print("🔄 Перезапуск через 5 секунд...")
            time.sleep(5)
