import aiogram
import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiocryptopay import AioCryptoPay, Networks

bf_token = '6741685282:AAF6dyGeM6QwzRIr64fo0dwZT0JoJOQyQbg'
crypto_pay_api = '10852:AAkaS1sBaieyVRnkrK9o0MCt6WSLvsvEH8W'

bot = Bot(token=bf_token)
crypto = AioCryptoPay(token=crypto_pay_api, network=Networks.TEST_NET)
dp = Dispatcher(bot)

inline_kb = InlineKeyboardMarkup()

# Добавляем кнопки с товарами и их ценами
inline_kb.add(InlineKeyboardButton('Товар 1 - 0.99', callback_data='buy:1'))
inline_kb.add(InlineKeyboardButton('Товар 2 - 0.05', callback_data='buy:2'))

async def check_product(db_path, product_id):
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.cursor()
        # Проверяем наличие ключей для данного товара
        await cursor.execute(f"SELECT key FROM goods{product_id}")
        keys = await cursor.fetchall()
        if keys:
            # Если ключи есть, возвращаем один из них
            return keys[0][0]
        else:
            # Если ключей нет, сообщаем об этом
            return "Товара нет"

async def delete_key(db_path, product_id, key):
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.cursor()
        await cursor.execute(f"DELETE FROM goods{product_id} WHERE key = ?", (key,))
        await db.commit()

@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    await message.reply("Привет! Я ваш бот. Нажмите на кнопку, чтобы купить товар.", reply_markup=inline_kb)

lock = asyncio.Lock()

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
    async with lock:
        key = await check_product('goods.db', code)
        if key == "Товара нет":
            await bot.send_message(callback_query.from_user.id, 'Товара нет')
            return

        await bot.answer_callback_query(callback_query.id, text=f'Вы выбрали товар {code}. Цена: {price}')
        fiat_invoice = await crypto.create_invoice(amount=price, fiat='USD', currency_type='fiat')

    # Добавляем message_id в callback_data кнопки отмены
    cancel_kb = InlineKeyboardMarkup()
    cancel_kb.add(InlineKeyboardButton('Отменить оплату', callback_data=f'cancel:{fiat_invoice.invoice_id}'))

    # Сохраняем message_id сообщения с запросом об оплате
    payment_message = await bot.send_message(callback_query.from_user.id, 'Оплатите счет на сумму ' + str(fiat_invoice.amount) + ' USD по ссылке ' + fiat_invoice.bot_invoice_url, reply_markup=cancel_kb)
    payment_message_id = payment_message.message_id

    # Обновляем callback_data кнопки отмены с добавлением message_id
    cancel_kb = InlineKeyboardMarkup()
    cancel_kb.add(InlineKeyboardButton('Отменить оплату', callback_data=f'cancel:{fiat_invoice.invoice_id}:{payment_message_id}'))

    await bot.edit_message_reply_markup(chat_id=callback_query.from_user.id, message_id=payment_message_id, reply_markup=cancel_kb)

    try :
        # Проверяем статус счета в течение 15 минут
        await asyncio.wait_for(check_invoice_status(fiat_invoice, callback_query, code), timeout=900)
    except asyncio.TimeoutError:
        await bot.send_message(callback_query.from_user.id, 'Время ожидания оплаты истекло')
        
    # Проверяем статус счета
    async def check_invoice_status(fiat_invoice, callback_query, code):
        while True:
            await asyncio.sleep(5)
            invoice = await crypto.get_invoice(invoice_id=fiat_invoice.invoice_id)
            if invoice.status == 'paid':
                # Если счет оплачен, отправляем товар
                await bot.send_message(callback_query.from_user.id, 'Ваш товар: ' + key)
                await delete_key('goods.db', code, key)
                break
            elif invoice.status == 'expired':
                # Если счет не оплачен, сообщаем об этом
                await bot.send_message(callback_query.from_user.id, 'Время ожидания оплаты истекло')
                break

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('cancel:'))
async def process_cancel_button(callback_query: types.CallbackQuery):
    # Извлекаем message_id из callback_data
    _, invoice_id, message_id = callback_query.data.split(':')

    # Удаляем сообщение с запросом об оплате
    await bot.delete_message(chat_id=callback_query.from_user.id, message_id=message_id)

    invoice_id = callback_query.data.split(':')[1]
    await crypto.delete_invoice(invoice_id=invoice_id)
    await bot.answer_callback_query(callback_query.id, text='Оплата отменена')

# Запускаем
if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)