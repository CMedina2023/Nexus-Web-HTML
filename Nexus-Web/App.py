from flask import Flask, render_template, request, jsonify, send_file, redirect
from werkzeug.utils import secure_filename
import os
import io
import story_backend
import matrix_backend
from chat_backend import cargar_conocimiento, consultar_gemini
import zipfile
import logging
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURACIÓN MEJORADA PARA PRODUCCIÓN
# ============================================================================

# Configuración del directorio temporal para las subidas
UPLOAD_FOLDER = 'temp_uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# CORREGIDO: Cargar conocimiento solo si el archivo existe
CONOCIMIENTO_JIRA = None
try:
    # Buscar el archivo en diferentes ubicaciones
    posibles_rutas = [
        "PLAN de Capacitacion.pptx",
        "./PLAN de Capacitacion.pptx",
        os.path.join(os.getcwd(), "PLAN de Capacitacion.pptx")
    ]

    ruta_encontrada = None
    for ruta in posibles_rutas:
        if os.path.exists(ruta):
            ruta_encontrada = ruta
            break

    if ruta_encontrada:
        CONOCIMIENTO_JIRA = cargar_conocimiento(ruta_encontrada)
        logger.info(f"Conocimiento JIRA cargado desde: {ruta_encontrada}")
    else:
        logger.warning("No se encontró el archivo de conocimiento JIRA")

except Exception as e:
    logger.error(f"Error cargando conocimiento JIRA: {e}")
    CONOCIMIENTO_JIRA = None

# ============================================================================
# MANEJO GLOBAL DE ERRORES PARA DEVOLVER JSON
# ============================================================================

@app.errorhandler(404)
def not_found_error(error):
    if request.path.startswith('/api/'):
        return jsonify({"error": "Endpoint no encontrado"}), 404
    return f"""
    <html>
        <head><title>404 - Página no encontrada</title></head>
        <body>
            <h1>404 - Página no encontrada</h1>
            <p>La página que buscas no existe.</p>
            <a href="/">Volver al inicio</a>
        </body>
    </html>
    """, 404

@app.errorhandler(500)
def internal_error(error):
    if request.path.startswith('/api/'):
        return jsonify({"error": "Error interno del servidor"}), 500
    return f"""
    <html>
        <head><title>500 - Error interno</title></head>
        <body>
            <h1>500 - Error interno del servidor</h1>
            <p>Ha ocurrido un error interno.</p>
            <a href="/">Volver al inicio</a>
        </body>
    </html>
    """, 500

@app.errorhandler(Exception)
def handle_exception(e):
    logger.error(f"Error no manejado: {e}", exc_info=True)
    if request.path.startswith('/api/'):
        return jsonify({"error": "Error interno del servidor"}), 500
    return f"""
    <html>
        <head><title>Error</title></head>
        <body>
            <h1>Error</h1>
            <p>Ha ocurrido un error inesperado.</p>
            <a href="/">Volver al inicio</a>
        </body>
    </html>
    """, 500

# ============================================================================
# ENDPOINT DE HEALTH CHECK
# ============================================================================

@app.route('/health')
def health_check():
    """Endpoint para verificar el estado de la aplicación"""
    try:
        api_key = os.getenv("GEMINI_API_KEY")

        status = {
            "status": "ok",
            "api_key_configured": bool(api_key),
            "api_key_length": len(api_key) if api_key else 0,
            "conocimiento_jira_loaded": CONOCIMIENTO_JIRA is not None,
            "upload_folder_exists": os.path.exists(UPLOAD_FOLDER),
            "dependencies": {}
        }

        # Verificar dependencias
        try:
            import google.generativeai
            status["dependencies"]["genai"] = "ok"
        except ImportError:
            status["dependencies"]["genai"] = "missing"

        try:
            import docx
            status["dependencies"]["docx"] = "ok"
        except ImportError:
            status["dependencies"]["docx"] = "missing"

        try:
            from pypdf import PdfReader
            status["dependencies"]["pypdf"] = "ok"
        except ImportError:
            status["dependencies"]["pypdf"] = "missing"

        return jsonify(status)

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ============================================================================
# RUTAS PRINCIPALES
# ============================================================================

@app.route('/')
def menu_principal():
    return render_template('index.html')

@app.route('/infografia')
def infografia():
    return render_template('Infografia.html')

@app.route('/overview')
def overview():
    return redirect('/infografia')

@app.route('/matrix-generator')
def matrix_generator():
    return render_template('matrix-generator.html')

