import aiogram
import asyncio
import aiocryptopay
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from aiocryptopay import AioCryptoPay, Networks

bf_token = 'bot_father_token'
crypto_pay_api = 'crypto_pay_api'

bot = Bot(token=bf_token)
crypto = AioCryptoPay(token=crypto_pay_api, network=Networks.TEST_NET) # testnet wallet!!!
dp = Dispatcher(bot)

inline_kb = InlineKeyboardMarkup()

# Добавляем кнопки с товарами и их ценами
inline_kb.add(InlineKeyboardButton('Товар 1 - 0.99', callback_data='buy:1'))
inline_kb.add(InlineKeyboardButton('Товар 2 - 0.01', callback_data='buy:2'))

# Создаем обработчик команды /start, который будет отображать клавиатуру
@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    await message.reply("Выберите товар:", reply_markup=inline_kb)

# Создаем обработчики для кнопок
@dp.callback_query_handler(lambda c: c.data and c.data.startswith('buy:'))
async def process_callback_button1(callback_query: types.CallbackQuery):
    code = callback_query.data[4:]
    if code == '1':
        price = 0.99
    elif code == '2':
        price = 0.01
    else:
        await bot.answer_callback_query(callback_query.id)
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
                await bot.send_message(callback_query.from_user.id, 'Спасибо за покупку!')
                return
        # Пауза перед следующей проверкой статуса
        await asyncio.sleep(5)
        

# Запускаем лонг поллинг
if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)