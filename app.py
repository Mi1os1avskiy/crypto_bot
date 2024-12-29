
import requests
import asyncio
from datetime import datetime, timedelta
from colorama import Fore, Style, init
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.error import TelegramError

# Initialize colorama
init(autoreset=True)

# Uniswap and SushiSwap API endpoints
UNISWAP_API = "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v2"
SUSHISWAP_API = "https://api.thegraph.com/subgraphs/name/sushiswap/exchange"

# Telegram Bot Token and Chat ID (updated with user-provided values)
TELEGRAM_BOT_TOKEN = "7679350299:AAETEqNp8vx9BFGAULUSrY23xFUYGtGihb8"
TELEGRAM_CHAT_ID = "279033187"

# Initialize Telegram Bot
bot = Bot(token=TELEGRAM_BOT_TOKEN)
application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# Global variable to track monitoring status
is_monitoring = False

# Function to query Uniswap prices
def get_uniswap_price(token0, token1):
    query = {
        "query": f"""
        {{
            pairs(where: {{ token0: \"{token0}\", token1: \"{token1}\" }}) {{
                token0Price
                token1Price
            }}
        }}
        """
    }
    try:
        response = requests.post(UNISWAP_API, json=query, timeout=10)
        response.raise_for_status()
        data = response.json()
        if 'data' in data and 'pairs' in data['data'] and data['data']['pairs']:
            pair_data = data['data']['pairs'][0]
            return float(pair_data['token0Price']), float(pair_data['token1Price'])
    except (requests.RequestException, KeyError, IndexError) as e:
        print(f"Error fetching data from Uniswap API: {e}")
    return None, None

# Function to query SushiSwap prices
def get_sushiswap_price(token0, token1):
    query = {
        "query": f"""
        {{
            pairs(where: {{ token0: \"{token0}\", token1: \"{token1}\" }}) {{
                token0Price
                token1Price
            }}
        }}
        """
    }
    try:
        response = requests.post(SUSHISWAP_API, json=query, timeout=10)
        response.raise_for_status()
        data = response.json()
        if 'data' in data and 'pairs' in data['data'] and data['data']['pairs']:
            pair_data = data['data']['pairs'][0]
            return float(pair_data['token0Price']), float(pair_data['token1Price'])
    except (requests.RequestException, KeyError, IndexError) as e:
        print(f"Error fetching data from SushiSwap API: {e}")
    return None, None

# Function to calculate arbitrage opportunity
def calculate_arbitrage_percentage(usdt_price_uniswap, usdt_price_sushiswap):
    # Calculate profit percentage
    if usdt_price_uniswap and usdt_price_sushiswap:
        return ((usdt_price_sushiswap - usdt_price_uniswap) / usdt_price_uniswap) * 100
    return 0

# Function to find the best arbitrage opportunity
def find_arbitrage_opportunities(tokens, base_token="USDT", seen_opportunities=None):
    best_opportunity = None
    current_time = datetime.now()
    if seen_opportunities is None:
        seen_opportunities = set()

    for token in tokens:
        if token == base_token:
            continue

        # Fetch prices from Uniswap and SushiSwap
        uniswap_price, _ = get_uniswap_price(base_token, token)
        sushiswap_price, _ = get_sushiswap_price(base_token, token)

        if uniswap_price and sushiswap_price:
            profit_percentage = calculate_arbitrage_percentage(uniswap_price, sushiswap_price)
            if profit_percentage > 0 and token not in seen_opportunities:
                opportunity = {
                    "token": token,
                    "profit_percentage": profit_percentage,
                    "uniswap_price": uniswap_price,
                    "sushiswap_price": sushiswap_price,
                    "time_start": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "time_end": (current_time + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
                }
                seen_opportunities.add(token)
                if not best_opportunity or profit_percentage > best_opportunity["profit_percentage"]:
                    best_opportunity = opportunity

    return best_opportunity

# Async function to send Telegram notification
async def send_telegram_message(message):
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except TelegramError as e:
        print(f"Error sending message via Telegram: {e}")

# Continuous monitoring function
async def monitor_arbitrage(tokens, base_token="USDT", interval=60, min_profit=0.1):
    global is_monitoring
    is_monitoring = True
    start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await send_telegram_message(f"✅ Monitoring started at {start_time}.")
    print("Starting arbitrage monitoring...")
    seen_opportunities = set()
    last_no_opportunity_time = datetime.now()

    try:
        best_opportunity = find_arbitrage_opportunities(tokens, base_token, seen_opportunities)
        if not best_opportunity:
            print(Fore.YELLOW + "No arbitrage opportunities found during initial check.")
        while True:
            best_opportunity = find_arbitrage_opportunities(tokens, base_token, seen_opportunities)

            if best_opportunity and best_opportunity["profit_percentage"] >= min_profit:
                message = (
                    f"💰 Arbitrage Opportunity Detected!"
                    f"Token to trade: {best_opportunity['token']}"
                    f"Profit: {best_opportunity['profit_percentage']:.2f}%"
                    f"Uniswap Price (USDT->{best_opportunity['token']}): {best_opportunity['uniswap_price']}"
                    f"SushiSwap Price (USDT->{best_opportunity['token']}): {best_opportunity['sushiswap_price']}"
                    f"Trade Window: {best_opportunity['time_start']} to {best_opportunity['time_end']}"
                    f"Suggested Action: Swap USDT->{best_opportunity['token']} on Uniswap, then {best_opportunity['token']}->USDT on SushiSwap"
                )
                print(Fore.GREEN + message)
                await send_telegram_message(message)
            else:
                current_time = datetime.now()
                if (current_time - last_no_opportunity_time).total_seconds() >= 3600:
                    no_opportunity_message = (
                        f"⚠ No arbitrage opportunities detected as of {current_time.strftime('%Y-%m-%d %H:%M:%S')}.")
                    print(Fore.YELLOW + no_opportunity_message)
                    last_no_opportunity_time = current_time

            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        stop_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await send_telegram_message(f"❌ Monitoring stopped at {stop_time}.")
        print(Fore.RED + f"Monitoring stopped at {stop_time}.")
        is_monitoring = False

# Command handlers for Telegram Bot
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_monitoring
    if is_monitoring:
        await update.message.reply_text("Monitoring is already running.")
    else:
        asyncio.create_task(monitor_arbitrage(tokens=[
            "DAI", "ETH", "WBTC", "LINK", "MATIC", "AAVE", "UNI", "COMP", "USDC", "YFI", "SUSHI", "SNX", "BAL", "CRV", "1INCH", "MKR"
        ]))  # Task создан
        is_monitoring = True  # Обновлено состояние
        await update.message.reply_text("Monitoring has started.")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_monitoring
    if is_monitoring:
        for task in asyncio.all_tasks():
            if task.get_coro().__name__ == "monitor_arbitrage":
                task.cancel()
        await update.message.reply_text("Monitoring has been stopped.")
    else:
        await update.message.reply_text("Monitoring is not running.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_monitoring
    if is_monitoring:
        await update.message.reply_text("✅ Monitoring is currently running.")
    else:
        await update.message.reply_text("❌ Monitoring is not running.")

# Main function
def main():
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("status", status))

    print("Starting the bot...")
    application.run_polling()

if __name__ == "__main__":
    main()
