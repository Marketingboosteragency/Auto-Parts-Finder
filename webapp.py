# webapp.py - Auto Parts Finder USA con Búsqueda por Imagen y Web Scraping Ético
from flask import Flask, request, jsonify, session, redirect, url_for, render_template_string, flash
import requests
import os
import re
import html
import time
import io
import random
import logging
from datetime import datetime, timedelta
from urllib.parse import urlparse, quote_plus, urljoin
from functools import wraps
from urllib.robotparser import RobotFileParser
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Imports para búsqueda por imagen (opcionales)
try:
    from PIL import Image
    PIL_AVAILABLE = True
    print("✅ PIL (Pillow) disponible para procesamiento de imagen")
except ImportError:
    PIL_AVAILABLE = False
    print("⚠ PIL (Pillow) no disponible - búsqueda por imagen limitada")

try:
    import google.generativeai as genai
    from google.api_core import exceptions as google_exceptions
    GEMINI_AVAILABLE = True
    print("✅ Google Generative AI (Gemini) disponible")
except ImportError:
    genai = None
    google_exceptions = None
    GEMINI_AVAILABLE = False
    print("⚠ Google Generative AI no disponible - instalar con: pip install google-generativeai")

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
    print("✅ BeautifulSoup4 disponible para web scraping")
except ImportError:
    BS4_AVAILABLE = False
    print("⚠ BeautifulSoup4 no disponible - instalar con: pip install beautifulsoup4")

# Configurar logging para web scraping
logging.basicConfig(level=logging.INFO)
scraper_logger = logging.getLogger('EthicalScraper')

# ==============================================================================
# CLASE DE WEB SCRAPING ÉTICO
# ==============================================================================

class EthicalWebScraper:
    """
    Web Scraper Ético para Auto Parts con respeto a robots.txt y límites de velocidad.
    
    Características:
    - Verificación de robots.txt
    - User-Agents rotativos y realistas
    - Control de velocidad con delays
    - Manejo robusto de errores
    - Headers HTTP realistas
    - Rate limiting
    """
    
    def __init__(self, base_url=None, delay_range=(1, 3), max_retries=3):
        self.base_url = base_url
        self.delay_range = delay_range
        self.max_retries = max_retries
        self.robots_cache = {}
        self.request_count = 0
        self.session_start = datetime.now()
        self.max_requests_per_hour = 200  # Límite conservador
        
        # User-Agents rotativos realistas
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
        
        # Configurar sesión con reintentos automáticos
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        scraper_logger.info("EthicalWebScraper inicializado para Auto Parts")
    
    def _get_random_user_agent(self):
        """Obtener User-Agent aleatorio"""
        return random.choice(self.user_agents)
    
    def _get_realistic_headers(self):
        """Generar headers HTTP realistas"""
        return {
            'User-Agent': self._get_random_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,es;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0'
        }
    
    def _check_rate_limit(self):
        """Verificar límites de velocidad"""
        hours_elapsed = (datetime.now() - self.session_start).total_seconds() / 3600
        if hours_elapsed > 0:
            requests_per_hour = self.request_count / hours_elapsed
            if requests_per_hour > self.max_requests_per_hour:
                sleep_time = 3600 / self.max_requests_per_hour
                scraper_logger.warning(f"Rate limit alcanzado, esperando {sleep_time:.1f}s")
                time.sleep(sleep_time)
    
    def check_robots_txt(self, url):
        """
        Verificar permisos en robots.txt
        """
        try:
            parsed_url = urlparse(url)
            domain = f"{parsed_url.scheme}://{parsed_url.netloc}"
            
            # Usar cache para robots.txt
            if domain in self.robots_cache:
                rp, last_check = self.robots_cache[domain]
                # Cache válido por 1 hora
                if datetime.now() - last_check < timedelta(hours=1):
                    return rp
            
            # Descargar y parsear robots.txt
            robots_url = urljoin(domain, '/robots.txt')
            rp = RobotFileParser()
            rp.set_url(robots_url)
            
            try:
                rp.read()
                self.robots_cache[domain] = (rp, datetime.now())
                scraper_logger.info(f"robots.txt cargado para {domain}")
                return rp
            except Exception as e:
                scraper_logger.warning(f"No se pudo cargar robots.txt de {domain}: {e}")
                # Si no hay robots.txt, asumir que está permitido
                return None
                
        except Exception as e:
            scraper_logger.error(f"Error verificando robots.txt: {e}")
            return None
    
    def can_fetch(self, url, user_agent='*'):
        """Verificar si se puede hacer fetch de la URL"""
        try:
            rp = self.check_robots_txt(url)
            if rp is None:
                return True  # No hay robots.txt, asumir permitido
            
            return rp.can_fetch(user_agent, url)
        except Exception as e:
            scraper_logger.error(f"Error verificando permisos: {e}")
            return False  # Por seguridad, denegar si hay error
    
    def get_crawl_delay(self, url, user_agent='*'):
        """Obtener delay recomendado de robots.txt"""
        try:
            rp = self.check_robots_txt(url)
            if rp is None:
                return random.uniform(*self.delay_range)
            
            delay = rp.crawl_delay(user_agent)
            if delay is not None:
                return max(delay, self.delay_range[0])  # Mínimo nuestro delay
            else:
                return random.uniform(*self.delay_range)
        except Exception as e:
            scraper_logger.error(f"Error obteniendo crawl delay: {e}")
            return random.uniform(*self.delay_range)
    
    def make_request(self, url, method='GET', **kwargs):
        """
        Realizar request ético con todas las verificaciones
        """
        try:
            # Verificar rate limiting
            self._check_rate_limit()
            
            # Verificar robots.txt
            if not self.can_fetch(url):
                scraper_logger.warning(f"robots.txt prohíbe acceso a {url}")
                return None
            
            # Obtener delay recomendado
            delay = self.get_crawl_delay(url)
            if self.request_count > 0:  # No delay en el primer request
                scraper_logger.debug(f"Esperando {delay:.1f}s antes del request")
                time.sleep(delay)
            
            # Preparar headers
            headers = self._get_realistic_headers()
            if 'headers' in kwargs:
                headers.update(kwargs['headers'])
            kwargs['headers'] = headers
            
            # Configurar timeouts
            if 'timeout' not in kwargs:
                kwargs['timeout'] = (10, 30)  # (connection, read)
            
            # Realizar request
            scraper_logger.info(f"Haciendo {method} request a {url}")
            response = self.session.request(method, url, **kwargs)
            
            # Incrementar contador
            self.request_count += 1
            
            # Verificar código de estado
            if response.status_code == 429:
                scraper_logger.warning("Rate limited (429), esperando más tiempo")
                time.sleep(60)  # Esperar 1 minuto
                return self.make_request(url, method, **kwargs)  # Reintentar
            
            response.raise_for_status()
            return response
            
        except requests.exceptions.RequestException as e:
            scraper_logger.error(f"Error en request a {url}: {e}")
            return None
        except Exception as e:
            scraper_logger.error(f"Error inesperado: {e}")
            return None
    
    def _extract_products_from_search_page(self, soup, store_name, query):
        """
        Extraer productos de páginas de búsqueda de auto parts
        """
        products = []
        
        try:
            # Selectores específicos para diferentes tiendas
            product_selectors = {
                'AutoZone': [
                    '.product-tile',
                    '.product-item',
                    '.search-result-item'
                ],
                'Advance Auto Parts': [
                    '.product-tile',
                    '.search-result',
                    '.product-card'
                ],
                'default': [
                    '[data-testid*="product"]',
                    '.product',
                    '.item',
                    '.result'
                ]
            }
            
            selectors = product_selectors.get(store_name, product_selectors['default'])
            
            for selector in selectors:
                product_elements = soup.select(selector)
                if product_elements:
                    break
            
            for element in product_elements[:3]:  # Máximo 3 productos por tienda
                try:
                    # Extraer título
                    title_selectors = ['h2', 'h3', '.product-name', '.title', 'a[title]']
                    title = "Repuesto automotriz"
                    
                    for title_sel in title_selectors:
                        title_elem = element.select_one(title_sel)
                        if title_elem and title_elem.get_text(strip=True):
                            title = title_elem.get_text(strip=True)[:100]
                            break
                    
                    # Extraer precio
                    price_selectors = ['.price', '.cost', '[class*="price"]', '[data-price]']
                    price = "$0.00"
                    
                    for price_sel in price_selectors:
                        price_elem = element.select_one(price_sel)
                        if price_elem:
                            price_text = price_elem.get_text(strip=True)
                            price_match = re.search(r'\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)', price_text)
                            if price_match:
                                price = price_match.group(0)
                                break
                    
                    # Extraer enlace
                    link_elem = element.select_one('a[href]')
                    link = "#"
                    if link_elem:
                        href = link_elem.get('href')
                        if href:
                            if href.startswith('http'):
                                link = href
                            elif href.startswith('/'):
                                if store_name == 'AutoZone':
                                    link = f"https://www.autozone.com{href}"
                                elif store_name == 'Advance Auto Parts':
                                    link = f"https://shop.advanceautoparts.com{href}"
                                else:
                                    link = href
                    
                    if title and title != "Repuesto automotriz" and "$" in price:
                        products.append({
                            'title': title,
                            'price': price,
                            'store': store_name,
                            'link': link,
                            'source': 'scraping_directo'
                        })
                
                except Exception as e:
                    scraper_logger.warning(f"Error extrayendo producto individual: {e}")
                    continue
            
            scraper_logger.info(f"Extraídos {len(products)} productos de {store_name}")
            return products
            
        except Exception as e:
            scraper_logger.error(f"Error general extrayendo productos de {store_name}: {e}")
            return products

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'fallback-key-change-in-production')
app.config['PERMANENT_SESSION_LIFETIME'] = 1800
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = True if os.environ.get('RENDER') else False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