@app.route('/chat')
def chat_assistant():
    return render_template('chat.html')

@app.route('/story-creator')
def story_creator():
    return render_template('story-creator.html')

# ============================================================================
# API ENDPOINTS CON MANEJO DE ERRORES
# ============================================================================

@app.route('/api/matrix', methods=['POST'])
def generate_matrix():
    try:
        logger.info("Iniciando generación de matriz")

        # Verificar archivo
        if 'file' not in request.files:
            return jsonify({"error": "No se subió ningún archivo"}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No se seleccionó un archivo"}), 400

        # Obtener parámetros del formulario, incluyendo el nuevo campo 'historia' y 'types'
        context = request.form.get('contexto', '')
        flow = request.form.get('flujo', '')
        historia = request.form.get('historia', '')
        types = request.form.getlist('types')
        if not types:
            types = ['funcional']
            logger.warning("No se especificaron tipos de prueba, usando 'funcional' por defecto")
        output_filename = request.form.get('output_filename', 'matriz_de_prueba')

        logger.info(f"Procesando archivo: {file.filename}")
        logger.info(f"Contexto: {len(context)} caracteres")
        logger.info(f"Flujo: {len(flow)} caracteres")
        logger.info(f"Historia de Usuario: {len(historia)} caracteres")
        logger.info(f"Tipos de prueba: {types}")

        # Guardar archivo temporal
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        try:
            # Extraer texto
            logger.info("Extrayendo texto del archivo")
            text = matrix_backend.extract_text_from_file(filepath)
            logger.info(f"Texto extraído: {len(text)} caracteres")

            # Generar matriz
            logger.info("Generando matriz de pruebas")
            result = matrix_backend.generar_matriz_test(context, flow, historia, text, types)
            logger.info(f"Resultado: {result['status']}")

            # Limpiar archivo temporal
            if os.path.exists(filepath):
                os.remove(filepath)

            if result['status'] == 'success':
                matrix_data = result['matrix']
                logger.info(f"Matriz generada con {len(matrix_data)} casos de prueba")

                # Crear ZIP con archivos
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED, False) as zip_file:
                    # JSON
                    json_content = matrix_backend.save_to_json_buffer(matrix_data)
                    zip_file.writestr(f"{output_filename}.json", json_content)

                    # CSV
                    csv_content = matrix_backend.save_to_csv_buffer(matrix_data)
                    zip_file.writestr(f"{output_filename}.csv", csv_content)

                    # XLSX
                    xlsx_content = matrix_backend.save_to_xlsx_buffer(matrix_data)
                    zip_file.writestr(f"{output_filename}.xlsx", xlsx_content)

                zip_buffer.seek(0)
                logger.info("Archivo ZIP creado exitosamente")

                return send_file(
                    zip_buffer,
                    as_attachment=True,
                    download_name=f"{output_filename}.zip",
                    mimetype='application/zip'
                )
            else:
                logger.error(f"Error en la generación: {result['message']}")
                return jsonify({"error": result['message']}), 500

        except Exception as e:
            logger.error(f"Error procesando archivo: {e}", exc_info=True)
            if os.path.exists(filepath):
                os.remove(filepath)
            return jsonify({"error": f"Error en el procesamiento del archivo: {str(e)}"}), 500

    except Exception as e:
        logger.error(f"Error general en generate_matrix: {e}", exc_info=True)
        return jsonify({"error": f"Error interno: {str(e)}"}), 500

@app.route('/api/chat', methods=['POST'])
def get_chat_response():
    try:
        logger.info("Procesando consulta de chat")

        if not CONOCIMIENTO_JIRA:
            return jsonify({"error": "Conocimiento JIRA no disponible"}), 503

        pregunta = request.json.get('pregunta', '') if request.json else ''
        if not pregunta:
            return jsonify({"error": "Por favor, escribe una pregunta"}), 400

        logger.info(f"Pregunta: {pregunta[:100]}...")
        respuesta = consultar_gemini(pregunta, CONOCIMIENTO_JIRA)
        logger.info("Respuesta generada exitosamente")

        return jsonify({"respuesta": respuesta})

    except Exception as e:
        logger.error(f"Error en chat: {e}", exc_info=True)
        return jsonify({"error": f"Error procesando la consulta: {str(e)}"}), 500

