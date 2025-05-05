import os
import logging
from datetime import datetime, timedelta
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackContext, CallbackQueryHandler, InlineQueryHandler
from imsakiye import namaz_vakitlerini_al_sehir
import pytz  # Add pytz for timezone handling
import asyncio

# Logging ayarları
logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.INFO
)

# Logger'ı özelleştir
logger = logging.getLogger(__name__)

# Diğer modüllerin log seviyesini ayarla
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)
logging.getLogger('apscheduler').setLevel(logging.WARNING)

# Türkiye saat dilimi
TURKEY_TZ = pytz.timezone('Europe/Istanbul')

# Telegram bot token'ı
TOKEN = '7299453980:AAGs5ZYJw2ylP5lwiGMBa_pWVlgngTNj-iU'

# Veritabanı bağlantısı
def get_db_connection():
    conn = sqlite3.connect('telegram_bot.db')
    conn.row_factory = sqlite3.Row
    return conn

# Veritabanı tablosunu oluştur
def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            sehir TEXT,
            bildirim_aktif INTEGER DEFAULT 0,
            bildirim_suresi INTEGER DEFAULT 5,
            grup_id TEXT,
            arkadas_onerisi INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

# Türkiye'nin tüm illeri
SEHIRLER = [
    "Adana", "Adıyaman", "Afyonkarahisar", "Ağrı", "Amasya", "Ankara", "Antalya", "Ardahan", "Artvin",
    "Aydın", "Balıkesir", "Batman", "Bayburt", "Bilecik", "Bingöl", "Bitlis", "Bolu", "Burdur", "Bursa",
    "Canakkale", "Cankiri", "Corum", "Denizli", "Diyarbakır", "Düzce", "Edirne", "Elazığ", "Erzincan", "Erzurum",
    "Eskisehir", "Gaziantep", "Giresun", "Gümüşhane", "Hakkari", "Hatay", "Iğdır", "Isparta", "İstanbul", "İzmir",
    "Kahramanmaraş", "Karabük", "Karaman", "Kars", "Kastamonu", "Kayseri", "Kırıkkale", "Kırklareli", "Kırsehir",
    "Kilis", "Kocaeli", "Konya", "Kutahya", "Malatya", "Manisa", "Mardin", "Mersin", "Muğla", "Muş", "Nevşehir",
    "Niğde", "Ordu", "Osmaniye", "Rize", "Sakarya", "Samsun", "Şanlıurfa", "Siirt", "Sinop", "Şırnak", "Sivas",
    "Tekirdağ", "Tokat", "Trabzon", "Tunceli", "Uşak", "Van", "Yalova", "Yozgat", "Zonguldak"
]