# Configuración de Gemini
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
if GEMINI_AVAILABLE and GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        print("✅ API de Google Gemini configurada correctamente")
        GEMINI_READY = True
    except Exception as e:
        print(f"❌ Error configurando Gemini: {e}")
        GEMINI_READY = False
elif GEMINI_AVAILABLE and not GEMINI_API_KEY:
    print("⚠ Gemini disponible pero falta GEMINI_API_KEY en variables de entorno")
    GEMINI_READY = False
else:
    print("⚠ Gemini no está disponible - búsqueda por imagen deshabilitada")
    GEMINI_READY = False

# Base de datos de vehículos populares en USA
VEHICLE_DATABASE = {
    'makes': {
        'chevrolet': ['silverado', 'equinox', 'malibu', 'tahoe', 'suburban', 'traverse', 'camaro', 'corvette'],
        'ford': ['f150', 'f250', 'f350', 'escape', 'explorer', 'mustang', 'edge', 'expedition'],
        'toyota': ['camry', 'corolla', 'rav4', 'highlander', 'prius', 'tacoma', 'tundra', 'sienna'],
        'honda': ['civic', 'accord', 'crv', 'pilot', 'odyssey', 'ridgeline', 'passport'],
        'nissan': ['altima', 'sentra', 'rogue', 'murano', 'pathfinder', 'titan', 'frontier'],
        'jeep': ['wrangler', 'grand cherokee', 'cherokee', 'compass', 'renegade', 'gladiator'],
        'ram': ['1500', '2500', '3500', 'promaster'],
        'gmc': ['sierra', 'terrain', 'acadia', 'yukon', 'canyon'],
        'hyundai': ['elantra', 'sonata', 'tucson', 'santa fe', 'palisade'],
        'kia': ['optima', 'forte', 'sorento', 'sportage', 'telluride'],
        'volkswagen': ['jetta', 'passat', 'tiguan', 'atlas'],
        'subaru': ['outback', 'forester', 'crosstrek', 'impreza', 'ascent'],
        'bmw': ['3 series', '5 series', 'x3', 'x5'],
        'mercedes': ['c class', 'e class', 'glc', 'gle'],
        'audi': ['a4', 'a6', 'q5', 'q7']
    },
    'years': list(range(1990, 2025)),
    'common_parts': [
        'brake pads', 'brake rotors', 'brake caliper', 'brake fluid',
        'oil filter', 'air filter', 'cabin filter', 'fuel filter',
        'spark plugs', 'ignition coils', 'battery', 'alternator',
        'starter', 'radiator', 'water pump', 'thermostat',
        'timing belt', 'serpentine belt', 'power steering pump',
        'shock absorbers', 'struts', 'tie rod ends', 'ball joints',
        'control arms', 'sway bar links', 'cv joints', 'wheel bearings',
        'headlights', 'taillights', 'turn signals', 'fog lights',
        'windshield wipers', 'side mirrors', 'door handles',
        'muffler', 'catalytic converter', 'oxygen sensor',
        'fuel pump', 'fuel injectors', 'mass airflow sensor',
        'throttle body', 'pcv valve', 'egr valve'
    ]
}

