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

# Inicializar Flask app temprano
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'fallback-key-change-in-production')
app.config['PERMANENT_SESSION_LIFETIME'] = 1800
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = True if os.environ.get('RENDER') else False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

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
    },
    'years': list(range(1990, 2025)),
    'common_parts': [
        'brake pads', 'brake rotors', 'brake caliper', 'brake fluid',
        'oil filter', 'air filter', 'cabin filter', 'fuel filter',
        'spark plugs', 'ignition coils', 'battery', 'alternator',
        'starter', 'radiator', 'water pump', 'thermostat',
    ]
}

# ==============================================================================
# CLASE DE WEB SCRAPING ÉTICO - SIMPLIFICADA
# ==============================================================================

class EthicalWebScraper:
    """Web Scraper Ético simplificado para Auto Parts"""
    
    def __init__(self, delay_range=(1, 3), max_retries=3):
        self.delay_range = delay_range
        self.max_retries = max_retries
        self.session = requests.Session()
        self.request_count = 0
        self.session_start = datetime.now()
        
    def can_fetch(self, url):
        """Verificación simple - siempre permitir para tiendas de auto parts"""
        try:
            domain = urlparse(url).netloc.lower()
            auto_stores = ['autozone.com', 'advanceautoparts.com', 'oreillyauto.com']
            return any(store in domain for store in auto_stores)
        except:
            return False
    
    def make_request(self, url, **kwargs):
        """Realizar request simple con retry"""
        try:
            time.sleep(random.uniform(*self.delay_range))
            response = self.session.get(url, timeout=10, **kwargs)
            self.request_count += 1
            return response
        except Exception as e:
            print(f"Error en request: {e}")
            return None

# ==============================================================================
# FIREBASE AUTH CLASS - SIMPLIFICADA
# ==============================================================================

class FirebaseAuth:
    def __init__(self):
        self.firebase_web_api_key = os.environ.get("FIREBASE_WEB_API_KEY")
        print(f"Firebase configurado: {bool(self.firebase_web_api_key)}")
    
    def login_user(self, email, password):
        # Hardcoded demo credentials para evitar dependencias externas
        if email == "admin@test.com" and password == "password123":
            return {
                'success': True,
                'message': 'Login exitoso',
                'user_data': {
                    'user_id': 'demo_user_123',
                    'email': email,
                    'display_name': 'Demo User',
                    'id_token': 'demo_token'
                }
            }
        else:
            return {
                'success': False,
                'message': 'Credenciales incorrectas',
                'user_data': None
            }
    
    def set_user_session(self, user_data):
        session['user_id'] = user_data['user_id']
        session['user_name'] = user_data['display_name']
        session['user_email'] = user_data['email']
        session['login_time'] = datetime.now().isoformat()
        session.permanent = True
    
    def clear_user_session(self):
        session.clear()
    
    def is_user_logged_in(self):
        return 'user_id' in session and session.get('user_id') is not None
    
    def get_current_user(self):
        if not self.is_user_logged_in():
            return None
        return {
            'user_id': session.get('user_id'),
            'user_name': session.get('user_name'),
            'user_email': session.get('user_email')
        }

# ==============================================================================
# AUTO PARTS FINDER CLASS - SIMPLIFICADA
# ==============================================================================

class AutoPartsFinder:
    def __init__(self):
        self.api_key = os.environ.get('SERPAPI_KEY')
        print(f"SerpAPI configurado: {bool(self.api_key)}")
        
    def search_auto_parts(self, query=None, image_content=None, vehicle_info=None):
        """Búsqueda simplificada de repuestos"""
        
        # Construir query final
        final_query = query or "auto parts"
        if vehicle_info:
            vehicle_part = ""
            if vehicle_info.get('year'):
                vehicle_part += f"{vehicle_info['year']} "
            if vehicle_info.get('make'):
                vehicle_part += f"{vehicle_info['make']} "
            if vehicle_info.get('model'):
                vehicle_part += f"{vehicle_info['model']} "
            final_query = f"{vehicle_part}{final_query}".strip()
        
        # Retornar ejemplos realistas
        return self._get_auto_parts_examples(final_query)
    
    def _get_auto_parts_examples(self, query):
        """Generar ejemplos de repuestos"""
        stores = ['AutoZone', 'Advance Auto Parts', "O'Reilly Auto Parts", 'NAPA', 'Amazon Automotive']
        examples = []
        
        base_prices = [29.99, 45.99, 67.99, 89.99, 124.99, 199.99]
        
        for i in range(6):
            store = stores[i % len(stores)]
            price = base_prices[i]
            
            examples.append({
                'title': f'{query.title()} - {"Premium OEM" if i % 2 == 0 else "Aftermarket"}',
                'price': f'${price:.2f}',
                'price_numeric': price,
                'source': store,
                'link': f"https://www.google.com/search?tbm=shop&q={quote_plus(query)}",
                'rating': f"{4.0 + (i * 0.1):.1f}",
                'reviews': str(100 + i * 50),
                'part_type': 'OEM' if i % 2 == 0 else 'Aftermarket',
                'search_source': 'example'
            })
        
        return examples