@app.route('/api/story', methods=['POST'])
def generate_and_download_story():
    try:
        logger.info("Iniciando generación de historias")
        logger.info(f"Parámetros recibidos - Archivo: {request.files['file'].filename if 'file' in request.files else 'No file'}, Rol: {request.form.get('role', 'Usuario')}, Tipo: {request.form.get('story_type', 'funcionalidad')}, Contexto: {request.form.get('business_context', '')[:200]}...")

        if 'file' not in request.files:
            return jsonify({"error": "No se subió ningún archivo"}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No se seleccionó un archivo"}), 400

        # Obtener parámetros
        role = request.form.get('role', 'Usuario')
        story_type = request.form.get('story_type', 'funcionalidad')
        output_filename = request.form.get('output_filename', 'historias_generadas')
        business_context = request.form.get('business_context', '')

        logger.info(f"Archivo: {file.filename}, Rol: {role}, Tipo: {story_type}, Contexto: {len(business_context)} caracteres")

        # Guardar archivo temporal
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        try:
            # Extraer texto
            text = story_backend.extract_text_from_file(filepath)
            logger.info(f"Documento con {len(text)} caracteres")

            # Procesar según tamaño
            if len(text) > 5000:
                logger.info("Usando procesamiento avanzado para documento grande")
                result = story_backend.process_large_document(text, role, story_type, business_context)

                if result['status'] == 'success':
                    stories = [result['story']]
                else:
                    raise Exception(result['message'])
            else:
                logger.info("Usando procesamiento por chunks")
                chunks = story_backend.split_document_into_chunks(text)
                logger.info(f"Dividido en {len(chunks)} chunks")

                stories = []
                for i, chunk in enumerate(chunks, 1):
                    logger.info(f"Procesando chunk {i}/{len(chunks)}")
                    result = story_backend.generate_story_from_chunk(chunk, role, story_type, business_context)
                    if result['status'] == 'success':
                        stories.append(result['story'])
                    else:
                        raise Exception(result['message'])

            # Limpiar archivo temporal
            if os.path.exists(filepath):
                os.remove(filepath)

            # Validar número mínimo de historias
            MIN_STORIES = 5
            if len(stories) < MIN_STORIES:
                logger.warning(f"Solo se generaron {len(stories)} historias, menos que el mínimo requerido ({MIN_STORIES})")

            # Crear documento Word
            logger.info("Creando documento Word")
            doc = story_backend.create_word_document(stories)
            stories_buffer = io.BytesIO()
            doc.save(stories_buffer)
            stories_buffer.seek(0)

            logger.info("Proceso completado exitosamente")

            return send_file(
                stories_buffer,
                as_attachment=True,
                download_name=f"{output_filename}.docx",
                mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )

        except Exception as e:
            logger.error(f"Error procesando story: {e}", exc_info=True)
            if os.path.exists(filepath):
                os.remove(filepath)
            return jsonify({"error": f"Error en el procesamiento: {str(e)}"}), 500

    except Exception as e:
        logger.error(f"Error general en generate_story: {e}", exc_info=True)
        return jsonify({"error": f"Error interno: {str(e)}"}), 500

@app.route('/api/preview', methods=['POST'])
def preview():
    try:
        logger.info(f"Parámetros recibidos en preview - Archivo: {request.files['file'].filename if 'file' in request.files else 'No file'}, Rol: {request.form.get('role', 'Usuario')}, Tipo: {request.form.get('story_type', 'historia de usuario')}, Contexto: {request.form.get('business_context', '')[:200]}...")

        if 'file' not in request.files:
            return jsonify({"error": "No se subió ningún archivo"}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No se seleccionó un archivo"}), 400

        role = request.form.get('role', 'Usuario')
        story_type = request.form.get('story_type', 'historia de usuario')
        business_context = request.form.get('business_context', '')

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        try:
            text = story_backend.extract_text_from_file(filepath)
            result = story_backend.generate_story_from_text(text, role, story_type, business_context)

            if os.path.exists(filepath):
                os.remove(filepath)

            if result['status'] == 'success':
                return jsonify({
                    "status": "success",
                    "stories": result['stories'],
                    "total_stories": len(result['stories'])
                })
            else:
                return jsonify({"error": result['message']}), 500

        except Exception as e:
            logger.error(f"Error en preview: {e}", exc_info=True)
            if os.path.exists(filepath):
                os.remove(filepath)
            return jsonify({"error": f"Error en el procesamiento: {str(e)}"}), 500

    except Exception as e:
        logger.error(f"Error general en preview: {e}", exc_info=True)
        return jsonify({"error": f"Error interno: {str(e)}"}), 500

# ============================================================================
# CONFIGURACIÓN PARA PRODUCCIÓN
# ============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