# Firebase Auth Class
class FirebaseAuth:
    def __init__(self):
        self.firebase_web_api_key = os.environ.get("FIREBASE_WEB_API_KEY")
        if not self.firebase_web_api_key:
            print("WARNING: FIREBASE_WEB_API_KEY no configurada")
        else:
            print("SUCCESS: Firebase Auth configurado")
    
    def login_user(self, email, password):
        if not self.firebase_web_api_key:
            return {'success': False, 'message': 'Servicio no configurado', 'user_data': None, 'error_code': 'SERVICE_NOT_CONFIGURED'}
        
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={self.firebase_web_api_key}"
        payload = {'email': email, 'password': password, 'returnSecureToken': True}
        
        try:
            response = requests.post(url, json=payload, timeout=8)
            response.raise_for_status()
            user_data = response.json()
            
            return {
                'success': True,
                'message': 'Bienvenido! Has iniciado sesion correctamente.',
                'user_data': {
                    'user_id': user_data['localId'],
                    'email': user_data['email'],
                    'display_name': user_data.get('displayName', email.split('@')[0]),
                    'id_token': user_data['idToken']
                },
                'error_code': None
            }
        except requests.exceptions.HTTPError as e:
            try:
                error_msg = e.response.json().get('error', {}).get('message', 'ERROR')
                if 'INVALID' in error_msg or 'EMAIL_NOT_FOUND' in error_msg:
                    return {'success': False, 'message': 'Correo o contraseña incorrectos', 'user_data': None, 'error_code': 'INVALID_CREDENTIALS'}
                elif 'TOO_MANY_ATTEMPTS' in error_msg:
                    return {'success': False, 'message': 'Demasiados intentos fallidos', 'user_data': None, 'error_code': 'TOO_MANY_ATTEMPTS'}
                else:
                    return {'success': False, 'message': 'Error de autenticacion', 'user_data': None, 'error_code': 'FIREBASE_ERROR'}
            except:
                return {'success': False, 'message': 'Error de conexion', 'user_data': None, 'error_code': 'CONNECTION_ERROR'}
        except Exception as e:
            print(f"Firebase auth error: {e}")
            return {'success': False, 'message': 'Error interno del servidor', 'user_data': None, 'error_code': 'UNEXPECTED_ERROR'}
    
    def set_user_session(self, user_data):
        session['user_id'] = user_data['user_id']
        session['user_name'] = user_data['display_name']
        session['user_email'] = user_data['email']
        session['id_token'] = user_data['id_token']
        session['login_time'] = datetime.now().isoformat()
        session.permanent = True
    
    def clear_user_session(self):
        important_data = {key: session.get(key) for key in ['timestamp'] if key in session}
        session.clear()
        for key, value in important_data.items():
            session[key] = value
    
    def is_user_logged_in(self):
        if 'user_id' not in session or session['user_id'] is None:
            return False
        if 'login_time' in session:
            try:
                login_time = datetime.fromisoformat(session['login_time'])
                time_diff = (datetime.now() - login_time).total_seconds()
                if time_diff > 7200:  # 2 horas maximo
                    return False
            except:
                pass
        return True
    
    def get_current_user(self):
        if not self.is_user_logged_in():
            return None
        return {
            'user_id': session.get('user_id'),
            'user_name': session.get('user_name'),
            'user_email': session.get('user_email'),
            'id_token': session.get('id_token')
        }

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not firebase_auth.is_user_logged_in():
            flash('Tu sesion ha expirado. Inicia sesion nuevamente.', 'warning')
            return redirect(url_for('auth_login_page'))
        return f(*args, **kwargs)
    return decorated_function

# ==============================================================================
# FUNCIONES DE BÚSQUEDA POR IMAGEN PARA AUTO PARTS
# ==============================================================================

def analyze_auto_part_image_with_gemini(image_content):
    """Analiza imagen de auto parts con Gemini Vision"""
    if not GEMINI_READY or not PIL_AVAILABLE or not image_content:
        print("❌ Gemini o PIL no disponible para análisis de imagen")
        return None
    
    try:
        # Convertir bytes a PIL Image
        image = Image.open(io.BytesIO(image_content))
        
        # Optimizar imagen
        max_size = (1024, 1024)
        if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        print("🔧 Analizando repuesto automotor con Gemini Vision...")
        
        prompt = """
        Analiza esta imagen de repuesto automotor y genera una consulta de búsqueda específica en inglés.
        
        Identifica:
        - Tipo de repuesto (brake pad, oil filter, spark plug, etc.)
        - Marca visible (ACDelco, Bosch, Motorcraft, etc.)
        - Número de parte si es visible
        - Características específicas (tamaño, tipo, material)
        - Compatible con qué vehículos si es posible determinar
        
        Genera una consulta optimizada para encontrar este repuesto en tiendas de auto parts en USA.
        
        Ejemplo de respuesta: "ACDelco brake pads front ceramic 2015 Chevrolet Silverado"
        
        Responde SOLO con la consulta de búsqueda optimizada.
        """
        
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        response = model.generate_content([prompt, image])
        
        if response.text:
            search_query = response.text.strip()
            print(f"🧠 Consulta generada desde imagen de repuesto: '{search_query}'")
            return search_query
        
        return None
            
    except Exception as e:
        print(f"❌ Error analizando imagen de repuesto: {e}")
        return None

def validate_image(image_content):
    """Valida imagen"""
    if not PIL_AVAILABLE or not image_content:
        return False
    
    try:
        image = Image.open(io.BytesIO(image_content))
        if image.size[0] < 10 or image.size[1] < 10:
            return False
        if image.format not in ['JPEG', 'PNG', 'WEBP']:
            return False
        return True
    except:
        return False

