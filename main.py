import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiocryptopay import AioCryptoPay, Networks

bf_token = 'Токен от бота'
crypto_pay_api = 'Токен от cryptopay'

bot = Bot(token=bf_token)
crypto = AioCryptoPay(token=crypto_pay_api, network=Networks.TEST_NET)
dp = Dispatcher(bot)

PRODUCT_NOT_AVAILABLE = "Товара нет"

inline_kb = InlineKeyboardMarkup()
inline_kb.add(InlineKeyboardButton('Товар 1 - 0.99', callback_data='buy:1'))
inline_kb.add(InlineKeyboardButton('Товар 2 - 0.05', callback_data='buy:2'))

lock = asyncio.Lock()

async def check_product(db_path, product_id):
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.cursor()
        await cursor.execute(f"SELECT key FROM goods{product_id}")
        keys = await cursor.fetchall()
        return keys[0][0] if keys else PRODUCT_NOT_AVAILABLE

async def delete_key(db_path, product_id, key):
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.cursor()
        await cursor.execute(f"DELETE FROM goods{product_id} WHERE key = ?", (key,))
        await db.commit()

async def create_cancel_button(invoice_id, message_id=None):
    callback_data = f'cancel:{invoice_id}:{message_id}' if message_id else f'cancel:{invoice_id}'
    cancel_kb = InlineKeyboardMarkup()
    cancel_kb.add(InlineKeyboardButton('Отменить оплату', callback_data=callback_data))
    return cancel_kb

async def check_invoice_status(fiat_invoice, callback_query, code):
    while True:
        await asyncio.sleep(5)
        invoice = await crypto.get_invoice(invoice_id=fiat_invoice.invoice_id)
        if invoice.status == 'paid':
            key = await check_product('goods.db', code)
            await bot.send_message(callback_query.from_user.id, 'Ваш товар: ' + key)
            await delete_key('goods.db', code, key)
            break
        elif invoice.status == 'expired':
            await bot.send_message(callback_query.from_user.id, 'Время ожидания оплаты истекло')
            break

@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    await message.reply("Привет! Я ваш бот. Нажмите на кнопку, чтобы купить товар.", reply_markup=inline_kb)

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('buy:'))
async def process_callback_button1(callback_query: types.CallbackQuery):
    code = callback_query.data[4:]
    price = 0.99 if code == '1' else 0.05 if code == '2' else None
    if price is None:
        await bot.answer_callback_query(callback_query.id)
        return

    async with lock:
        key = await check_product('goods.db', code)
        if key == PRODUCT_NOT_AVAILABLE:
            await bot.send_message(callback_query.from_user.id, PRODUCT_NOT_AVAILABLE)
            return

        await bot.answer_callback_query(callback_query.id, text=f'Вы выбрали товар {code}. Цена: {price}')
        fiat_invoice = await crypto.create_invoice(amount=price, fiat='USD', currency_type='fiat')

    cancel_kb = await create_cancel_button(fiat_invoice.invoice_id)
    payment_message = await bot.send_message(callback_query.from_user.id, 'Оплатите счет на сумму ' + str(fiat_invoice.amount) + ' USD по ссылке ' + fiat_invoice.bot_invoice_url, reply_markup=cancel_kb)
    payment_message_id = payment_message.message_id

    cancel_kb = await create_cancel_button(fiat_invoice.invoice_id, payment_message_id)
    await bot.edit_message_reply_markup(chat_id=callback_query.from_user.id, message_id=payment_message_id, reply_markup=cancel_kb)

    try :
        await asyncio.wait_for(check_invoice_status(fiat_invoice, callback_query, code), timeout=900)
    except asyncio.TimeoutError:
        await bot.send_message(callback_query.from_user.id, 'Время ожидания оплаты истекло')
        await crypto.delete_invoice(invoice_id=fiat_invoice.invoice_id)

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('cancel:'))
async def process_cancel_button(callback_query: types.CallbackQuery):
    _, invoice_id, message_id = callback_query.data.split(':')
    await bot.delete_message(chat_id=callback_query.from_user.id, message_id=message_id)
    await crypto.delete_invoice(invoice_id=invoice_id)
    await bot.answer_callback_query(callback_query.id, text='Оплата отменена')

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)