import os
import requests
import re
import logging
import google.generativeai as genai
import urllib3
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
from bs4 import BeautifulSoup

# Отключаем предупреждения о невалидном сертификате (для прототипа)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Настройки API
TELEGRAM_BOT_TOKEN = "8184665271:AAHaKGl4_gMqupv3XdIPpyE_IGKYpkwtRSM"
GEMINI_API_KEY = "AIzaSyANeHY9pIj82d3pUL6LLB5ffsORuE8Gk58"

# Устанавливаем API-ключ для Gemini
genai.configure(api_key=GEMINI_API_KEY)

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Функция для получения редкого слова через Gemini API
def get_rare_word():
    model = genai.GenerativeModel("gemini-pro")
    prompt = "Дай мне одно редкое русское слово. Без объяснений, только слово"
    
    response = model.generate_content(prompt)
    if response and response.text:
        return response.text.strip()
    return "Ошибка при получении слова"

# **Добавляем куки с `sid` авторизованного пользователя**
COOKIES = {
    "sid": "c0i4b22p13kjkh6vq98e1ve5g1"
}

# Функция очистки перевода
def clean_translation(text):
    """Удаляет скобки и лишние пробелы."""
    return re.sub(r"[\(\)]", "", text).strip()

# Функция для перевода слова на казахский через sozdik.kz
def translate_to_kazakh(word):
    url = f"https://sozdik.kz/translate/ru/kk/{word}/"

    for attempt in range(3):  # Делаем до 3 попыток, если лимит превышен
        try:
            response = requests.get(url, cookies=COOKIES, verify=False)

            # Проверяем, не вернул ли сайт JSON с ошибкой
            if response.headers.get("Content-Type") == "application/json":
                data = response.json()
                if data.get("result") == -90:  # Ошибка "Translations limit exceed"
                    print(f"Лимит запросов превышен, попытка {attempt+1}/3. Жду 5 секунд...")
                    time.sleep(5)
                    continue  # Пробуем снова

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                translations = []

                # 1️⃣ **Перевод в `<summary>` внутри `<a class="ig_local">`**
                for summary in soup.find_all("summary"):
                    for abbr in summary.find_all("abbr"):
                        abbr.extract()  # Удаляем ненужные <abbr>

                    explanation_tag = summary.find("em")
                    explanation = explanation_tag.text.strip() if explanation_tag else "Без пояснения"

                    if explanation_tag:
                        explanation_tag.extract()  # Удаляем <em>, чтобы оставить только перевод

                    # Извлекаем все слова внутри <a class="ig_local">
                    local_translations = [a.text.strip() for a in summary.find_all("a", class_="ig_local")]

                    if local_translations:
                        translations.append(f"{explanation}: {', '.join(local_translations)}")

                # 2️⃣ **Перевод в `<em>` внутри `<p>` (убираем скобки)**
                for p_tag in soup.find_all("p"):
                    em_tags = p_tag.find_all("em")
                    for em in em_tags:
                        translation = clean_translation(em.text)  # Убираем скобки
                        if translation:
                            translations.append(translation)

                # 3️⃣ **Перевод в `<p>` без `<abbr>`**
                for p_tag in soup.find_all("p"):
                    for abbr in p_tag.find_all("abbr"):
                        abbr.extract()  # Удаляем ненужные <abbr>

                    kazakh_translation = p_tag.text.strip()
                    if kazakh_translation:
                        translations.append(kazakh_translation)

                if translations:
                    return "\n".join(translations)

        except Exception as e:
            print(f"Ошибка при переводе на казахский: {e}")

    return "Перевод не найден"  # Если после 3 попыток ничего не нашли

# Функция для перевода слова на английский через WooordHunt
def translate_to_english(word):
    url = f"https://wooordhunt.ru/word/{word}"
    
    try:
        response = requests.get(url, verify=False)  # Отключаем проверку SSL-сертификата
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            translations = set()  # Используем множество для удаления дубликатов

            # 1️⃣ Поиск в <p class="t_inline"> (как в "Хлябь")
            p_tag = soup.find("p", class_="t_inline")
            if p_tag:
                words = p_tag.text.strip().split(", ")  # Разбиваем, если есть дубли
                translations.update(words[:1])  # Берём только первое слово

            # 2️⃣ Поиск всех <a> внутри <div id="wd_content">
            content_block = soup.find("div", id="wd_content", class_="ru_content")
            if content_block:
                for a_tag in content_block.find_all("a"):
                    word = a_tag.text.strip()
                    if word.isalpha():  # Фильтруем, чтобы брать только английские слова
                        translations.add(word)

            if translations:
                return ", ".join(sorted(translations))  # Сортируем для красоты

    except Exception as e:
        print(f"Ошибка при переводе на английский: {e}")

    return "Перевод не найден"

# Команда /word для отправки пользователю редкого слова
async def word(update: Update, context: CallbackContext) -> None:
    word_info = get_rare_word()
    
    word = word_info.strip()
    meaning = "Нет информации"

    kazakh_translation = translate_to_kazakh(word)
    english_translation = translate_to_english(word)
    
    message = (
        f"📖 *Слово дня:* {word.strip()}\n\n"
        f"📜 *Значение:* {meaning.strip()}\n"
        f"🇰🇿 *Перевод на казахский:* {kazakh_translation}\n"
        f"🇬🇧 *Перевод на английский:* {english_translation}"
    )
    
    await update.message.reply_text(message, parse_mode="Markdown")

# Запуск бота
def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("word", word))
    app.run_polling()

if __name__ == "__main__":
    main()