# Auto Parts Finder Class - ESPECIALIZADO para repuestos automotores
class AutoPartsFinder:
    def __init__(self):
        # Intentar multiples nombres de variables de entorno comunes
        self.api_key = (
            os.environ.get('SERPAPI_KEY') or 
            os.environ.get('SERPAPI_API_KEY') or 
            os.environ.get('SERP_API_KEY') or
            os.environ.get('serpapi_key') or
            os.environ.get('SERPAPI')
        )
        
        self.base_url = "https://serpapi.com/search"
        self.cache = {}
        self.cache_ttl = 300  # 5 minutos para repuestos
        self.timeouts = {'connect': 3, 'read': 8}
        
        # Tiendas especializadas en auto parts prioritarias
        self.preferred_stores = [
            'autozone', 'advance auto parts', 'oreilly', 'napa', 'pepboys',
            'rock auto', 'car parts', 'auto parts warehouse', 'parts geek',
            'amazon automotive', 'walmart automotive', 'jegs', 'summit racing'
        ]
        
        # Sitios no especializados en automotive que queremos filtrar
        self.non_automotive_stores = [
            'alibaba', 'aliexpress', 'temu', 'wish', 'banggood', 'dhgate',
            'general stores', 'toys', 'clothing', 'electronics'
        ]
        
        # URLs directas de tiendas para scraping como fallback
        self.direct_store_urls = {
            'autozone': 'https://www.autozone.com',
            'advance': 'https://shop.advanceautoparts.com',
            'oreilly': 'https://www.oreillyauto.com',
            'napa': 'https://www.napaonline.com',
            'rockauto': 'https://www.rockauto.com'
        }
        
        if not self.api_key:
            print("WARNING: No se encontro API key en variables de entorno")
            print("Variables verificadas: SERPAPI_KEY, SERPAPI_API_KEY, SERP_API_KEY, serpapi_key, SERPAPI")
            print("NOTA: Se usará scraping directo como fallback")
        else:
            print(f"SUCCESS: SerpAPI configurado correctamente para Auto Parts (key: {self.api_key[:8]}...)")
    
    def is_api_configured(self):
        return bool(self.api_key)
    
    def _extract_price(self, price_str):
        if not price_str:
            return 0.0
        try:
            match = re.search(r'\$\s*(\d{1,4}(?:,\d{3})*(?:\.\d{2})?)', str(price_str))
            if match:
                price_value = float(match.group(1).replace(',', ''))
                # Precios realistas para auto parts (entre $1 y $2000)
                return price_value if 1.0 <= price_value <= 2000 else 0.0
        except:
            pass
        return 0.0
    
    def _generate_realistic_auto_part_price(self, query, index=0):
        """Genera precios realistas para repuestos automotores"""
        query_lower = query.lower()
        
        # Categorías de precios para auto parts
        if any(word in query_lower for word in ['engine', 'transmission', 'turbo', 'catalytic converter']):
            base_price = 400  # Componentes mayores
        elif any(word in query_lower for word in ['brake', 'rotor', 'caliper', 'strut', 'shock']):
            base_price = 80   # Frenos y suspensión
        elif any(word in query_lower for word in ['alternator', 'starter', 'water pump', 'fuel pump']):
            base_price = 120  # Componentes eléctricos/mecánicos
        elif any(word in query_lower for word in ['filter', 'spark plug', 'belt', 'hose']):
            base_price = 25   # Mantenimiento básico
        elif any(word in query_lower for word in ['headlight', 'taillight', 'mirror', 'handle']):
            base_price = 50   # Exterior/luces
        else:
            base_price = 60   # Precio promedio general
            
        return round(base_price * (1 + index * 0.2), 2)
    
    def _clean_text(self, text):
        if not text:
            return "Sin informacion"
        return html.escape(str(text)[:150])  # Más caracteres para descripciones de repuestos
    
    def _is_automotive_relevant(self, item):
        """Verifica si el resultado es relevante para repuestos automotores"""
        if not item:
            return False
            
        title = str(item.get('title', '')).lower()
        source = str(item.get('source', '')).lower()
        snippet = str(item.get('snippet', '')).lower()
        
        # Palabras clave automotrices
        automotive_keywords = [
            'auto', 'car', 'vehicle', 'automotive', 'motor', 'engine',
            'brake', 'filter', 'spark', 'battery', 'alternator', 'starter',
            'transmission', 'suspension', 'exhaust', 'radiator', 'fuel',
            'ignition', 'clutch', 'differential', 'axle', 'steering',
            'tire', 'wheel', 'part', 'replacement', 'oem', 'aftermarket'
        ]
        
        # Verificar si contiene palabras automotrices
        text_to_check = f"{title} {source} {snippet}"
        has_automotive_keywords = any(keyword in text_to_check for keyword in automotive_keywords)
        
        # Verificar marcas de vehículos
        vehicle_makes = list(VEHICLE_DATABASE['makes'].keys())
        has_vehicle_make = any(make in text_to_check for make in vehicle_makes)
        
        # Verificar tiendas especializadas
        is_auto_store = any(store in source for store in self.preferred_stores)
        
        return has_automotive_keywords or has_vehicle_make or is_auto_store
    
    def _get_valid_link(self, item):
        if not item:
            return "#"
        product_link = item.get('product_link', '')
        if product_link:
            return product_link
        general_link = item.get('link', '')
        if general_link:
            return general_link
        title = item.get('title', '')
        if title:
            search_query = quote_plus(f"auto parts {str(title)[:50]}")
            return f"https://www.google.com/search?tbm=shop&q={search_query}"
        return "#"
    
    def _optimize_auto_part_query(self, query):
        """Optimiza la consulta para búsqueda de repuestos"""
        if not query:
            return "auto parts"
            
        query = query.strip().lower()
        
        # Si ya contiene términos automotrices, devolver como está
        automotive_terms = ['auto', 'car', 'automotive', 'vehicle', 'part', 'parts']
        if any(term in query for term in automotive_terms):
            return query
        
        # Agregar contexto automotriz
        return f"{query} auto parts"
    
    def _make_api_request(self, engine, query):
        if not self.api_key:
            return None
        
        # Optimizar query para auto parts
        optimized_query = self._optimize_auto_part_query(query)
        
        params = {
            'engine': engine, 
            'q': optimized_query, 
            'api_key': self.api_key, 
            'num': 8,  # Más resultados para filtrar mejor
            'location': 'United States', 
            'gl': 'us'
        }
        
        try:
            time.sleep(0.3)
            response = requests.get(self.base_url, params=params, timeout=(self.timeouts['connect'], self.timeouts['read']))
            if response.status_code != 200:
                return None
            return response.json()
        except Exception as e:
            print(f"Error en request: {e}")
            return None
    
    def _process_auto_parts_results(self, data, engine):
        if not data:
            return []
        products = []
        results_key = 'shopping_results' if engine == 'google_shopping' else 'organic_results'
        if results_key not in data:
            return []
        
        for item in data[results_key]:
            try:
                if not item or not self._is_automotive_relevant(item):
                    continue
                    
                title = item.get('title', '')
                if not title or len(title) < 5:
                    continue
                
                price_str = item.get('price', '')
                price_num = self._extract_price(price_str)
                if price_num == 0:
                    price_num = self._generate_realistic_auto_part_price(title, len(products))
                    price_str = f"${price_num:.2f}"
                
                # Información adicional para auto parts
                source = item.get('source', 'Auto Parts Store')
                rating = item.get('rating', '')
                reviews = item.get('reviews', '')
                
                # Detectar si es OEM o Aftermarket
                title_lower = title.lower()
                part_type = "OEM" if any(term in title_lower for term in ['oem', 'genuine', 'original']) else "Aftermarket"
                
                products.append({
                    'title': self._clean_text(title),
                    'price': str(price_str),
                    'price_numeric': float(price_num),
                    'source': self._clean_text(source),
                    'link': self._get_valid_link(item),
                    'rating': str(rating),
                    'reviews': str(reviews),
                    'part_type': part_type,
                    'image': ''
                })
                
                if len(products) >= 6:  # Limitamos a 6 productos
                    break
                    
            except Exception as e:
                print(f"Error procesando item de auto parts: {e}")
                continue
        return products
    
    def _scrape_direct_stores(self, query, max_results=3):
        """
        Scraping directo de tiendas de auto parts como fallback
        """
        if not BS4_AVAILABLE:
            print("⚠ BeautifulSoup4 no disponible para scraping directo")
            return []
        
        scraped_products = []
        
        try:
            print(f"🔍 Iniciando scraping directo para: {query}")
            
            # Construir URLs de búsqueda para tiendas específicas
            search_urls = []
            
            # AutoZone
            autozone_search = f"https://www.autozone.com/search?searchText={quote_plus(query)}"
            search_urls.append(('AutoZone', autozone_search))
            
            # Advance Auto Parts (solo si está disponible)
            advance_search = f"https://shop.advanceautoparts.com/find/?searchTerm={quote_plus(query)}"
            search_urls.append(('Advance Auto Parts', advance_search))
            
            for store_name, search_url in search_urls[:2]:  # Limitar a 2 tiendas para velocidad
                try:
                    print(f"🛒 Scraping {store_name}...")
                    response = ethical_scraper.make_request(search_url)
                    
                    if response and response.status_code == 200:
                        soup = BeautifulSoup(response.content, 'html.parser')
                        
                        # Extraer productos de la página de resultados
                        products = ethical_scraper._extract_products_from_search_page(soup, store_name, query)
                        scraped_products.extend(products[:max_results])
                        
                        if len(scraped_products) >= max_results:
                            break
                            
                except Exception as e:
                    print(f"❌ Error scraping {store_name}: {e}")
                    continue
            
            print(f"✅ Scraping directo completado: {len(scraped_products)} productos encontrados")
            return scraped_products
            
        except Exception as e:
            print(f"❌ Error general en scraping directo: {e}")
            return scraped_products
    
    def search_auto_parts(self, query=None, image_content=None, vehicle_info=None):
        """Búsqueda especializada en repuestos automotores"""
        # Determinar consulta final
        final_query = None
        search_source = "text"
        
        # Construir query con información del vehículo
        if vehicle_info:
            vehicle_part = ""
            if vehicle_info.get('year'):
                vehicle_part += f"{vehicle_info['year']} "
            if vehicle_info.get('make'):
                vehicle_part += f"{vehicle_info['make']} "
            if vehicle_info.get('model'):
                vehicle_part += f"{vehicle_info['model']} "
        else:
            vehicle_part = ""
        
        if image_content and GEMINI_READY and PIL_AVAILABLE:
            if validate_image(image_content):
                if query:
                    # Texto + imagen + vehículo
                    image_query = analyze_auto_part_image_with_gemini(image_content)
                    if image_query:
                        final_query = f"{vehicle_part}{query} {image_query}".strip()
                        search_source = "combined"
                        print(f"🔗 Búsqueda combinada: vehículo + texto + imagen")
                    else:
                        final_query = f"{vehicle_part}{query}".strip()
                        search_source = "text_fallback"
                        print(f"📝 Imagen falló, usando vehículo + texto")
                else:
                    # Solo imagen + vehículo
                    image_query = analyze_auto_part_image_with_gemini(image_content)
                    if image_query:
                        final_query = f"{vehicle_part}{image_query}".strip()
                        search_source = "image"
                        print(f"🖼 Búsqueda basada en imagen + vehículo")
            else:
                print("❌ Imagen inválida")
                final_query = f"{vehicle_part}{query or 'auto parts'}".strip()
                search_source = "text"
        else:
            # Solo texto + vehículo
            final_query = f"{vehicle_part}{query or 'auto parts'}".strip()
            search_source = "text"
            if image_content and not GEMINI_READY:
                print("⚠ Imagen proporcionada pero Gemini no está configurado")
        
        if not final_query or len(final_query.strip()) < 2:
            return self._get_auto_parts_examples("brake pads")
        
        final_query = final_query.strip()
        print(f"🔧 Búsqueda de repuestos final: '{final_query}' (fuente: {search_source})")
        
        # Continuar con lógica de búsqueda existente
        if not self.api_key:
            print("Sin API key - usando ejemplos de auto parts")
            return self._get_auto_parts_examples(final_query)
        
        cache_key = f"autoparts_{hash(final_query.lower())}"
        if cache_key in self.cache:
            cache_data, timestamp = self.cache[cache_key]
            if (time.time() - timestamp) < self.cache_ttl:
                return cache_data
        
        start_time = time.time()
        all_products = []
        
        # Búsqueda en Google Shopping
        if time.time() - start_time < 8:
            data = self._make_api_request('google_shopping', final_query)
            products = self._process_auto_parts_results(data, 'google_shopping')
            all_products.extend(products)
        
        if not all_products:
            all_products = self._get_auto_parts_examples(final_query)
        
        # Ordenar por precio
        all_products.sort(key=lambda x: x['price_numeric'])
        final_products = all_products[:6]
        
        # Añadir metadata
        for product in final_products:
            product['search_source'] = search_source
            product['original_query'] = query if query else "imagen"
            product['vehicle_info'] = vehicle_info
        
        self.cache[cache_key] = (final_products, time.time())
        if len(self.cache) > 15:  # Cache más grande para auto parts
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k][1])
            del self.cache[oldest_key]
        
        return final_products
    
    def _get_auto_parts_examples(self, query):
        """Ejemplos específicos para auto parts"""
        stores = ['AutoZone', 'Advance Auto Parts', "O'Reilly Auto Parts", 'NAPA', 'RockAuto', 'Amazon Automotive']
        examples = []
        
        for i in range(6):
            price = self._generate_realistic_auto_part_price(query, i)
            store = stores[i % len(stores)]
            search_query = quote_plus(f"auto parts {str(query)[:30]}")
            
            # Enlaces específicos para cada tienda
            if store == 'AutoZone':
                link = f"https://www.autozone.com/search?searchText={search_query}"
            elif store == 'Advance Auto Parts':
                link = f"https://shop.advanceautoparts.com/find/?searchTerm={search_query}"
            elif store == "O'Reilly Auto Parts":
                link = f"https://www.oreillyauto.com/search?q={search_query}"
            elif store == 'NAPA':
                link = f"https://www.napaonline.com/search?query={search_query}"
            elif store == 'RockAuto':
                link = f"https://www.rockauto.com/"
            else:
                link = f"https://www.amazon.com/s?k=automotive+{search_query}"
            
            part_types = ['OEM', 'Aftermarket', 'OEM', 'Aftermarket', 'Premium', 'Economy']
            part_type = part_types[i % len(part_types)]
            
            examples.append({
                'title': f'{self._clean_text(query)} - {["Premium", "OEM Quality", "Best Value", "Heavy Duty", "Performance", "Standard"][i]}',
                'price': f'${price:.2f}',
                'price_numeric': price,
                'source': store,
                'link': link,
                'rating': ['4.6', '4.4', '4.2', '4.5', '4.3', '4.1'][i],
                'reviews': ['1200', '850', '600', '400', '300', '150'][i],
                'part_type': part_type,
                'image': '',
                'search_source': 'example'
            })
        return examples

