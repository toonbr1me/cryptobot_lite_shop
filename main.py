import aiogram
import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiocryptopay import AioCryptoPay, Networks

bf_token = 'tg_bot_token'
crypto_pay_api = 'cb_api_key'

bot = Bot(token=bf_token)
crypto = AioCryptoPay(token=crypto_pay_api, network=Networks.TEST_NET)
dp = Dispatcher(bot)

inline_kb = InlineKeyboardMarkup()

# Добавляем кнопки с товарами и их ценами
inline_kb.add(InlineKeyboardButton('Товар 1 - 0.99', callback_data='buy:1'))
inline_kb.add(InlineKeyboardButton('Товар 2 - 0.05', callback_data='buy:2'))

async def buy_product(db_path, product_id, user_id):
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.cursor()
        # Проверяем наличие ключей для данного товара
        await cursor.execute(f"SELECT key FROM goods{product_id}")
        keys = await cursor.fetchall()
        if keys:
            # Если ключи есть, выдаем один из них
            key = keys[0][0]
            await cursor.execute(f"DELETE FROM goods{product_id} WHERE key = ?", (key,))
            await db.commit()
            return key
        else:
            # Если ключей нет, сообщаем об этом
            return "Товара нет"

@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    await message.reply("Выберите товар:", reply_markup=inline_kb)

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('buy:'))
async def process_callback_button1(callback_query: types.CallbackQuery):
    code = callback_query.data[4:]
    if code == '1':
        price = 0.99
    elif code == '2':
        price = 0.05
    else:
        await bot.answer_callback_query(callback_query.id)
        return

    # Проверяем наличие товара
    key = await buy_product('goods.db', code, callback_query.from_user.id)
    if key == "Товара нет":
        await bot.send_message(callback_query.from_user.id, 'Товара нет')
        return

    await bot.answer_callback_query(callback_query.id, text=f'Вы выбрали товар {code}. Цена: {price}')
    fiat_invoice = await crypto.create_invoice(amount=price, fiat='USD', currency_type='fiat')
    await bot.send_message(callback_query.from_user.id, 'Оплатите счет на сумму ' + str(fiat_invoice.amount) + ' USD по ссылке ' + fiat_invoice.bot_invoice_url)

    # Проверяем статус счета
    while True:
        invoices = await crypto.get_invoices(invoice_ids=[fiat_invoice.invoice_id])
        print(invoices)
        for invoice in invoices:
            if invoice.status == 'paid':
                await bot.send_message(callback_query.from_user.id, f'Спасибо за покупку товара {code}. Ваш ключ: {key}')
                return
        # Пауза перед следующей проверкой статуса
        await asyncio.sleep(5)

# Запускаем
if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)