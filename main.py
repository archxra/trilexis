import os
import requests
import re
import logging
import google.generativeai as genai
import urllib3
import tempfile
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler
from bs4 import BeautifulSoup

# Отключаем предупреждения
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 🔹 Настройки API
TELEGRAM_BOT_TOKEN = "8184665271:AAHaKGl4_gMqupv3XdIPpyE_IGKYpkwtRSM"
GEMINI_API_KEY = "AIzaSyANeHY9pIj82d3pUL6LLB5ffsORuE8Gk58"
IAM_TOKEN = "t1.9eudzZ2NlMyOm82Uk5OXlpGcis-Rye3rnc2djceOypKcnpqNkY2ekJuNj5Dl8_cIF2FC-e9iEDom_t3z90hFXkL572IQOib-zef1653NnYyelMzOyoqbzcfIiZ2Jl8yY7_zF653NnYyelMzOyoqbzcfIiZ2Jl8yY.Zdumu7Qq3ol3Tvdb8UD87RmvT8any-oXAykwVeVAZuOZbPg5avwo2zT1ejAMSxMUl7GKLlDEqmILGTvw5lhrDw"  # 🔹 Yandex IAM-токен
FOLDER_ID = "ao777nqtbemrohksilrt"  # 🔹 Yandex Folder ID

# Настраиваем Google Gemini API
genai.configure(api_key=GEMINI_API_KEY)

# Логирование
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# 🔹 Функция получения редкого слова через Gemini API
def get_rare_word():
    model = genai.GenerativeModel("gemini-pro")
    prompt = "Дай мне одно редкое русское слово. Без объяснений, только слово"
    response = model.generate_content(prompt)
    if response and response.text:
        return response.text.strip()
    return "Ошибка при получении слова"

# 🔹 Перевод на казахский через sozdik.kz
COOKIES = {"sid": "q3opq07hg5e0v0mn41id0q60lc"}

def translate_to_kazakh(word):
    url = f"https://sozdik.kz/translate/ru/kk/{word}/"
    for attempt in range(3):
        try:
            response = requests.get(url, cookies=COOKIES, verify=False)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")

                # 1️⃣ Перевод внутри <summary>
                for summary in soup.find_all("summary"):
                    local_translations = [a.text.strip() for a in summary.find_all("a")]
                    if local_translations:
                        return local_translations[0]

                # 2️⃣ Перевод в <p> без <abbr>
                for p_tag in soup.find_all("p"):
                    for abbr in p_tag.find_all("abbr"):
                        abbr.extract()
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

        except Exception as e:
            print(f"Ошибка при переводе на казахский: {e}")
    return "Перевод не найден"

# 🔹 Перевод на английский через WooordHunt
def translate_to_english(word):
    url = f"https://wooordhunt.ru/word/{word}"
    try:
        response = requests.get(url, verify=False)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            translations = set()

            # 1️⃣ Поиск в <p class="t_inline">
            p_tag = soup.find("p", class_="t_inline")
            if p_tag:
                words = p_tag.text.strip().split(", ")
                translations.update(words[:1])

            # 2️⃣ Поиск первого <span> внутри <div class="word_ex word_ex_sup">
            example_block = soup.find("div", class_="word_ex word_ex_sup")
            if example_block:
                span_tag = example_block.find("span")
                if span_tag:
                    translations.add(span_tag.text.strip())

            if translations:
                tr = list(translations)
                filtered_tr = [w for w in tr if not re.search(r'[а-яА-Я]', w)]
                return "; ".join(filtered_tr)
    except Exception as e:
        print(f"Ошибка при переводе на английский: {e}")
    return "Перевод не найден"

# 🔹 Генерация речи через Yandex SpeechKit
def generate_audio(text, lang):
    """Генерирует аудиофайл с помощью Yandex SpeechKit (REST API)."""
    
    voice_mapping = {"ru": "oksana", "kk": "daulet", "en": "nick"}  # Доступные голоса
    voice = voice_mapping.get(lang, "oksana")  # Если язык не найден, берём русский

    url = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"
    headers = {"Authorization": f"Bearer {IAM_TOKEN}", "x-folder-id": FOLDER_ID}
    params = {
        "text": text,
        "voice": voice,
        "folderId": FOLDER_ID,
        "lang": lang
    }

    response = requests.post(url, headers=headers, params=params)
    
    if response.status_code == 200:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as f:
            temp_filename = f.name
            f.write(response.content)
        return temp_filename  # Возвращает путь к файлу
    else:
        print(f"Ошибка Yandex SpeechKit: {response.text}")
        return None  # В случае ошибки вернёт `None`

# 🔹 Создание клавиатуры с кнопками
def create_inline_keyboard(kazakh, english):
    kazakh_words = [w.strip() for w in kazakh.split(";") if w.strip()]
    english_words = [w.strip() for w in english.split(";") if w.strip()]
    keyboard = []
    
    # ✅ Ограничиваем длину callback_data до 64 символов и убираем недопустимые символы
    def sanitize_callback_data(word, lang):
        clean_word = re.sub(r"[^a-zA-Zа-яА-ЯёЁңқүұөһіғәңҚҰҮӨҺІҒӘ ]", "", word)  # Убираем запрещённые символы
        return f"TTS_{lang}:{clean_word[:60]}"  # Ограничиваем длину (60 символов + "TTS_KK:")

    if kazakh_words:
        row = [InlineKeyboardButton(text=word, callback_data=sanitize_callback_data(word, "KK")) for word in kazakh_words]
        keyboard.append(row)
    
    if english_words:
        row = [InlineKeyboardButton(text=word, callback_data=sanitize_callback_data(word, "EN")) for word in english_words]
        keyboard.append(row)
    
    return InlineKeyboardMarkup(keyboard)


# 🔹 Обработка нажатий на кнопки
async def tts_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data.startswith("TTS_KK:"):
        word_to_speak = data.split(":", 1)[1]
        lang = "kk"
    elif data.startswith("TTS_EN:"):
        word_to_speak = data.split(":", 1)[1]
        lang = "en"
    elif data.startswith("TTS_RU:"):
        word_to_speak = data.split(":", 1)[1]
        lang = "ru"
    else:
        return
    
    filename = generate_audio(word_to_speak, lang)
    if filename:
        with open(filename, "rb") as audio:
            await query.message.reply_voice(voice=audio)
        os.remove(filename)


# 🔹 Отправка слова пользователю
async def word(update: Update, context: CallbackContext):
    word = get_rare_word().strip()
    kazakh_translation = translate_to_kazakh(word)
    english_translation = translate_to_english(word)
    message = f"📖 *Слово дня:* {word}\n\n🇰🇿 *Перевод на казахский:* {kazakh_translation}\n🇬🇧 *Перевод на английский:* {english_translation}"
    keyboard = create_inline_keyboard(kazakh_translation, english_translation)
    await update.message.reply_text(message, parse_mode="Markdown", reply_markup=keyboard)

# 🔹 Запуск бота
def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("word", word))
    app.add_handler(CallbackQueryHandler(tts_callback))
    app.run_polling()

if __name__ == "__main__":
    main()