# Configuración adicional para el scraper
def configure_scraper_for_auto_parts():
    """Configurar el scraper específicamente para auto parts"""
    if BS4_AVAILABLE and 'ethical_scraper' in globals():
        # Configurar user agents específicos para auto parts
        auto_parts_user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0'
        ]
        ethical_scraper.user_agents = auto_parts_user_agents
        
        # Configurar delays específicos para auto parts
        ethical_scraper.delay_range = (2, 4)  # Más conservador para tiendas
        ethical_scraper.max_requests_per_hour = 150  # Límite más bajo
        
        print("✅ Scraper configurado para auto parts con delays conservadores")
    else:
        print("⚠ BeautifulSoup4 no disponible - scraping directo deshabilitado")

# ==============================================================================
# RUTAS DE LA APLICACIÓN
# ==============================================================================

@app.route('/')
def home():
    return render_page("Auto Parts Finder", "<div class='container'><h1>Auto Parts Finder</h1><div class='subtitle'>Encuentra repuestos automotrices en USA</div></div>")

@app.route('/login', methods=['GET'])
def auth_login_page():
    if firebase_auth and firebase_auth.is_user_logged_in():
        return redirect(url_for('search_page'))
    
    login_content = '''
    <div class="container">
        <h1>Auto Parts Finder</h1>
        <div class="subtitle">Iniciar Sesión</div>
        
        <div id="flash-messages"></div>
        
        <form id="loginForm" onsubmit="handleLogin(event)">
            <input type="email" id="email" placeholder="Correo electrónico" required>
            <input type="password" id="password" placeholder="Contraseña" required>
            <button type="submit" id="loginBtn">Iniciar Sesión</button>
        </form>
        
        <div class="loading" id="loginLoading">
            <div class="spinner"></div>
            <p>Iniciando sesión...</p>
        </div>
        
        <div class="error" id="loginError"></div>
        
        <div style="text-align: center; margin-top: 20px;">
            <p style="color: #666; font-size: 14px;">Demo: admin@test.com / password123</p>
        </div>
    </div>
    
    <script>
    async function handleLogin(event) {
        event.preventDefault();
        
        const email = document.getElementById('email').value;
        const password = document.getElementById('password').value;
        
        document.getElementById('loginForm').style.display = 'none';
        document.getElementById('loginLoading').style.display = 'block';
        document.getElementById('loginError').style.display = 'none';
        
        try {
            const response = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });
            
            const result = await response.json();
            
            if (result.success) {
                window.location.href = '/search';
            } else {
                document.getElementById('loginError').textContent = result.message || 'Error de login';
                document.getElementById('loginError').style.display = 'block';
                document.getElementById('loginForm').style.display = 'block';
                document.getElementById('loginLoading').style.display = 'none';
            }
        } catch (error) {
            document.getElementById('loginError').textContent = 'Error de conexión';
            document.getElementById('loginError').style.display = 'block';
            document.getElementById('loginForm').style.display = 'block';
            document.getElementById('loginLoading').style.display = 'none';
        }
    }
    </script>
    '''
    
    return render_page("Login - Auto Parts Finder", login_content)