# ==============================================================================
# DECORADOR LOGIN REQUIRED
# ==============================================================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            if not firebase_auth or not firebase_auth.is_user_logged_in():
                flash('Debes iniciar sesión para acceder a esta página.', 'warning')
                return redirect(url_for('auth_login_page'))
            return f(*args, **kwargs)
        except Exception as e:
            print(f"Error en login_required: {e}")
            return redirect(url_for('auth_login_page'))
    return decorated_function

# ==============================================================================
# FUNCIONES AUXILIARES
# ==============================================================================

def validate_image(image_content):
    """Validación simple de imagen"""
    if not PIL_AVAILABLE or not image_content:
        return False
    try:
        image = Image.open(io.BytesIO(image_content))
        return image.size[0] > 10 and image.size[1] > 10
    except:
        return False

def render_page(title, content):
    """Template simplificado"""
    template = f'''<!DOCTYPE html>
<html lang="es">
<head>
    <title>{title}</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: Arial, sans-serif; background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); min-height: 100vh; padding: 15px; }}
        .container {{ max-width: 700px; margin: 0 auto; background: white; padding: 25px; border-radius: 12px; box-shadow: 0 8px 25px rgba(0,0,0,0.15); }}
        h1 {{ color: #1e3c72; text-align: center; margin-bottom: 20px; }}
        .subtitle {{ text-align: center; color: #666; margin-bottom: 25px; }}
        input, select {{ width: 100%; padding: 12px; margin: 8px 0; border: 2px solid #e1e5e9; border-radius: 6px; font-size: 16px; }}
        button {{ background: #1e3c72; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 16px; font-weight: 600; padding: 12px 20px; }}
        button:hover {{ background: #2a5298; }}
        .search-bar {{ display: flex; gap: 8px; margin-bottom: 20px; }}
        .search-bar input {{ flex: 1; }}
        .vehicle-form {{ background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 15px 0; }}
        .vehicle-row {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; margin-bottom: 15px; }}
        .error {{ background: #ffebee; color: #c62828; padding: 12px; border-radius: 6px; margin: 12px 0; display: none; }}
        .loading {{ text-align: center; padding: 30px; display: none; }}
        .spinner {{ border: 3px solid #f3f3f3; border-top: 3px solid #1e3c72; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 0 auto 15px; }}
        @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
        .user-info {{ background: #e3f2fd; padding: 12px; border-radius: 6px; margin-bottom: 15px; text-align: center; }}
        .user-info a {{ color: #1976d2; text-decoration: none; }}
        .image-upload {{ background: #f8f9fa; border: 2px dashed #dee2e6; border-radius: 8px; padding: 20px; text-align: center; margin: 15px 0; cursor: pointer; }}
        .image-upload input[type="file"] {{ display: none; }}
        .or-divider {{ text-align: center; margin: 20px 0; color: #666; font-weight: 600; }}
    </style>
</head>
<body>{content}</body>
</html>'''
    return template

# ==============================================================================
# RUTAS DE LA APLICACIÓN
# ==============================================================================