# Ana menü butonları
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("Namaz Vakitleri 🕒", callback_data="vakitler"),
         InlineKeyboardButton("🔍 Şehir Seçimi 📍", switch_inline_query_current_chat="")],
        [InlineKeyboardButton("Bildirim Ayarları 🔔", callback_data="bildirim_ayarlari"),
         InlineKeyboardButton("Grup Ayarları 👥", callback_data="grup_ayarlari")],
        [InlineKeyboardButton("Yardım ❓", callback_data="yardim"),
         InlineKeyboardButton("İletişim 📱", callback_data="iletisim")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Şehir seçimi için butonlar
def get_city_keyboard():
    keyboard = []
    row = []
    for i, city in enumerate(SEHIRLER):
        row.append(KeyboardButton(city))
        if (i + 1) % 2 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([KeyboardButton("Ana Menüye Dön ⬅️")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Bildirim ayarları için butonlar
def get_notification_keyboard():
    keyboard = [
        [KeyboardButton("Bildirimleri Aç 🔔"), KeyboardButton("Bildirimleri Kapat 🔕")],
        [KeyboardButton("Bildirim Süresini Ayarla ⚙️"), KeyboardButton("Bildirim Durumu 📊")],
        [KeyboardButton("Ana Menüye Dön ⬅️")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Bildirim süresi seçimi için butonlar
def get_duration_keyboard():
    keyboard = [
        [KeyboardButton("5 Dakika ⏰"), KeyboardButton("10 Dakika ⏰")],
        [KeyboardButton("15 Dakika ⏰")],
        [KeyboardButton("Ana Menüye Dön ⬅️")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot başlatıldığında çalışacak komut"""
    user_id = update.effective_user.id
    
    # Kullanıcıyı veritabanına ekle
    conn = get_db_connection()
    conn.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        '🕌 Merhaba! Namaz Vakitleri Bot\'a hoş geldiniz!\n\n'
        'Ben size namaz vakitlerini hatırlatmak için buradayım. Aşağıdaki butonları kullanarak işlemlerinizi gerçekleştirebilirsiniz.',
        reply_markup=get_main_keyboard()
    )

async def sehirler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tüm şehirleri listeler"""
    message = "📋 Türkiye'nin İlleri:\n\n"
    for sehir in SEHIRLER:
        message += f"📍 {sehir}\n"
    message += "\n💡 Bir şehir seçtikten sonra:\n"
    message += "• /vakitler <şehir> ile vakitleri görebilirsiniz\n"
    message += "• /bildirim <şehir> ile bildirimleri aktif edebilirsiniz"
    await update.message.reply_text(message)

async def bildirim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bildirim ayarlarını yapılandırır"""
    user_id = update.effective_user.id
    conn = get_db_connection()
    user = conn.execute('SELECT sehir FROM users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    
    if not user or not user['sehir']:
        await update.message.reply_text(
            "❌ Önce bir şehir seçmelisiniz!\n\n"
            "💡 Şehir seçmek için 'Şehir Seçimi' butonunu kullanın.",
            reply_markup=get_main_keyboard()
        )
        return
    
    sehir = user['sehir']
    
    # Kullanıcının bildirim ayarlarını güncelle
    conn = get_db_connection()
    conn.execute('''
        UPDATE users 
        SET bildirim_aktif = 1 
        WHERE user_id = ?
    ''', (user_id,))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        f"✅ Tebrikler! Bildirimleriniz aktif edildi!\n\n"
        f"📍 Şehir: {sehir}\n"
        "📢 Her namaz vaktinden 5 dakika önce size bildirim göndereceğim.\n\n"
        "💡 Bildirim ayarlarınızı özelleştirmek için:\n"
        "• Bildirim süresini değiştirmek için 'Bildirim Süresini Ayarla' butonunu kullanın\n"
        "• Mevcut ayarlarınızı görmek için 'Bildirim Durumu' butonunu kullanın\n"
        "• Bildirimleri kapatmak için 'Bildirimleri Kapat' butonunu kullanın",
        reply_markup=get_notification_keyboard()
    )

async def bildirim_kapat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bildirimleri kapatır"""
    user_id = update.effective_user.id
    
    conn = get_db_connection()
    conn.execute('UPDATE users SET bildirim_aktif = 0 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        "🔕 Bildirimleriniz kapatıldı.\n\n"
        "💡 Tekrar bildirim almak isterseniz /bildirim <şehir> komutunu kullanabilirsiniz.\n"
        "📱 Mevcut ayarlarınızı görmek için /bildirim_durum komutunu kullanabilirsiniz."
    )

async def bildirim_durum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bildirim ayarlarını gösterir"""
    user_id = update.effective_user.id
    
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    
    if not user or not user['sehir']:
        await update.message.reply_text(
            "❌ Henüz bir şehir seçmediniz!\n\n"
            "💡 Bildirim almak için:\n"
            "1. /sehirler komutu ile bir şehir seçin\n"
            "2. /bildirim <şehir> komutu ile bildirimleri aktif edin"
        )
        return
    
    if user['bildirim_aktif']:
        bildirim_suresi = user['bildirim_suresi'] or 5
        await update.message.reply_text(
            f"📊 Bildirim Ayarlarınız:\n\n"
            f"📍 Şehir: {user['sehir']}\n"
            f"🔔 Bildirimler: Aktif\n"
            f"⏰ Bildirim Süresi: {bildirim_suresi} dakika\n\n"
            "💡 Ayarlarınızı değiştirmek için:\n"
            "• Bildirim süresini değiştirmek için /bildirim_ayarla <süre>\n"
            "• Bildirimleri kapatmak için /bildirim_kapat"
        )
    else:
        await update.message.reply_text(
            f"📊 Bildirim Ayarlarınız:\n\n"
            f"📍 Şehir: {user['sehir']}\n"
            f"🔔 Bildirimler: Kapalı\n\n"
            "💡 Bildirimleri aktif etmek için /bildirim <şehir> komutunu kullanın."
        )

async def vakitler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Günün namaz vakitlerini gösterir"""
    try:
        user_id = update.effective_user.id
        conn = get_db_connection()
        user = conn.execute('SELECT sehir, bildirim_aktif FROM users WHERE user_id = ?', (user_id,)).fetchone()
        conn.close()
        
        if not user or not user['sehir']:
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    "❌ Önce bir şehir seçmelisiniz!\n\n"
                    "💡 Şehir seçmek için 'Şehir Seçimi' butonunu kullanın.",
                    reply_markup=get_main_keyboard()
                )
            else:
                await update.message.reply_text(
                    "❌ Önce bir şehir seçmelisiniz!\n\n"
                    "💡 Şehir seçmek için 'Şehir Seçimi' butonunu kullanın.",
                    reply_markup=get_main_keyboard()
                )
                return
        
        sehir = user['sehir']
        bugun = datetime.now().strftime('%Y-%m-%d')
        prayer_times = namaz_vakitlerini_al_sehir(sehir, bugun)
        today = datetime.now().strftime('%d.%m.%Y')
        
        message = f"📅 {today} Namaz Vakitleri ({sehir}):\n\n"
        message += f"🌅 İmsak: {prayer_times['imsak']}\n"
        message += f"🌞 Güneş: {prayer_times['gunes']}\n"
        message += f"🌆 Öğle: {prayer_times['ogle']}\n"
        message += f"🌅 İkindi: {prayer_times['ikindi']}\n"
        message += f"🌆 Akşam: {prayer_times['aksam']}\n"
        message += f"🌙 Yatsı: {prayer_times['yatsi']}\n"
        
        # Bildirim durumuna göre inline buton oluştur
        if user['bildirim_aktif']:
            keyboard = [
                [InlineKeyboardButton("Bildirimleri Kapat 🔕", callback_data="vakit_bildirim_kapat")],
                [InlineKeyboardButton("Ana Menüye Dön ⬅️", callback_data="main_menu")]
            ]
        else:
            keyboard = [
                [InlineKeyboardButton("Bildirimleri Etkinleştir 🔔", callback_data="vakit_bildirim_ac")],
                [InlineKeyboardButton("Ana Menüye Dön ⬅️", callback_data="main_menu")]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(message, reply_markup=reply_markup)
        else:
            await update.message.reply_text(message, reply_markup=reply_markup)
            
    except Exception as e:
        logger.error(f"Vakitler alınırken hata oluştu: {e}")
        if update.callback_query:
            await update.callback_query.edit_message_text(
                "Üzgünüm, namaz vakitlerini şu anda gösteremiyorum. Lütfen daha sonra tekrar deneyin.",
                reply_markup=get_main_keyboard()
            )
        else:
            await update.message.reply_text(
                "Üzgünüm, namaz vakitlerini şu anda gösteremiyorum. Lütfen daha sonra tekrar deneyin."
            )

async def sehir_ara(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Şehir arama özelliği"""
    query = update.inline_query.query.lower().strip()
    
    try:
        if not query:  # Eğer arama terimi boşsa tüm şehirleri göster
            results = [
                InlineQueryResultArticle(
                    id=str(i),
                    title=sehir,
                    description=f"'{sehir}' şehrini seçmek için tıklayın",
                    input_message_content=InputTextMessageContent(
                        message_text=f"!sehirsec_{sehir}"
                    ),
                    thumbnail_url="https://static.vecteezy.com/system/resources/previews/019/619/771/non_2x/sultan-ahamed-mosque-icon-sultan-ahamed-mosque-blue-illustration-blue-mosque-icon-vector.jpg"  # İsteğe bağlı: Küçük bir cami ikonu
                )
                for i, sehir in enumerate(SEHIRLER[:20])  # İlk 20 şehri göster
            ]
        else:
            # Arama terimine göre şehirleri filtrele
            filtered_cities = [city for city in SEHIRLER if query in city.lower()]
            results = [
                InlineQueryResultArticle(
                    id=str(i),
                    title=sehir,
                    description=f"'{sehir}' şehrini seçmek için tıklayın",
                    input_message_content=InputTextMessageContent(
                        message_text=f"!sehirsec_{sehir}"
                    ),
                    thumbnail_url="https://static.vecteezy.com/system/resources/previews/019/619/771/non_2x/sultan-ahamed-mosque-icon-sultan-ahamed-mosque-blue-illustration-blue-mosque-icon-vector.jpg"  # İsteğe bağlı: Küçük bir cami ikonu
                )
                for i, sehir in enumerate(filtered_cities[:20])  # En fazla 20 sonuç göster
            ]
        
        if not results:  # Eğer sonuç bulunamadıysa
            results = [
                InlineQueryResultArticle(
                    id="0",
                    title="Sonuç Bulunamadı",
                    description="Lütfen farklı bir arama terimi deneyin",
                    input_message_content=InputTextMessageContent(
                        message_text="Şehir bulunamadı. Lütfen tekrar deneyin."
                    )
                )
            ]
        
        await update.inline_query.answer(results, cache_time=1)
    except Exception as e:
        logger.error(f"Şehir arama hatası: {e}")
        # Hata durumunda kullanıcıya bilgi ver
        results = [
            InlineQueryResultArticle(
                id="error",
                title="Bir Hata Oluştu",
                description="Lütfen tekrar deneyin",
                input_message_content=InputTextMessageContent(
                    message_text="Arama sırasında bir hata oluştu. Lütfen tekrar deneyin."
                )
            )
        ]
        await update.inline_query.answer(results)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mesajları işler"""
    text = update.message.text
    
    if text == "Namaz Vakitleri 🕒":
        await vakitler(update, context)
    elif text == "Şehir Seçimi 📍":
        # Şehir seçimi için sadece arama butonu
        keyboard = [
            [InlineKeyboardButton("🔍 Şehir Aramak İçin Tıklayın", switch_inline_query_current_chat="")],
            [InlineKeyboardButton("Ana Menüye Dön ⬅️", callback_data="main_menu")]
        ]
            
        await update.message.reply_text(
            "🏙️ Şehir Seçimi\n\n"
            "• Yukarıdaki arama butonuna tıklayarak şehir arayabilirsiniz\n"
            "• Arama yapmak için boşluk bırakıp şehir adını yazmaya başlayın",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif text.startswith("!sehirsec_"):
        # Şehir seçimi yapıldığında
        selected_city = text.split("!sehirsec_")[1]
        if selected_city in SEHIRLER:
            user_id = update.effective_user.id
            conn = get_db_connection()
            conn.execute('UPDATE users SET sehir = ? WHERE user_id = ?', (selected_city, user_id))
            conn.commit()
            conn.close()
            await update.message.reply_text(
                f"✅ {selected_city} şehri seçildi!\n\n"
                "Bildirim ayarlarınızı yapmak için 'Bildirim Ayarları' butonunu kullanabilirsiniz.",
                reply_markup=get_main_keyboard()
            )
    elif text == "Bildirim Ayarları 🔔":
        # Bildirim durumunu göster
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE user_id = ?', (update.effective_user.id,)).fetchone()
        conn.close()
        
        durum = "Aktif ✅" if user['bildirim_aktif'] else "Kapalı 🔕"
        sure = user['bildirim_suresi'] or 5
        sehir = user['sehir'] or "Seçilmemiş"
        
        keyboard = [
            [InlineKeyboardButton("Bildirimleri Aç 🔔", callback_data="bildirim_menu_ac"),
             InlineKeyboardButton("Bildirimleri Kapat 🔕", callback_data="bildirim_menu_kapat")],
            [InlineKeyboardButton("Bildirim Süresini Ayarla ⚙️", callback_data="bildirim_sure_menu")]
        ]
        
        await update.message.reply_text(
            f"📊 Bildirim Durumunuz:\n\n"
            f"🔔 Bildirimler: {durum}\n"
            f"⏰ Bildirim Süresi: {sure} dakika\n"
            f"📍 Seçili Şehir: {sehir}\n\n"
            "Ayarlarınızı değiştirmek için aşağıdaki butonları kullanabilirsiniz:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif text == "Grup Ayarları 👥":
        await grup_ayarla(update, context)
    elif text == "Yardım ❓":
        await aciklama(update, context)
    elif text == "İletişim 📱":
        await iletisim(update, context)
    elif text == "Ana Menüye Dön ⬅️":
        await update.message.reply_text(
            "Ana menüye döndünüz:",
            reply_markup=get_main_keyboard()
        )
    elif text in SEHIRLER:
        # Şehir seçildiğinde bildirim ayarlarını güncelle
        user_id = update.effective_user.id
        conn = get_db_connection()
        conn.execute('UPDATE users SET sehir = ? WHERE user_id = ?', (text, user_id))
        conn.commit()
        conn.close()
        await update.message.reply_text(
            f"✅ {text} şehri seçildi!\n\n"
            "Bildirim ayarlarınızı yapmak için 'Bildirim Ayarları' butonunu kullanabilirsiniz.",
            reply_markup=get_main_keyboard()
        )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buton tıklamalarını işler"""
    query = update.callback_query
    user_id = query.from_user.id
    
    try:
        if query.data == "vakitler":
            await vakitler(update, context)
        elif query.data == "bildirim_ayarlari":
            # Bildirim durumunu göster
            conn = get_db_connection()
            user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
            conn.close()
            
            durum = "Aktif ✅" if user['bildirim_aktif'] else "Kapalı 🔕"
            sure = user['bildirim_suresi'] or 5
            sehir = user['sehir'] or "Seçilmemiş"
            
            keyboard = [
                [InlineKeyboardButton("Bildirimleri Aç 🔔", callback_data="bildirim_menu_ac"),
                 InlineKeyboardButton("Bildirimleri Kapat 🔕", callback_data="bildirim_menu_kapat")],
                [InlineKeyboardButton("Bildirim Süresini Ayarla ⚙️", callback_data="bildirim_sure_menu")],
                [InlineKeyboardButton("Ana Menüye Dön ⬅️", callback_data="main_menu")]
            ]
            
            await query.edit_message_text(
                f"📊 Bildirim Durumunuz:\n\n"
                f"🔔 Bildirimler: {durum}\n"
                f"⏰ Bildirim Süresi: {sure} dakika\n"
                f"📍 Seçili Şehir: {sehir}\n\n"
                "Ayarlarınızı değiştirmek için aşağıdaki butonları kullanabilirsiniz:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        elif query.data == "grup_ayarlari":
            await grup_ayarla(update, context)
        elif query.data == "yardim":
            await aciklama(update, context)
        elif query.data == "iletisim":
            await iletisim(update, context)
        elif query.data == "main_menu":
            await query.edit_message_text(
                '🕌 Merhaba! Namaz Vakitleri Bot\'a hoş geldiniz!\n\n'
                'Ben size namaz vakitlerini hatırlatmak için buradayım. Aşağıdaki butonları kullanarak işlemlerinizi gerçekleştirebilirsiniz.',
                reply_markup=get_main_keyboard()
            )
        elif query.data.startswith("sehir_sec_"):
            # Şehir seçimi yapıldığında
            selected_city = query.data.split("sehir_sec_")[1]
            conn = get_db_connection()
            conn.execute('UPDATE users SET sehir = ? WHERE user_id = ?', (selected_city, user_id))
            conn.commit()
            conn.close()
            
            await query.edit_message_text(
                f"✅ {selected_city} şehri seçildi!\n\n"
                "Bildirim ayarlarınızı yapmak için 'Bildirim Ayarları' butonunu kullanabilirsiniz.",
                reply_markup=get_main_keyboard()
            )
            await query.answer(f"✅ {selected_city} şehri seçildi!")
            
        elif query.data.startswith("vakit_bildirim_"):
            # Namaz vakitleri ekranından gelen bildirim işlemleri
            action = query.data.split('_')[2]  # ac veya kapat
            conn = get_db_connection()
            
            if action == "ac":
                conn.execute('UPDATE users SET bildirim_aktif = 1 WHERE user_id = ?', (user_id,))
                conn.commit()
                new_keyboard = [
                    [InlineKeyboardButton("Bildirimleri Kapat 🔕", callback_data="vakit_bildirim_kapat")],
                    [InlineKeyboardButton("Ana Menüye Dön ⬅️", callback_data="main_menu")]
                ]
                await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(new_keyboard))
                await query.answer("✅ Bildirimler etkinleştirildi!")
            
            elif action == "kapat":
                conn.execute('UPDATE users SET bildirim_aktif = 0 WHERE user_id = ?', (user_id,))
                conn.commit()
                new_keyboard = [
                    [InlineKeyboardButton("Bildirimleri Etkinleştir 🔔", callback_data="vakit_bildirim_ac")],
                    [InlineKeyboardButton("Ana Menüye Dön ⬅️", callback_data="main_menu")]
                ]
                await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(new_keyboard))
                await query.answer("🔕 Bildirimler kapatıldı!")
            
            conn.close()
            
        elif query.data.startswith("bildirim_menu"):
            # Bildirim menüsü işlemleri
            action = query.data.split('_')[2]  # ac, kapat
            conn = get_db_connection()
            
            if action == "ac":
                conn.execute('UPDATE users SET bildirim_aktif = 1 WHERE user_id = ?', (user_id,))
                conn.commit()
            elif action == "kapat":
                conn.execute('UPDATE users SET bildirim_aktif = 0 WHERE user_id = ?', (user_id,))
                conn.commit()
            
            # Güncel durumu al ve ekranı güncelle
            user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
            conn.close()
            
            durum = "Aktif ✅" if user['bildirim_aktif'] else "Kapalı 🔕"
            sure = user['bildirim_suresi'] or 5
            sehir = user['sehir'] or "Seçilmemiş"
            
            keyboard = [
                [InlineKeyboardButton("Bildirimleri Aç 🔔", callback_data="bildirim_menu_ac"),
                 InlineKeyboardButton("Bildirimleri Kapat 🔕", callback_data="bildirim_menu_kapat")],
                [InlineKeyboardButton("Bildirim Süresini Ayarla ⚙️", callback_data="bildirim_sure_menu")],
                [InlineKeyboardButton("Ana Menüye Dön ⬅️", callback_data="main_menu")]
            ]
            
            try:
                await query.edit_message_text(
                    f"📊 Bildirim Durumunuz:\n\n"
                    f"🔔 Bildirimler: {durum}\n"
                    f"⏰ Bildirim Süresi: {sure} dakika\n"
                    f"📍 Seçili Şehir: {sehir}\n\n"
                    "Ayarlarınızı değiştirmek için aşağıdaki butonları kullanabilirsiniz:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception as e:
                if "message is not modified" not in str(e).lower():
                    raise e
            
            await query.answer("✅ Bildirimler güncellendi!")
        
        elif query.data == "bildirim_sure_menu":
            # Bildirim süresi seçim menüsü
            keyboard = [
                [InlineKeyboardButton("5 Dakika ⏰", callback_data="bildirim_sure_5"),
                 InlineKeyboardButton("10 Dakika ⏰", callback_data="bildirim_sure_10")],
                [InlineKeyboardButton("15 Dakika ⏰", callback_data="bildirim_sure_15")],
                [InlineKeyboardButton("Geri Dön ⬅️", callback_data="bildirim_durum_menu")]
            ]
            await query.edit_message_text(
                "⚙️ Bildirim Süresini Ayarla\n\n"
                "Namaz vakitlerinden kaç dakika önce bildirim almak istiyorsunuz?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        elif query.data.startswith("bildirim_sure_"):
            # Bildirim süresi ayarlama
            sure = int(query.data.split('_')[2])
            conn = get_db_connection()
            conn.execute('UPDATE users SET bildirim_suresi = ? WHERE user_id = ?', (sure, user_id))
            conn.commit()
            
            # Güncel durumu al
            user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
            conn.close()
            
            durum = "Aktif ✅" if user['bildirim_aktif'] else "Kapalı 🔕"
            sehir = user['sehir'] or "Seçilmemiş"
            
            keyboard = [
                [InlineKeyboardButton("Bildirimleri Aç 🔔", callback_data="bildirim_menu_ac"),
                 InlineKeyboardButton("Bildirimleri Kapat 🔕", callback_data="bildirim_menu_kapat")],
                [InlineKeyboardButton("Bildirim Süresini Ayarla ⚙️", callback_data="bildirim_sure_menu")],
                [InlineKeyboardButton("Ana Menüye Dön ⬅️", callback_data="main_menu")]
            ]
            
            await query.edit_message_text(
                f"📊 Bildirim Durumunuz:\n\n"
                f"🔔 Bildirimler: {durum}\n"
                f"⏰ Bildirim Süresi: {sure} dakika\n"
                f"📍 Seçili Şehir: {sehir}\n\n"
                "Ayarlarınızı değiştirmek için aşağıdaki butonları kullanabilirsiniz:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            await query.answer(f"✅ Bildirim süresi {sure} dakika olarak ayarlandı!")
    
    except Exception as e:
        logger.error(f"Buton işlenirken hata oluştu: {e}")
        await query.answer("❌ Bir hata oluştu. Lütfen tekrar deneyin.")

async def temizle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Konuşmadaki tüm mesajları siler"""
    chat_id = update.effective_chat.id
    try:
        # Son mesajın ID'sini al (temizle komutunun kendisi)
        last_message_id = update.message.message_id
        
        # Son 100 mesajı aşağıdan yukarıya doğru sil
        for message_id in range(last_message_id , max(1, last_message_id - 100), -1):
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                # Her mesaj silindikten sonra 0.5 saniye bekle
                await asyncio.sleep(0.5)
            except Exception as e:
                # Mesaj silinemezse (zaten silinmiş veya başka bir hata) devam et
                continue
        
        # Temizleme işlemi bitince start komutunu çalıştır
        await start(update, context)
    except Exception as e:
        logger.error(f"Temizleme işlemi sırasında hata oluştu: {e}")
        await update.message.reply_text("❌ Mesajları silerken bir hata oluştu.")

async def aciklama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot hakkında detaylı açıklama ve kullanım bilgileri verir"""
    message = (
        "🕌 Namaz Vakitleri Bot - Detaylı Açıklama\n\n"
        "Bu bot, Türkiye'nin tüm illeri için namaz vakitlerini gösterir ve bildirim gönderir.\n\n"
        "📱 Komutlar ve Açıklamaları:\n\n"
        "📍 Şehir Seçimi\n"
        "• Arama butonuna tıklayarak şehir arayabilirsiniz\n"
        "• Boşluk bırakıp şehir adını yazmaya başlayın\n\n"
        "🕒 Namaz Vakitleri\n"
        "• Seçtiğiniz şehir için günün namaz vakitlerini gösterir\n"
        "• Bildirimleri açıp kapatabilirsiniz\n\n"
        "🔔 Bildirim Ayarları\n"
        "• Bildirimleri açıp kapatabilirsiniz\n"
        "• Bildirim süresini ayarlayabilirsiniz\n"
        "• Varsayılan süre 5 dakikadır\n\n"
        "👥 Grup Ayarları\n"
        "• Grup sohbetlerinde namaz vakitlerini paylaşabilirsiniz\n"
        "• Sadece grup yöneticileri kullanabilir\n\n"
        "💡 Tavsiyeler:\n"
        "1. Bildirimleri aktif etmeden önce doğru şehri seçtiğinizden emin olun\n"
        "2. Bildirimlerin düzgün çalışması için botun engellenmediğinden emin olun\n"
        "3. Vakitleri kontrol etmek için Namaz Vakitleri butonunu kullanabilirsiniz\n"
        "4. Bildirimlerinizi kapatmak istediğinizde Bildirim Ayarları butonunu kullanın"
    )
    
    if update.callback_query:
        await update.callback_query.edit_message_text(message, reply_markup=get_main_keyboard())
    else:
        await update.message.reply_text(message, reply_markup=get_main_keyboard())

async def bildirim_ayarla(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bildirim süresini ayarlar"""
    user_id = update.effective_user.id
    args = context.args
    
    # Önce kullanıcının bildirim aktif olup olmadığını kontrol et
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    
    if not user or not user['bildirim_aktif']:
        await update.message.reply_text(
            "❌ Önce bildirimleri aktif etmelisiniz!\n\n"
            "💡 Bildirimleri aktif etmek için:\n"
            "1. /sehirler komutu ile bir şehir seçin\n"
            "2. /bildirim <şehir> komutu ile bildirimleri aktif edin"
        )
        return
    
    if not args or not args[0].isdigit():
        await update.message.reply_text(
            "❌ Lütfen geçerli bir süre belirtin.\n\n"
            "💡 Kullanım: /bildirim_ayarla <süre>\n"
            "Örnek: /bildirim_ayarla 10\n\n"
            "⚠️ Süre 5, 10 veya 15 dakika olabilir."
        )
        return
    
    sure = int(args[0])
    if sure not in [5, 10, 15]:
        await update.message.reply_text(
            "❌ Geçersiz süre! Lütfen 5, 10 veya 15 dakika seçin.\n\n"
            "💡 Örnek: /bildirim_ayarla 10"
        )
        return
    
    conn = get_db_connection()
    conn.execute('UPDATE users SET bildirim_suresi = ? WHERE user_id = ?', (sure, user_id))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        f"✅ Bildirim süreniz {sure} dakika olarak ayarlandı!\n\n"
        f"📢 Artık her vaktin {sure} dakika öncesinde bildirim alacaksınız.\n\n"
        "💡 Mevcut ayarlarınızı görmek için /bildirim_durum komutunu kullanabilirsiniz."
    )

async def grup_ayarla(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Grup sohbetinde namaz vakitlerini paylaşma ayarını yapar"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # Önce kullanıcının şehir seçip seçmediğini kontrol et
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    
    if not user or not user['sehir']:
        if update.callback_query:
            await update.callback_query.edit_message_text(
                "❌ Önce bir şehir seçmelisiniz!\n\n"
                "💡 Grup ayarlarını yapmak için:\n"
                "1. Şehir seçimi yapın\n"
                "2. Bildirimleri aktif edin\n"
                "3. Sonra bu komutu tekrar kullanın",
                reply_markup=get_main_keyboard()
            )
        else:
            await update.message.reply_text(
            "❌ Önce bir şehir seçmelisiniz!\n\n"
            "💡 Grup ayarlarını yapmak için:\n"
                "1. Şehir seçimi yapın\n"
                "2. Bildirimleri aktif edin\n"
                "3. Sonra bu komutu tekrar kullanın",
                reply_markup=get_main_keyboard()
        )
        return
    
    # Sadece grup yöneticileri bu komutu kullanabilir
    chat_member = await context.bot.get_chat_member(chat_id, user_id)
    if chat_member.status not in ['creator', 'administrator']:
        if update.callback_query:
            await update.callback_query.edit_message_text(
                "❌ Bu komutu sadece grup yöneticileri kullanabilir.\n\n"
                "💡 Lütfen grup yöneticisi ile iletişime geçin.",
                reply_markup=get_main_keyboard()
            )
        else:
            await update.message.reply_text(
            "❌ Bu komutu sadece grup yöneticileri kullanabilir.\n\n"
                "💡 Lütfen grup yöneticisi ile iletişime geçin.",
                reply_markup=get_main_keyboard()
        )
        return
    
    conn = get_db_connection()
    conn.execute('UPDATE users SET grup_id = ? WHERE user_id = ?', (str(chat_id), user_id))
    conn.commit()
    conn.close()
    
    message = (
        "✅ Grup ayarları başarıyla kaydedildi!\n\n"
        f"📢 Artık bu grupta {user['sehir']} için namaz vakitleri paylaşılacak.\n\n"
        "💡 Ayarlarınızı değiştirmek için:\n"
        "• Bildirim süresini değiştirmek için Bildirim Ayarları butonunu kullanın\n"
        "• Mevcut ayarlarınızı görmek için Bildirim Durumu butonunu kullanın\n"
        "• Bildirimleri kapatmak için Bildirimleri Kapat butonunu kullanın"
    )
    
    if update.callback_query:
        await update.callback_query.edit_message_text(message, reply_markup=get_main_keyboard())
    else:
        await update.message.reply_text(message, reply_markup=get_main_keyboard())

async def arkadas_oner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Arkadaşlara botu önerme mesajı gönderir"""
    user_id = update.effective_user.id
    
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    
    if not user or not user['sehir']:
        await update.message.reply_text(
            "❌ Önce bir şehir seçmelisiniz.\n\n"
            "💡 /bildirim <şehir> komutu ile şehrinizi seçin."
        )
        return
    
    oneri_mesaji = (
        f"🌟 Merhaba! Size harika bir bot önermek istiyorum:\n\n"
        f"🕌 Namaz Vakitleri Bot\n\n"
        f"Bu bot ile:\n"
        f"📍 {user['sehir']} için namaz vakitlerini öğrenebilirsiniz\n"
        f"🔔 Her vaktin {user['bildirim_suresi']} dakika öncesinde bildirim alabilirsiniz\n"
        f"📱 Tüm Türkiye şehirleri için namaz vakitlerini görebilirsiniz\n\n"
        f"Botu denemek için: @{context.bot.username}\n\n"
        f"💡 İbadetlerinizi vaktinde yapmanız için harika bir yardımcı!"
    )
    
    await update.message.reply_text(
        "✅ Arkadaşlarınıza önerme mesajı hazır!\n\n"
        "💡 Bu mesajı kopyalayıp arkadaşlarınızla paylaşabilirsiniz:\n\n"
        f"{oneri_mesaji}"
    )

async def bildirim_gonder(context: CallbackContext):
    """Namaz vakitlerine göre bildirim gönderir"""
    try:
        conn = get_db_connection()
        users = conn.execute('SELECT * FROM users WHERE bildirim_aktif = 1').fetchall()
        conn.close()
        
        # Türkiye saatini kullan
        now = datetime.now(TURKEY_TZ)
        
        for user in users:
            sehir = user['sehir']
            bildirim_suresi = user['bildirim_suresi'] or 5  # Varsayılan 5 dakika
            bugun = now.strftime('%Y-%m-%d')
            prayer_times = namaz_vakitlerini_al_sehir(sehir, bugun)
            
            # Her vakit için kontrol et
            for vakit, time in prayer_times.items():
                if time == "null":
                    continue
                    
                # Vakit saatini datetime'a çevir
                vakit_time = datetime.strptime(time, '%H:%M')
                # Şu anki tarih ile birleştir
                vakit_time = now.replace(hour=vakit_time.hour, minute=vakit_time.minute)
                
                # Bildirim süresi öncesini hesapla
                bildirim_zamani = vakit_time - timedelta(minutes=bildirim_suresi)
                
                # Şu anki zaman ile bildirim zamanı arasındaki fark 1 dakikadan az ise bildirim gönder
                if abs((now - bildirim_zamani).total_seconds()) < 60:
                    vakit_adi = {
                        'imsak': 'İmsak',
                        'gunes': 'Güneş',
                        'ogle': 'Öğle',
                        'ikindi': 'İkindi',
                        'aksam': 'Akşam',
                        'yatsi': 'Yatsı'
                    }[vakit]
                    
                    message = f"⏰ {vakit_adi} vaktine {bildirim_suresi} dakika kaldı!\n"
                    message += f"📍 {sehir}\n"
                    message += f"🕒 Vakit: {time}"
                    
                    # Kullanıcıya bildirim gönder
                    await context.bot.send_message(chat_id=user['user_id'], text=message)
                    
                    # Grup sohbetinde de paylaş
                    if user['grup_id']:
                        try:
                            await context.bot.send_message(chat_id=user['grup_id'], text=message)
                        except Exception as e:
                            logger.error(f"Grup mesajı gönderilirken hata oluştu: {e}")
                    
    except Exception as e:
        logger.error(f"Bildirim gönderilirken hata oluştu: {e}")

async def iletisim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """İletişim bilgilerini gösterir"""
    message = (
        "📱 İletişim Bilgileri\n\n"
        "👨‍💻 Geliştirici: Yiğit Gülyurt\n\n"
        "🌐 Sosyal Medya Hesapları:\n"
        "• Instagram: instagram.com/yigitgulyurt\n"
        "• GitHub: github.com/yigitgulyurt\n"
        "• LinkedIn: linkedin.com/in/yigitgulyurt\n"
        "• Twitter: @yigitgulyurt\n\n"
        "📧 E-posta: 05yigid05@gmail.com\n\n"
        "🌟 Geri bildirimleriniz için teşekkür ederiz!"
    )
    
    if update.callback_query:
        await update.callback_query.edit_message_text(message, reply_markup=get_main_keyboard())
    else:
        await update.message.reply_text(message, reply_markup=get_main_keyboard())

def main():
    """Bot'u başlatır"""
    # Veritabanını başlat
    init_db()
    
    logger.info("🚀 Namaz Vakitleri Bot başlatılıyor...")
    application = Application.builder().token(TOKEN).build()

    # Komut işleyicilerini ekle
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("vakitler", vakitler))
    application.add_handler(CommandHandler("sehirler", sehirler))
    application.add_handler(CommandHandler("bildirim", bildirim))
    application.add_handler(CommandHandler("bildirim_kapat", bildirim_kapat))
    application.add_handler(CommandHandler("bildirim_durum", bildirim_durum))
    application.add_handler(CommandHandler("iletisim", iletisim))
    application.add_handler(CommandHandler("temizle", temizle))
    application.add_handler(CommandHandler("aciklama", aciklama))
    application.add_handler(CommandHandler("bildirim_ayarla", bildirim_ayarla))
    application.add_handler(CommandHandler("grup_ayarla", grup_ayarla))
    application.add_handler(CommandHandler("arkadas_oner", arkadas_oner))
    
    # Mesaj ve buton işleyicilerini ekle
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Inline arama işleyicisini ekle
    application.add_handler(InlineQueryHandler(sehir_ara))
    
    logger.info("✅ Komut işleyicileri yüklendi")

    # Bildirim gönderme işini her dakika kontrol et
    job_queue = application.job_queue
    job_queue.run_repeating(bildirim_gonder, interval=60, first=0)
    logger.info("✅ Bildirim sistemi aktif edildi")

    # Bot'u başlat
    logger.info("🤖 Bot hazır! Ctrl+C ile kapatabilirsiniz.")
    application.run_polling()

if __name__ == '__main__':
    main() 