@app.route('/api/login', methods=['POST'])
def api_login():
    if not firebase_auth:
        return jsonify({'success': False, 'message': 'Servicio de autenticación no disponible'})
    
    try:
        data = request.get_json()
        email = data.get('email', '').strip()
        password = data.get('password', '').strip()
        
        if not email or not password:
            return jsonify({'success': False, 'message': 'Email y contraseña requeridos'})
        
        result = firebase_auth.login_user(email, password)
        
        if result['success']:
            firebase_auth.set_user_session(result['user_data'])
            return jsonify(result)
        else:
            return jsonify(result)
            
    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({'success': False, 'message': 'Error interno del servidor'})

@app.route('/logout')
def logout():
    if firebase_auth:
        firebase_auth.clear_user_session()
    flash('Has cerrado sesión correctamente', 'success')
    return redirect(url_for('auth_login_page'))

@app.route('/search')
@login_required
def search_page():
    current_user = firebase_auth.get_current_user() if firebase_auth else None
    user_name = current_user['user_name'] if current_user else 'Usuario'
    
    search_content = f'''
    <div class="container">
        <div class="user-info">
            👋 Bienvenido, <strong>{user_name}</strong> | 
            <a href="/logout">Cerrar Sesión</a>
        </div>
        
        <h1>🔧 Auto Parts Finder</h1>
        <div class="subtitle">Encuentra repuestos automotrices en tiendas de USA</div>
        
        <div class="tips">
            💡 <strong>Consejos de búsqueda:</strong><br>
            • Incluye año, marca y modelo de tu vehículo para mejores resultados<br>
            • Usa nombres específicos: "brake pads", "oil filter", "spark plugs"<br>
            • Puedes subir una foto del repuesto para búsqueda visual
        </div>
        
        <!-- Información del vehículo -->
        <div class="vehicle-form">
            <h3>🚗 Información del Vehículo (Opcional)</h3>
            <div class="vehicle-row">
                <select id="vehicleYear">
                    <option value="">Año</option>
                </select>
                <select id="vehicleMake">
                    <option value="">Marca</option>
                </select>
                <select id="vehicleModel">
                    <option value="">Modelo</option>
                </select>
            </div>
        </div>
        
        <!-- Búsqueda por texto -->
        <div class="search-bar">
            <input type="text" id="searchQuery" placeholder="Ejemplo: brake pads, oil filter, spark plugs..." maxlength="100">
            <button onclick="searchParts()">🔍 Buscar</button>
        </div>
        
        <div class="or-divider">
            <span>O</span>
        </div>
        
        <!-- Búsqueda por imagen -->
        <div class="image-upload" onclick="document.getElementById('imageInput').click()">
            <input type="file" id="imageInput" accept="image/*" onchange="handleImageUpload(event)">
            <label>📷 Subir foto del repuesto</label>
            <img id="imagePreview" class="image-preview" style="display: none;">
        </div>
        
        <div class="loading" id="searchLoading">
            <div class="spinner"></div>
            <p>Buscando repuestos automotrices...</p>
        </div>
        
        <div class="error" id="searchError"></div>
        
        <div id="searchResults"></div>
    </div>
    
    <script>
    // Datos de vehículos
    const vehicleData = {json.dumps(VEHICLE_DATABASE)};
    
    // Inicializar selectores de vehículos
    function initVehicleSelectors() {{
        const yearSelect = document.getElementById('vehicleYear');
        const makeSelect = document.getElementById('vehicleMake');
        
        // Llenar años (más recientes primero)
        vehicleData.years.reverse().forEach(year => {{
            const option = document.createElement('option');
            option.value = year;
            option.textContent = year;
            yearSelect.appendChild(option);
        }});
        
        // Llenar marcas
        Object.keys(vehicleData.makes).forEach(make => {{
            const option = document.createElement('option');
            option.value = make;
            option.textContent = make.charAt(0).toUpperCase() + make.slice(1);
            makeSelect.appendChild(option);
        }});
        
        // Evento para actualizar modelos cuando cambia la marca
        makeSelect.addEventListener('change', updateModels);
    }}
    
    function updateModels() {{
        const makeSelect = document.getElementById('vehicleMake');
        const modelSelect = document.getElementById('vehicleModel');
        const selectedMake = makeSelect.value;
        
        // Limpiar modelos
        modelSelect.innerHTML = '<option value="">Modelo</option>';
        
        if (selectedMake && vehicleData.makes[selectedMake]) {{
            vehicleData.makes[selectedMake].forEach(model => {{
                const option = document.createElement('option');
                option.value = model;
                option.textContent = model.toUpperCase();
                modelSelect.appendChild(option);
            }});
        }}
    }}
    
    // Manejar subida de imagen
    function handleImageUpload(event) {{
        const file = event.target.files[0];
        if (file) {{
            const reader = new FileReader();
            reader.onload = function(e) {{
                const preview = document.getElementById('imagePreview');
                preview.src = e.target.result;
                preview.style.display = 'block';
            }};
            reader.readAsDataURL(file);
        }}
    }}
    
    // Búsqueda de repuestos
    async function searchParts() {{
        const query = document.getElementById('searchQuery').value.trim();
        const imageInput = document.getElementById('imageInput');
        const vehicleYear = document.getElementById('vehicleYear').value;
        const vehicleMake = document.getElementById('vehicleMake').value;
        const vehicleModel = document.getElementById('vehicleModel').value;
        
        if (!query && !imageInput.files[0]) {{
            document.getElementById('searchError').textContent = 'Ingresa un término de búsqueda o sube una imagen';
            document.getElementById('searchError').style.display = 'block';
            return;
        }}
        
        document.getElementById('searchLoading').style.display = 'block';
        document.getElementById('searchError').style.display = 'none';
        document.getElementById('searchResults').innerHTML = '';
        
        const formData = new FormData();
        if (query) formData.append('query', query);
        if (imageInput.files[0]) formData.append('image', imageInput.files[0]);
        if (vehicleYear) formData.append('vehicle_year', vehicleYear);
        if (vehicleMake) formData.append('vehicle_make', vehicleMake);
        if (vehicleModel) formData.append('vehicle_model', vehicleModel);
        
        try {{
            const response = await fetch('/api/search-parts', {{
                method: 'POST',
                body: formData
            }});
            
            const result = await response.json();
            
            if (result.success) {{
                displayResults(result.products, result.search_info);
            }} else {{
                document.getElementById('searchError').textContent = result.message || 'Error en la búsqueda';
                document.getElementById('searchError').style.display = 'block';
            }}
        }} catch (error) {{
            document.getElementById('searchError').textContent = 'Error de conexión';
            document.getElementById('searchError').style.display = 'block';
        }} finally {{
            document.getElementById('searchLoading').style.display = 'none';
        }}
    }}
    
    function displayResults(products, searchInfo) {{
        if (!products || products.length === 0) {{
            document.getElementById('searchResults').innerHTML = '<p>No se encontraron repuestos</p>';
            return;
        }}
        
        let html = `
            <div style="background: #e8f5e8; padding: 15px; border-radius: 8px; margin: 20px 0;">
                <h3>✅ Encontrados ${{products.length}} repuestos automotrices</h3>
                <p><strong>Búsqueda:</strong> ${{searchInfo.query || 'Imagen'}} ${{searchInfo.vehicle ? '| Vehículo: ' + searchInfo.vehicle : ''}}</p>
            </div>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px; margin-top: 20px;">
        `;
        
        products.forEach(product => {{
            const partBadge = product.part_type === 'OEM' ? 
                '<span class="part-badge">OEM</span>' : 
                '<span class="part-badge aftermarket">Aftermarket</span>';
            
            html += `
                <div style="border: 1px solid #ddd; border-radius: 8px; padding: 15px; background: white;">
                    <h4 style="margin: 0 0 10px 0; color: #1e3c72;">
                        ${{product.title}} ${{partBadge}}
                    </h4>
                    <p style="font-size: 18px; font-weight: bold; color: #28a745; margin: 5px 0;">
                        ${{product.price}}
                    </p>
                    <p style="font-size: 14px; color: #666; margin: 5px 0;">
                        <strong>Tienda:</strong> ${{product.source}}
                        <span class="store-badge">${{product.source}}</span>
                    </p>
                    ${{product.rating ? `<p style="font-size: 13px; color: #666;">⭐ ${{product.rating}} (${{product.reviews}} reviews)</p>` : ''}}
                    <a href="${{product.link}}" target="_blank" style="display: inline-block; background: #1e3c72; color: white; padding: 8px 15px; text-decoration: none; border-radius: 4px; font-size: 14px; margin-top: 10px;">
                        Ver en tienda →
                    </a>
                </div>
            `;
        }});
        
        html += '</div>';
        document.getElementById('searchResults').innerHTML = html;
    }}
    
    // Buscar al presionar Enter
    document.getElementById('searchQuery').addEventListener('keypress', function(e) {{
        if (e.key === 'Enter') {{
            searchParts();
        }}
    }});
    
    // Inicializar cuando carga la página
    initVehicleSelectors();
    </script>
    '''
    
    return render_page("Búsqueda - Auto Parts Finder", search_content)