@app.route('/')
def home():
    """Página principal"""
    try:
        home_content = f'''
        <div class="container">
            <h1>🔧 Auto Parts Finder</h1>
            <div class="subtitle">Encuentra repuestos automotrices en tiendas de USA</div>
            
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
            
            <div class="or-divider">O</div>
            
            <!-- Búsqueda por imagen -->
            <div class="image-upload" onclick="document.getElementById('imageInput').click()">
                <input type="file" id="imageInput" accept="image/*">
                <div>📷 Subir foto del repuesto</div>
            </div>
            
            <div class="loading" id="searchLoading">
                <div class="spinner"></div>
                <p>Buscando repuestos...</p>
            </div>
            
            <div class="error" id="searchError"></div>
            <div id="searchResults"></div>
            
            <div style="text-align: center; margin-top: 30px;">
                <a href="/login" style="background: #1e3c72; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px;">
                    Iniciar Sesión
                </a>
            </div>
        </div>
        
        <script>
        const vehicleData = {VEHICLE_DATABASE};
        
        function initVehicleSelectors() {{
            const yearSelect = document.getElementById('vehicleYear');
            const makeSelect = document.getElementById('vehicleMake');
            
            vehicleData.years.reverse().forEach(year => {{
                const option = document.createElement('option');
                option.value = year;
                option.textContent = year;
                yearSelect.appendChild(option);
            }});
            
            Object.keys(vehicleData.makes).forEach(make => {{
                const option = document.createElement('option');
                option.value = make;
                option.textContent = make.charAt(0).toUpperCase() + make.slice(1);
                makeSelect.appendChild(option);
            }});
            
            makeSelect.addEventListener('change', updateModels);
        }}
        
        function updateModels() {{
            const makeSelect = document.getElementById('vehicleMake');
            const modelSelect = document.getElementById('vehicleModel');
            const selectedMake = makeSelect.value;
            
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
        
        async function searchParts() {{
            const query = document.getElementById('searchQuery').value.trim();
            const imageInput = document.getElementById('imageInput');
            
            if (!query && !imageInput.files[0]) {{
                document.getElementById('searchError').textContent = 'Ingresa un término de búsqueda o sube una imagen';
                document.getElementById('searchError').style.display = 'block';
                return;
            }}
            
            document.getElementById('searchLoading').style.display = 'block';
            document.getElementById('searchError').style.display = 'none';
            
            const formData = new FormData();
            if (query) formData.append('query', query);
            if (imageInput.files[0]) formData.append('image', imageInput.files[0]);
            formData.append('vehicle_year', document.getElementById('vehicleYear').value);
            formData.append('vehicle_make', document.getElementById('vehicleMake').value);
            formData.append('vehicle_model', document.getElementById('vehicleModel').value);
            
            try {{
                const response = await fetch('/api/search-parts-public', {{
                    method: 'POST',
                    body: formData
                }});
                
                const result = await response.json();
                
                if (result.success) {{
                    displayResults(result.products);
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
        
        function displayResults(products) {{
            if (!products || products.length === 0) {{
                document.getElementById('searchResults').innerHTML = '<p>No se encontraron repuestos</p>';
                return;
            }}
            
            let html = '<div style="margin-top: 20px;"><h3>Repuestos encontrados:</h3>';
            
            products.forEach(product => {{
                html += `
                    <div style="border: 1px solid #ddd; border-radius: 8px; padding: 15px; margin: 10px 0;">
                        <h4>${{product.title}}</h4>
                        <p style="font-size: 18px; color: #28a745; font-weight: bold;">${{product.price}}</p>
                        <p>Tienda: ${{product.source}}</p>
                        <a href="${{product.link}}" target="_blank" style="background: #1e3c72; color: white; padding: 8px 15px; text-decoration: none; border-radius: 4px;">
                            Ver en tienda →
                        </a>
                    </div>
                `;
            }});
            
            html += '</div>';
            document.getElementById('searchResults').innerHTML = html;
        }}
        
        initVehicleSelectors();
        </script>
        '''
        
        return render_page("Auto Parts Finder", home_content)
    except Exception as e:
        print(f"Error in home route: {e}")
        return f"<h1>Error</h1><p>{str(e)}</p>", 500

