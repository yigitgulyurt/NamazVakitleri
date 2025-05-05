from flask import Flask, render_template, jsonify, request, session, redirect, url_for, send_from_directory
from datetime import datetime, timedelta
import json
import os
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import requests
from flask_cors import CORS
import logging
from logging.handlers import RotatingFileHandler
import pytz

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///imsakiye.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Loglama ayarları
log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs', 'imsakiye-python-access.log')
os.makedirs(os.path.dirname(log_file), exist_ok=True)

# Log formatını özelleştir
log_formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
log_handler = RotatingFileHandler(log_file, maxBytes=10000000, backupCount=5)
log_handler.setFormatter(log_formatter)

# Diğer modüllerin log seviyesini ayarla
logging.getLogger('werkzeug').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy').setLevel(logging.WARNING)

app.logger.addHandler(log_handler)
app.logger.setLevel(logging.INFO)

# Loglanacak ana sayfalar
LOGGED_PAGES = {
    '/sehir-secimi',
    '/sehir/',
    '/ulke/'
}

# Loglama middleware'i
@app.before_request
def log_request_info():
    path = request.path
    
    # Sadece ana sayfaları logla
    if not any(path.startswith(page) for page in LOGGED_PAGES):
        return
        
    # API isteklerini loglama
    if '/api/' in path:
        return
        
    # Service worker ve browser cache isteklerini loglama
    if any(path.endswith(ext) for ext in ['.js', '.css', '.ico', '.png', '.jpg', '.svg']):
        return
        
    try:
        # Türkiye saatini kullan
        turkey_tz = pytz.timezone('Europe/Istanbul')
        now = datetime.now(turkey_tz)
        
        # IP adresini al
        if request.headers.get('X-Forwarded-For'):
            ip = request.headers.get('X-Forwarded-For').split(',')[0]
        else:
            ip = request.remote_addr
            
        # Sadece sayfa ziyaretini logla
        log_line = f'{ip} ziyaret: {path}'
        app.logger.info(log_line)
    except Exception as e:
        app.logger.error(f"Loglama hatası: {str(e)}")

# Instagram in-app browser kontrolü
@app.before_request
def check_instagram_browser():
    user_agent = request.headers.get('User-Agent', '').lower()
    if 'instagram' in user_agent and ('fbav' in user_agent or 'instagram' in user_agent):
        return render_template('open_in_browser.html')

# Apache2 için WSGI uygulaması
application = app