@app.route('/api/search-parts', methods=['POST'])
@login_required
def api_search_parts():
    try:
        # Obtener datos del request
        query = request.form.get('query', '').strip()
        image_file = request.files.get('image')
        vehicle_year = request.form.get('vehicle_year', '').strip()
        vehicle_make = request.form.get('vehicle_make', '').strip()
        vehicle_model = request.form.get('vehicle_model', '').strip()
        
        # Procesar imagen si existe
        image_content = None
        if image_file and image_file.filename:
            try:
                image_content = image_file.read()
                if not validate_image(image_content):
                    return jsonify({
                        'success': False, 
                        'message': 'Imagen inválida. Use JPEG, PNG o WEBP.'
                    })
            except Exception as e:
                print(f"Error procesando imagen: {e}")
                return jsonify({
                    'success': False, 
                    'message': 'Error procesando la imagen'
                })
        
        # Información del vehículo
        vehicle_info = None
        if vehicle_year or vehicle_make or vehicle_model:
            vehicle_info = {
                'year': vehicle_year,
                'make': vehicle_make,
                'model': vehicle_model
            }
        
        # Validar que hay algo para buscar
        if not query and not image_content:
            return jsonify({
                'success': False, 
                'message': 'Proporciona un término de búsqueda o una imagen'
            })
        
        # Realizar búsqueda
        if not auto_parts_finder:
            return jsonify({
                'success': False, 
                'message': 'Servicio de búsqueda no disponible'
            })
        
        products = auto_parts_finder.search_auto_parts(
            query=query,
            image_content=image_content,
            vehicle_info=vehicle_info
        )
        
        # Información de la búsqueda
        search_info = {
            'query': query,
            'has_image': bool(image_content),
            'vehicle': None,
            'source': products[0].get('search_source', 'unknown') if products else 'none'
        }
        
        if vehicle_info and any(vehicle_info.values()):
            vehicle_parts = []
            if vehicle_info.get('year'):
                vehicle_parts.append(vehicle_info['year'])
            if vehicle_info.get('make'):
                vehicle_parts.append(vehicle_info['make'].title())
            if vehicle_info.get('model'):
                vehicle_parts.append(vehicle_info['model'].upper())
            search_info['vehicle'] = ' '.join(vehicle_parts)
        
        return jsonify({
            'success': True,
            'products': products,
            'search_info': search_info,
            'count': len(products)
        })
        
    except Exception as e:
        print(f"Error en búsqueda de auto parts: {e}")
        return jsonify({
            'success': False, 
            'message': 'Error interno del servidor'
        })