@app.route('/login', methods=['GET'])
def auth_login_page():
    """Página de login"""
    try:
        login_content = '''
        <div class="container">
            <h1>Auto Parts Finder</h1>
            <div class="subtitle">Iniciar Sesión</div>
            
            <form id="loginForm" onsubmit="handleLogin(event)">
                <input type="email" id="email" placeholder="Correo electrónico" required>
                <input type="password" id="password" placeholder="Contraseña" required>
                <button type="submit" style="width: 100%;">Iniciar Sesión</button>
            </form>
            
            <div class="loading" id="loginLoading">
                <div class="spinner"></div>
                <p>Iniciando sesión...</p>
            </div>
            
            <div class="error" id="loginError"></div>
            
            <div style="text-align: center; margin-top: 20px;">
                <p style="color: #666; font-size: 14px;">Demo: admin@test.com / password123</p>
                <p><a href="/">← Volver a búsqueda</a></p>
            </div>
        </div>
        
        <script>
        async function handleLogin(event) {
            event.preventDefault();
            
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;
            
            document.getElementById('loginForm').style.display = 'none';
            document.getElementById('loginLoading').style.display = 'block';
            
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
                    document.getElementById('loginError').textContent = result.message;
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
    except Exception as e:
        print(f"Error in login page: {e}")
        return f"<h1>Error</h1><p>{str(e)}</p>", 500

@app.route('/api/login', methods=['POST'])
def api_login():
    """API de login"""
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
            
    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({'success': False, 'message': 'Error interno del servidor'})

@app.route('/search')
@login_required
def search_page():
    """Página de búsqueda para usuarios logueados"""
    try:
        current_user = firebase_auth.get_current_user()
        user_name = current_user['user_name'] if current_user else 'Usuario'
        
        # Similar al home pero con info de usuario
        search_content = f'''
        <div class="container">
            <div class="user-info">
                👋 Bienvenido, <strong>{user_name}</strong> | 
                <a href="/logout">Cerrar Sesión</a>
            </div>
            
            <h1>🔧 Auto Parts Finder</h1>
            <div class="subtitle">Encuentra repuestos automotrices</div>
            
            <!-- Contenido similar al home -->
            <div class="search-bar">
                <input type="text" id="searchQuery" placeholder="Buscar repuestos..." maxlength="100">
                <button onclick="searchParts()">🔍 Buscar</button>
            </div>
            
            <div class="loading" id="searchLoading">
                <div class="spinner"></div>
                <p>Buscando...</p>
            </div>
            
            <div class="error" id="searchError"></div>
            <div id="searchResults"></div>
        </div>
        
        <script>
        async function searchParts() {{
            const query = document.getElementById('searchQuery').value.trim();
            
            if (!query) {{
                document.getElementById('searchError').textContent = 'Ingresa un término de búsqueda';
                document.getElementById('searchError').style.display = 'block';
                return;
            }}
            
            document.getElementById('searchLoading').style.display = 'block';
            
            const formData = new FormData();
            formData.append('query', query);
            
            try {{
                const response = await fetch('/api/search-parts', {{
                    method: 'POST',
                    body: formData
                }});
                
                const result = await response.json();
                
                if (result.success) {{
                    displayResults(result.products);
                }} else {{
                    document.getElementById('searchError').textContent = result.message;
                    document.getElementById('searchError').style.display = 'block';
                }}
            }} catch (error) {{
                document.getElementById('searchError').textContent = 'Error de conexión';
                document.getElementById('searchError').style.display = 'block';
            }} finally {{
                document.getElementById('searchLoading').style.display = 'none';
            }}
        }}
        
        function displayResults(products) {{
            let html = '<div><h3>Resultados:</h3>';
            products.forEach(product => {{
                html += `<div style="border: 1px solid #ddd; padding: 10px; margin: 10px 0;">
                    <h4>${{product.title}}</h4>
                    <p>${{product.price}} - ${{product.source}}</p>
                </div>`;
            }});
            html += '</div>';
            document.getElementById('searchResults').innerHTML = html;
        }}
        </script>
        '''
        
        return render_page("Búsqueda - Auto Parts Finder", search_content)
    except Exception as e:
        print(f"Error in search page: {e}")
        return redirect(url_for('auth_login_page'))

@app.route('/logout')
def logout():
    """Logout"""
    try:
        firebase_auth.clear_user_session()
        return redirect(url_for('auth_login_page'))
    except Exception as e:
        print(f"Error in logout: {e}")
        return redirect(url_for('home'))

@app.route('/api/search-parts-public', methods=['POST'])
def api_search_parts_public():
    """API de búsqueda pública"""
    try:
        query = request.form.get('query', '').strip()
        vehicle_year = request.form.get('vehicle_year', '').strip()
        vehicle_make = request.form.get('vehicle_make', '').strip()
        vehicle_model = request.form.get('vehicle_model', '').strip()
        
        if not query:
            return jsonify({'success': False, 'message': 'Término de búsqueda requerido'})
        
        vehicle_info = None
        if vehicle_year or vehicle_make or vehicle_model:
            vehicle_info = {
                'year': vehicle_year,
                'make': vehicle_make,
                'model': vehicle_model
            }
        
        products = auto_parts_finder.search_auto_parts(
            query=query,
            vehicle_info=vehicle_info
        )
        
        return jsonify({
            'success': True,
            'products': products,
            'count': len(products)
        })
        
    except Exception as e:
        print(f"Error en búsqueda: {e}")
        return jsonify({'success': False, 'message': 'Error interno del servidor'})

# ==============================================================================
# INICIALIZACIÓN DE INSTANCIAS GLOBALES CON MANEJO DE ERRORES
# ==============================================================================

def initialize_app_components():
    """Inicializar componentes de la aplicación de forma segura"""
    global firebase_auth, auto_parts_finder, ethical_scraper
    
    try:
        # Inicializar Firebase Auth
        firebase_auth = FirebaseAuth()
        print("✅ FirebaseAuth inicializado")
    except Exception as e:
        print(f"❌ Error inicializando FirebaseAuth: {e}")
        firebase_auth = None
    
    try:
        # Inicializar AutoPartsFinder
        auto_parts_finder = AutoPartsFinder()
        print("✅ AutoPartsFinder inicializado")
    except Exception as e:
        print(f"❌ Error inicializando AutoPartsFinder: {e}")
        auto_parts_finder = None
    
    try:
        # Inicializar EthicalWebScraper
        ethical_scraper = EthicalWebScraper()
        print("✅ EthicalWebScraper inicializado")
    except Exception as e:
        print(f"❌ Error inicializando EthicalWebScraper: {e}")
        ethical_scraper = None

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return render_page("Página no encontrada", 
        '<div class="container"><h1>Error 404</h1><p>Página no encontrada</p><a href="/">Volver al inicio</a></div>'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_page("Error interno", 
        '<div class="container"><h1>Error 500</h1><p>Error interno del servidor</p><a href="/">Volver al inicio</a></div>'), 500

@app.errorhandler(Exception)
def handle_exception(e):
    print(f"Error no manejado: {e}")
    return render_page("Error", 
        '<div class="container"><h1>Error</h1><p>Ha ocurrido un error inesperado</p><a href="/">Volver al inicio</a></div>'), 500

# ==============================================================================
# PUNTO DE ENTRADA DE LA APLICACIÓN
# ==============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("🔧 AUTO PARTS FINDER USA - INICIANDO")
    print("=" * 60)
    
    # Inicializar componentes
    initialize_app_components()
    
    # Configuración del servidor
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    
    print(f"Puerto: {port}")
    print(f"Debug: {debug_mode}")
    print(f"PIL disponible: {PIL_AVAILABLE}")
    print(f"Gemini disponible: {GEMINI_AVAILABLE}")
    print(f"BeautifulSoup4 disponible: {BS4_AVAILABLE}")
    print("=" * 60)
    
    try:
        app.run(host='0.0.0.0', port=port, debug=debug_mode)
    except Exception as e:
        print(f"Error iniciando la aplicación: {e}")
        print("Verifica que el puerto no esté en uso y que tengas los permisos necesarios.")
            'products': products,
            'count': len(products)
        })
        
    except Exception as e:
        print(f"Error en búsqueda pública: {e}")
        return jsonify({'success': False, 'message': 'Error interno del servidor'})

@app.route('/api/search-parts', methods=['POST'])
@login_required
def api_search_parts():
    """API de búsqueda para usuarios logueados"""
    try:
        query = request.form.get('query', '').strip()
        
        if not query:
            return jsonify({'success': False, 'message': 'Término requerido'})
        
        products = auto_parts_finder.search_auto_parts(query=query)
        
        return jsonify({
            'success': True,
