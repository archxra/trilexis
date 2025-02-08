import os
import requests
import re
import json
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
    "sid": "q3opq07hg5e0v0mn41id0q60lc"
}

# Функция очистки перевода
def clean_translation(text):
    """Удаляет скобки и лишние пробелы."""
    return re.sub(r"[\(\)]", "", text).strip()

def parse_translation_arrow(text):
    """Парсит перевод после символа `→`"""
    if "→" in text:
        return text.split("→", 1)[1].strip()
    return None  # Если `→` нет, возвращаем `None`

def translate_to_kazakh(word):
    url = f"https://sozdik.kz/translate/ru/kk/{word}/"

    for attempt in range(3):
        try:
            response = requests.get(url, cookies=COOKIES, verify=False)

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")

                # 6️⃣ **Перевод в <summary> без <a>, где нужное слово не в теге**
                for summary in soup.find_all("summary"):
                    for abbr in summary.find_all("abbr"):
                        abbr.extract()  # Удаляем ненужные <abbr>
                    for em in summary.find_all("em"):
                        em.extract()

                    # Берём оставшийся текст без тегов
                    clean_text = summary.text.strip()
                    clean_text = clean_text.replace("1)", "")
                    if clean_text:
                        return clean_text

                # 1️⃣ Перевод в <summary> внутри <a class="ig_local">
                for summary in soup.find_all("summary"):
                    local_translations = [a.text.strip() for a in summary.find_all("a")]
                    if local_translations:
                        return local_translations[0]

                # 2️⃣ Перевод в <p> без <abbr>, <em>
                for p_tag in soup.find_all("p"):
                    for abbr in p_tag.find_all("abbr"):
                        abbr.extract()
                    for em in p_tag.find_all("em"):
                        em.extract()
                    kazakh_translation = p_tag.text.strip()
                    if kazakh_translation:
                        return kazakh_translation

                # 3️⃣ Перевод в <em> внутри <p>
                for p_tag in soup.find_all("p"):
                    em_tags = p_tag.find_all("em")
                    for em in em_tags:
                        translation = em.text.strip()
                        if translation:
                            return translation

                # 4️⃣ Перевод в <p> внутри <a class="ig_local"> (как в "благовест")
                for p_tag in soup.find_all("p"):
                    a_tag = p_tag.find_all("a")
                    if a_tag:
                        return a_tag[0].text.strip()

                # 5️⃣ Перевод после `→` в JSON
                if "translation" in response.text:
                    arrow_translation = parse_translation_arrow(response.text)
                    if arrow_translation:
                        return arrow_translation

        except Exception as e:
            print(f"Ошибка при переводе на казахский: {e}")

    return "Перевод не найден"



# Функция для перевода слова на английский через WooordHunt
def translate_to_english(word):
    url = f"https://wooordhunt.ru/word/{word}"

    try:
        response = requests.get(url, verify=False)  # Отключаем проверку SSL-сертификата

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            translations = set()  # Используем множество для удаления дубликатов

            # 1️⃣ **Поиск в `<p class="t_inline">`** (как в "Хлябь")
            p_tag = soup.find("p", class_="t_inline")
            if p_tag:
                words = p_tag.text.strip().split(", ")  # Разбиваем, если есть дубли
                translations.update(words[:1])  # Берём только первое слово

            # 2️⃣ **Поиск всех `<a>` внутри `<div id="wd_content">`**
            content_block = soup.find("div", id="wd_content", class_="ru_content")
            if content_block:
                for a_tag in content_block.find_all("a"):
                    word = a_tag.text.strip()
                    if word.isalpha():  # Фильтруем, чтобы брать только английские слова
                        translations.add(word)

            # 3️⃣ **Поиск первого `<span>` внутри `<div class="word_ex word_ex_sup">`**
            example_block = soup.find("div", class_="word_ex word_ex_sup")
            if example_block:
                span_tag = example_block.find("span")  # Берём первый найденный `<span>`
                if span_tag:
                    translations.add(span_tag.text.strip())  # Добавляем текст

            if translations:
                tr = list(translations)
                filtered_tr = [word for word in tr if not re.search(r'[а-яА-Я]', word)]
                return "; ".join(filtered_tr)  # Берём первый найденный перевод

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
    
    translation_kz = translate_to_kazakh(word)
    print(f"Перевод на казахский: {translation_kz} (тип: {type(translation_kz)})")

    message = (
        f"📖 *Слово дня:* {word.strip()}\n\n"
        f"📜 *Значение:* {meaning.strip()}\n"
        f"🇰🇿 *Перевод на казахский:* {kazakh_translation}\n"
        f"🇬🇧 *Перевод на английский:* {english_translation}"
    )
    
    print(f"Отправляемое сообщение:\n{message}")
    await update.message.reply_text(message, parse_mode="Markdown")

# Запуск бота
def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("word", word))
    app.run_polling()

if __name__ == "__main__":
    main()