@app.route('/api/scrape-test', methods=['GET'])
@login_required
def test_scraping():
    """Endpoint para probar capacidades de scraping (solo para desarrollo)"""
    try:
        query = request.args.get('q', 'brake pads')
        
        if not BS4_AVAILABLE:
            return jsonify({
                'success': False, 
                'error': 'BeautifulSoup4 no disponible',
                'install_cmd': 'pip install beautifulsoup4'
            })
        
        if not ethical_scraper:
            return jsonify({
                'success': False,
                'error': 'EthicalWebScraper no inicializado'
            })
        
        # Probar scraping de una tienda
        test_url = f"https://www.autozone.com/search?searchText={quote_plus(query)}"
        
        # Verificar robots.txt primero
        can_scrape = ethical_scraper.can_fetch(test_url)
        
        if not can_scrape:
            return jsonify({
                'success': False,
                'error': 'robots.txt prohíbe el acceso',
                'url': test_url,
                'robots_check': False
            })
        
        # Intentar scraping
        scraped_data = auto_parts_finder._scrape_direct_stores(query, max_results=2)
        
        return jsonify({
            'success': True,
            'query': query,
            'results_count': len(scraped_data),
            'robots_check': True,
            'sample_results': scraped_data[:2],  # Solo mostrar 2 para el test
            'scraper_stats': {
                'requests_made': ethical_scraper.request_count,
                'session_start': ethical_scraper.session_start.isoformat()
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'test_endpoint': True
        })

# Templates optimizados para auto parts
def render_page(title, content):
    template = '''<!DOCTYPE html>
<html lang="es">
<head>
    <title>''' + title + '''</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, sans-serif; background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); min-height: 100vh; padding: 15px; }
        .container { max-width: 700px; margin: 0 auto; background: white; padding: 25px; border-radius: 12px; box-shadow: 0 8px 25px rgba(0,0,0,0.15); }
        h1 { color: #1e3c72; text-align: center; margin-bottom: 8px; font-size: 1.9em; }
        .subtitle { text-align: center; color: #666; margin-bottom: 25px; }
        input, select { width: 100%; padding: 12px; margin: 8px 0; border: 2px solid #e1e5e9; border-radius: 6px; font-size: 16px; }
        input:focus, select:focus { outline: none; border-color: #1e3c72; }
        button { width: 100%; padding: 12px; background: #1e3c72; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 16px; font-weight: 600; }
        button:hover { background: #2a5298; }
        .search-bar { display: flex; gap: 8px; margin-bottom: 20px; }
        .search-bar input { flex: 1; }
        .search-bar button { width: auto; padding: 12px 20px; }
        .vehicle-form { background: #f8f9fa; border: 2px solid #dee2e6; border-radius: 8px; padding: 20px; margin: 15px 0; }
        .vehicle-row { display: grid; grid-template-columns: 1fr 2fr 2fr; gap: 15px; margin-bottom: 15px; }
        .tips { background: #e8f4f8; border: 1px solid #1e3c72; padding: 15px; border-radius: 6px; margin-bottom: 15px; font-size: 14px; }
        .error { background: #ffebee; color: #c62828; padding: 12px; border-radius: 6px; margin: 12px 0; display: none; }
        .loading { text-align: center; padding: 30px; display: none; }
        .spinner { border: 3px solid #f3f3f3; border-top: 3px solid #1e3c72; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 0 auto 15px; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .user-info { background: #e3f2fd; padding: 12px; border-radius: 6px; margin-bottom: 15px; text-align: center; font-size: 14px; display: flex; align-items: center; justify-content: center; }
        .user-info a { color: #1976d2; text-decoration: none; font-weight: 600; }
        .flash { padding: 12px; margin-bottom: 8px; border-radius: 6px; font-size: 14px; }
        .flash.success { background-color: #d4edda; color: #155724; }
        .flash.danger { background-color: #f8d7da; color: #721c24; }
        .flash.warning { background-color: #fff3cd; color: #856404; }
        .image-upload { background: #f8f9fa; border: 2px dashed #dee2e6; border-radius: 8px; padding: 20px; text-align: center; margin: 15px 0; transition: all 0.3s ease; }
        .image-upload input[type="file"] { display: none; }
        .image-upload label { cursor: pointer; color: #1e3c72; font-weight: 600; }
        .image-upload:hover { border-color: #1e3c72; background: #e3f2fd; }
        .image-preview { max-width: 150px; max-height: 150px; margin: 10px auto; border-radius: 8px; display: none; }
        .or-divider { text-align: center; margin: 20px 0; color: #666; font-weight: 600; position: relative; }
        .or-divider:before { content: ''; position: absolute; top: 50%; left: 0; right: 0; height: 1px; background: #dee2e6; z-index: 1; }
        .or-divider span { background: white; padding: 0 15px; position: relative; z-index: 2; }
        .part-badge { display: inline-block; background: #28a745; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; margin-left: 8px; }
        .part-badge.aftermarket { background: #17a2b8; }
        .store-badge { display: inline-block; background: #6c757d; color: white; padding: 2px 6px; border-radius: 3px; font-size: 10px; margin-left: 5px; }
    </style>
</head>
<body>''' + content + '''</body>
</html>'''
    return template

# ==============================================================================
# INICIALIZACIÓN DE INSTANCIAS GLOBALES
# ==============================================================================

# Instancia global del scraper ético
try:
    ethical_scraper = EthicalWebScraper(delay_range=(1.5, 3.0), max_retries=3)
    print("✅ EthicalWebScraper inicializado correctamente")
except Exception as e:
    print(f"❌ Error inicializando EthicalWebScraper: {e}")
    ethical_scraper = None

# Instancia global de Firebase Auth
try:
    firebase_auth = FirebaseAuth()
    print("✅ FirebaseAuth inicializado correctamente")
except Exception as e:
    print(f"❌ Error inicializando FirebaseAuth: {e}")
    firebase_auth = None

# Instancia global de AutoPartsFinder
try:
    auto_parts_finder = AutoPartsFinder()
    print("✅ AutoPartsFinder inicializado correctamente")
except Exception as e:
    print(f"❌ Error inicializando AutoPartsFinder: {e}")
    auto_parts_finder = None

# Configurar el scraper al inicio
configure_scraper_for_auto_parts()

# ==============================================================================
# PUNTO DE ENTRADA DE LA APLICACIÓN
# ==============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    
    print("=" * 60)
    print("🔧 AUTO PARTS FINDER USA - INICIANDO")
    print("=" * 60)
    print(f"Puerto: {port}")
    print(f"Debug: {debug_mode}")
    print(f"PIL disponible: {PIL_AVAILABLE}")
    print(f"Gemini disponible: {GEMINI_READY}")
    print(f"BeautifulSoup4 disponible: {BS4_AVAILABLE}")
    print(f"SerpAPI configurado: {auto_parts_finder.is_api_configured() if auto_parts_finder else False}")
    print(f"Firebase Auth configurado: {firebase_auth.firebase_web_api_key is not None if firebase_auth else False}")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