# Uygulama kök dizinini al
APP_ROOT = os.path.dirname(os.path.abspath(__file__))

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Veritabani Modelleri
class Kullanici(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sehir = db.Column(db.String(50))
    olusturma_tarihi = db.Column(db.DateTime, default=datetime.utcnow)

class NamazVakti(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sehir = db.Column(db.String(50), nullable=False)
    tarih = db.Column(db.Date, nullable=False)
    imsak = db.Column(db.String(5))
    gunes = db.Column(db.String(5))
    ogle = db.Column(db.String(5))
    ikindi = db.Column(db.String(5))
    aksam = db.Column(db.String(5))
    yatsi = db.Column(db.String(5))

# Ramazan 2025 başlangıç ve bitiş tarihleri
RAMAZAN_BASLANGIC = datetime(2025, 3, 1)
RAMAZAN_BITIS = datetime(2025, 4, 29)

def get_current_date():
    """
    Ramazan ayı içindeki geçerli tarihi döndürür.
    Eğer bugün Ramazan ayı dışındaysa, Ramazan'ın ilk gününü döndürür.
    """
    bugun = datetime.now()
    if RAMAZAN_BASLANGIC <= bugun <= RAMAZAN_BITIS:
        return bugun
    return RAMAZAN_BASLANGIC

def namaz_vakitlerini_al(sehir, tarih):
    try:
        # namaz_vakitleri.json dosyasının tam yolunu oluştur
        json_dosya_yolu = os.path.join(APP_ROOT, 'static/namaz_vakitleri.json')
        
        # Dosyanın varlığını kontrol et
        if not os.path.exists(json_dosya_yolu):
            print(f"Hata: {json_dosya_yolu} dosyasi bulunamadi!")
            return {
                "imsak": "null", "gunes": "null", "ogle": "null",
                "ikindi": "null", "aksam": "null", "yatsi": "null"
            }
        
        # namaz_vakitleri.json dosyasini oku
        with open(json_dosya_yolu, 'r', encoding='utf-8') as f:
            namaz_vakitleri = json.load(f)
        
        # Eger sehir veya tarih listede yoksa varsayilan degerleri kullan
        if sehir not in namaz_vakitleri or tarih.strftime("%Y-%m-%d") not in namaz_vakitleri[sehir]:
            return {
                "imsak": "null", "gunes": "null", "ogle": "null",
                "ikindi": "null", "aksam": "null", "yatsi": "null"
            }
        
        return namaz_vakitleri[sehir][tarih.strftime("%Y-%m-%d")]
    except Exception as e:
        print(f"Namaz vakitleri okuma hatasi: {e}")
        print(f"Dosya yolu: {json_dosya_yolu}")
        # Hata durumunda varsayilan degerleri dondur
        return {
            "imsak": "null", "gunes": "null", "ogle": "null",
            "ikindi": "null", "aksam": "null", "yatsi": "null"
        }

def get_daily_content():
    try:
        # JSON dosyasını oku
        with open(os.path.join(APP_ROOT, 'static/data/daily_content.json'), 'r', encoding='utf-8') as file:
            content_data = json.load(file)
            
        # Günün içeriğini seç (gün sayısına göre döngüsel olarak)
        day_of_year = datetime.now().timetuple().tm_yday
        content_index = day_of_year % len(content_data['content'])
        return content_data['content'][content_index]
    except Exception as e:
        print(f"Error loading daily content: {e}")
        return {
            "type": "hadis",
            "text": "Cennet'in sekiz kapısından biri 'Reyyan' adını taşır ki, buradan ancak oruçlular girer.",
            "source": "Buhârî, Savm, 4",
            "translation": {
                "en": "There is a gate in Paradise called Ar-Raiyan, and those who observe fasting will enter through it.",
                "ar": "إن في الجنة بابا يقال له الريان يدخل منه الصائمون"
            }
        }

# Normal rotalar
@app.route('/')
def ana_sayfa():
    return redirect(url_for('sehir_secimi'))

@app.route('/sehir-secimi')
def sehir_secimi():
    return render_template('sehir-secimi.html')

@app.route('/sehir/<sehir>')
def sehir_sayfasi(sehir):
    try:
        # Namaz vakitlerini al
        bugun = datetime.now().strftime('%Y-%m-%d')
        vakitler = namaz_vakitlerini_al_sehir(sehir, bugun)
        
        # Günlük içeriği al
        daily_content = get_daily_content()
        
        return render_template('index.html', sehir=sehir, vakitler=vakitler, daily_content=daily_content)
    except Exception as e:
        return str(e), 500

@app.route('/sehir/<sehir>/tamekran')
def tam_ekran(sehir):
    try:
        # Namaz vakitlerini al
        bugun = datetime.now().strftime('%Y-%m-%d')
        vakitler = namaz_vakitlerini_al_sehir(sehir, bugun)
        
        # Günlük içeriği al
        daily_content = get_daily_content()
        
        return render_template('tam_ekran.html', 
                            sehir=sehir,
                            vakitler=vakitler,
                            daily_content=daily_content)
    except Exception as e:
        return str(e), 500
    
@app.route('/ulke/<ulke>')
def ulke_sayfasi(ulke):
    try:
        # Namaz vakitlerini al
        bugun = datetime.now().strftime('%Y-%m-%d')
        vakitler = namaz_vakitlerini_al_ulke(ulke, bugun)
        
        # Günlük içeriği al
        daily_content = get_daily_content()
        
        return render_template('index.html', sehir=ulke, vakitler=vakitler, ulke=True, daily_content=daily_content)
    except Exception as e:
        return str(e), 500

@app.route('/api/sehirler')
def sehirleri_getir():
    # Turkiye'nin tum illeri
    sehirler = [
        "Adana", "Adiyaman", "Afyonkarahisar", "Agri", "Aksaray", "Amasya", "Ankara", "Antalya", "Ardahan", "Artvin",
        "Aydin", "Balikesir", "Batman", "Bayburt", "Bilecik", "Bingol", "Bitlis", "Bolu", "Burdur", "Bursa",
        "Canakkale", "Cankiri", "Corum", "Denizli", "Diyarbakir", "Duzce", "Edirne", "Elazig", "Erzincan", "Erzurum",
        "Eskisehir", "Gaziantep", "Giresun", "Gumushane", "Hakkari", "Hatay", "Igdir", "Isparta", "Istanbul", "Izmir",
        "Kahramanmaras", "Karabuk", "Karaman", "Kars", "Kastamonu", "Kayseri", "Kirikkale", "Kirklareli", "Kirsehir",
        "Kilis", "Kocaeli", "Konya", "Kutahya", "Malatya", "Manisa", "Mardin", "Mersin", "Mugla", "Mus", "Nevsehir",
        "Nigde", "Ordu", "Osmaniye", "Rize", "Sakarya", "Samsun", "Sanliurfa", "Siirt", "Sinop", "Sirnak", "Sivas",
        "Tekirdag", "Tokat", "Trabzon", "Tunceli", "Usak", "Van", "Yalova", "Yozgat", "Zonguldak"
    ]
    return jsonify(sehirler)

@app.route('/api/sehir_kaydet', methods=['POST'])
def sehir_kaydet():
    data = request.get_json()
    sehir = data.get('sehir')
    vakitler = data.get('vakitler', {})
    
    if not sehir:
        return jsonify({'error': 'Sehir bilgisi gerekli'}), 400
    
    session['sehir'] = sehir
    session['vakitler'] = vakitler
    
    return jsonify({'redirect': f'/sehir/{sehir}'})

@app.route('/api/ulke_kaydet', methods=['POST'])
def ulke_kaydet():
    data = request.get_json()
    ulke = data.get('ulke')
    vakitler = data.get('vakitler', {})
    
    if not ulke:
        return jsonify({'error': 'Ulke bilgisi gerekli'}), 400
    
    session['ulke'] = ulke
    session['vakitler'] = vakitler
    
    return jsonify({'redirect': f'/ulke/{ulke}'})

@app.route('/api/namaz_vakitleri')
def namaz_vakitlerini_al_api():
    sehir = request.args.get('sehir')
    ulke = request.args.get('ulke')
    tarih = request.args.get('date')  # Yeni tarih parametresi
    
    if not sehir and not ulke:
        return jsonify({'error': 'Sehir veya ulke bilgisi gerekli'}), 400
    
    try:
        if ulke:
            # Ülke için vakitleri al
            vakitler = namaz_vakitlerini_al_ulke(ulke, tarih)
        else:
            # Şehir için vakitleri al
            vakitler = namaz_vakitlerini_al_sehir(sehir, tarih)
            
        return jsonify({'vakitler': vakitler})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def namaz_vakitlerini_al_sehir(sehir, tarih=None):
    try:
        # JSON dosyasını oku
        json_dosya_yolu = os.path.join(APP_ROOT, 'static/namaz_vakitleri.json')
        with open(json_dosya_yolu, 'r', encoding='utf-8') as file:
            vakitler_data = json.load(file)
        
        # Eğer tarih belirtilmemişse, geçerli tarihi kullan
        if not tarih:
            bugun = get_current_date()
            tarih = bugun.strftime("%Y-%m-%d")
        
        # Şehir için vakitleri kontrol et
        if sehir in vakitler_data and tarih in vakitler_data[sehir]:
            return vakitler_data[sehir][tarih]
        else:
            print(f"Veri bulunamadı: {sehir}, {tarih}")
            return {
                'imsak': '--:--',
                'gunes': '--:--',
                'ogle': '--:--',
                'ikindi': '--:--',
                'aksam': '--:--',
                'yatsi': '--:--'
            }
    except Exception as e:
        print(f"Hata: {e}")
        print(f"Dosya yolu: {json_dosya_yolu}")
        return {
            'imsak': '--:--',
            'gunes': '--:--',
            'ogle': '--:--',
            'ikindi': '--:--',
            'aksam': '--:--',
            'yatsi': '--:--'
        }

def namaz_vakitlerini_al_ulke(ulke, tarih=None):
    try:
        # JSON dosyasını oku
        json_dosya_yolu = os.path.join(APP_ROOT, 'static/namaz_vakitleri.json')
        with open(json_dosya_yolu, 'r', encoding='utf-8') as file:
            vakitler_data = json.load(file)
        
        # Eğer tarih belirtilmemişse, geçerli tarihi kullan
        if not tarih:
            bugun = get_current_date()
            tarih = bugun.strftime("%Y-%m-%d")
        
        # Ülke için vakitleri kontrol et
        if ulke in vakitler_data and tarih in vakitler_data[ulke]:
            return vakitler_data[ulke][tarih]
        else:
            print(f"Veri bulunamadı: {ulke}, {tarih}")
            return {
                'imsak': '--:--',
                'gunes': '--:--',
                'ogle': '--:--',
                'ikindi': '--:--',
                'aksam': '--:--',
                'yatsi': '--:--'
            }
    except Exception as e:
        print(f"Hata: {e}")
        print(f"Dosya yolu: {json_dosya_yolu}")
        return {
            'imsak': '--:--',
            'gunes': '--:--',
            'ogle': '--:--',
            'ikindi': '--:--',
            'aksam': '--:--',
            'yatsi': '--:--'
        }

@app.route('/api/sonraki_vakit')
def sonraki_vakti_getir():
    sehir = request.args.get('sehir')
    if not sehir:
        return jsonify({"error": "Sehir gerekli"}), 400
    
    simdi = datetime.now()
    bugun = simdi.date()
    bugun_str = bugun.strftime("%Y-%m-%d")
    
    # Bugünün vakitleri
    vakitler = namaz_vakitlerini_al(sehir, bugun)
    
    # Yarının tarihi ve vakitleri
    yarin = bugun + timedelta(days=1)
    yarin_str = yarin.strftime("%Y-%m-%d")
    yarin_vakitler = namaz_vakitlerini_al(sehir, yarin)
    
    vakit_sirasi = ["imsak", "gunes", "ogle", "ikindi", "aksam", "yatsi"]
    sonraki_vakit_adi = None
    kalan_saniye = None
    
    # Önce bugünün vakitlerini kontrol et
    for vakit in vakit_sirasi:
        vakit_str = vakitler[vakit]
        if vakit_str == "null":
            continue
            
        try:
            vakit_zamani = datetime.strptime(f"{bugun_str} {vakit_str}", "%Y-%m-%d %H:%M")
            
            # İmsak vakti için her zaman yarının vaktini göster
            if vakit == "imsak":
                yarin_imsak_str = yarin_vakitler["imsak"]
                if yarin_imsak_str != "null":
                    vakit_zamani = datetime.strptime(f"{yarin_str} {yarin_imsak_str}", "%Y-%m-%d %H:%M")
            
            # Akşam vakti için özel kontrol
            elif vakit == "aksam":
                # Eğer akşam vakti geçtiyse ve saat 00:00'ı geçmediyse, süre 0 olarak kalsın
                if vakit_zamani < simdi and simdi.hour < 24:
                    return jsonify({
                        "sonraki_vakit": "aksam",
                        "vakit": vakit_str,
                        "kalan_sure": 0,
                        "vakit_gecti": True
                    })
                # Eğer saat 00:00'ı geçtiyse, yarının akşam vaktini göster
                elif simdi.hour >= 0 and vakit_zamani < simdi:
                    yarin_aksam_str = yarin_vakitler["aksam"]
                    if yarin_aksam_str != "null":
                        vakit_zamani = datetime.strptime(f"{yarin_str} {yarin_aksam_str}", "%Y-%m-%d %H:%M")
            
            if vakit_zamani > simdi:
                sonraki_vakit_adi = vakit
                kalan_saniye = (vakit_zamani - simdi).total_seconds()
                break
        except ValueError:
            continue
    
    # Eğer bugün için sonraki vakit bulunamadıysa ve saat 00:00'ı geçtiyse
    if sonraki_vakit_adi is None and simdi.hour >= 0:
        try:
            # Yarının vakitlerini kontrol et
            for vakit in vakit_sirasi:
                vakit_str = yarin_vakitler[vakit]
                if vakit_str == "null":
                    continue
                    
                vakit_zamani = datetime.strptime(f"{yarin_str} {vakit_str}", "%Y-%m-%d %H:%M")
                sonraki_vakit_adi = vakit
                kalan_saniye = (vakit_zamani - simdi).total_seconds()
                break
        except ValueError:
            pass
    
    if sonraki_vakit_adi is None:
        return jsonify({
            "sonraki_vakit": "aksam",
            "vakit": vakitler["aksam"],
            "kalan_sure": 0,
            "vakit_gecti": True
        })
    
    return jsonify({
        "sonraki_vakit": sonraki_vakit_adi,
        "vakit": yarin_vakitler[sonraki_vakit_adi] if sonraki_vakit_adi == "imsak" else vakitler[sonraki_vakit_adi],
        "kalan_sure": int(kalan_saniye) if kalan_saniye is not None else 0,
        "vakit_gecti": False
    })

@app.route('/api/reset_db')
def reset_db():
    try:
        # Veritabanı dosyasını sil
        if os.path.exists('imsakiye.db'):
            os.remove('imsakiye.db')
        return jsonify({"success": True, "message": "Veritabani sifirlandi"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/update_city', methods=['POST'])
def update_city():
    try:
        data = request.get_json()
        new_city = data.get('sehir')
        if not new_city:
            return jsonify({"success": False, "error": "Sehir gerekli"})
        
        user = Kullanici.query.first()
        if user:
            user.sehir = new_city
        else:
            user = Kullanici(sehir=new_city)
            db.session.add(user)
        
        db.session.commit()
        return jsonify({"success": True, "message": f"Sehir {new_city} olarak guncellendi"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/current_date')
def get_current_date_info():
    current_date = get_current_date()
    return jsonify({
        'date': current_date.strftime("%Y-%m-%d"),
        'is_ramadan': RAMAZAN_BASLANGIC <= current_date <= RAMAZAN_BITIS
    })

@app.route('/api/daily_content')
def daily_content():
    return jsonify(get_daily_content())

@app.route('/offline')
def offline():
    return render_template('offline.html')

@app.route('/progressier.js')
def serve_service_worker():
    return send_from_directory('.', 'progressier.js')

@app.route('/sitemap.xml')
def serve_sitemap():
    return send_from_directory('.', 'sitemap.xml')

@app.route('/robots.txt')
def serve_robots():
    return send_from_directory('.', 'robots.txt')

@app.route('/privacy-policy')
def privacy_policy():
    return render_template('privacy_policy.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)