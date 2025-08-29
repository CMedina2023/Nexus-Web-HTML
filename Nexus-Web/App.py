from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
import os
import io
import story_backend
import matrix_backend
from chat_backend import cargar_conocimiento, consultar_gemini
import zipfile

app = Flask(__name__)

# Carga el conocimiento una sola vez al iniciar la aplicación
CONOCIMIENTO_JIRA = cargar_conocimiento(r"D:\Proyectos_python\Nexus-Web\PLAN de Capacitacion.pptx")

# Configuración del directorio temporal para las subidas
UPLOAD_FOLDER = 'temp_uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Ruta para la página de la herramienta Matrix Generator
@app.route('/matrix-generator')
def matrix_generator():
    return render_template('matrix-generator.html')


@app.route('/api/matrix', methods=['POST'])
def generate_matrix():
    if 'file' not in request.files:
        return jsonify({"error": "No se subió ningún archivo"}), 400

    file = request.files['file']
    context = request.form.get('contexto', '')
    flow = request.form.get('flujo', '')
    output_filename = request.form.get('output_filename', 'matriz_de_prueba')

    if file.filename == '':
        return jsonify({"error": "No se seleccionó un archivo"}), 400

    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        try:
            text = matrix_backend.extract_text_from_file(filepath)
            result = matrix_backend.generar_matriz_test(context, flow, text)

            os.remove(filepath)

            if result['status'] == 'success':
                matrix_data = result['matrix']

                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED, False) as zip_file:
                    json_content = matrix_backend.save_to_json_buffer(matrix_data)
                    zip_file.writestr(f"{output_filename}.json", json_content)

                    csv_content = matrix_backend.save_to_csv_buffer(matrix_data)
                    zip_file.writestr(f"{output_filename}.csv", csv_content)

                zip_buffer.seek(0)

                return send_file(
                    zip_buffer,
                    as_attachment=True,
                    download_name=f"{output_filename}.zip",
                    mimetype='application/zip'
                )

            else:
                return jsonify({"error": result['message']}), 500

        except Exception as e:
            if os.path.exists(filepath):
                os.remove(filepath)
            # Imprime el error en la consola del servidor para depuración
            print(f"❌ Error en el procesamiento: {e}")
            return jsonify({"error": f"Error en el procesamiento del archivo: {e}"}), 500

# Ruta principal que sirve el menú
@app.route('/')
def menu_principal():
    return render_template('index.html')


# Ruta para la herramienta Chat Assistant
@app.route('/chat')
def chat_assistant():
    return render_template('chat.html')


# Nueva ruta de la API para el chat
@app.route('/api/chat', methods=['POST'])
def get_chat_response():
    pregunta = request.json.get('pregunta', '')
    if not pregunta:
        return jsonify({"respuesta": "Por favor, escribe una pregunta."}), 400

    respuesta = consultar_gemini(pregunta, CONOCIMIENTO_JIRA)
    return jsonify({"respuesta": respuesta})


# Ruta para la página de la herramienta Story Creator
@app.route('/story-creator')
def story_creator():
    return render_template('story-creator.html')


# API mejorada para procesar la generación de historias
@app.route('/api/story', methods=['POST'])
def generate_and_download_story():
    if 'file' not in request.files:
        return jsonify({"error": "No se subió ningún archivo"}), 400

    file = request.files['file']
    role = request.form.get('role', 'Usuario')
    story_type = request.form.get('story_type', 'funcionalidad')
    output_filename = request.form.get('output_filename', 'historias_generadas')

    if file.filename == '':
        return jsonify({"error": "No se seleccionó un archivo"}), 400

    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        try:
            # Extraer texto del documento
            text = story_backend.extract_text_from_file(filepath)

            print(f"📄 Documento con {len(text)} caracteres")
            print(f"👤 Rol: {role}")
            print(f"📝 Tipo de historia: {story_type}")

            # Determinar si usar procesamiento simple o avanzado
            if len(text) > 5000:
                # Para documentos grandes, usar el procesamiento avanzado por chunks
                print("📋 Documento grande detectado, usando procesamiento avanzado...")
                result = story_backend.process_large_document(
                    text,
                    role,
                    story_type,
                    "AIzaSyCrNYH7OtSt7c9uxkSJ9LE1s0YnFSE-e9U"
                )

                if result['status'] == 'success':
                    stories = [result['story']]  # El resultado ya viene como una historia completa
                else:
                    os.remove(filepath)
                    return jsonify({"error": result['message']}), 500

            else:
                # Para documentos medianos/pequeños, usar el método de chunks tradicional
                print("📄 Documento mediano, usando procesamiento por chunks...")
                chunks = story_backend.split_document_into_chunks(text)
                print(f"🔀 Dividido en {len(chunks)} chunks")

                stories = []
                for i, chunk in enumerate(chunks, 1):
                    print(f"🔨 Procesando chunk {i}/{len(chunks)}")
                    result = story_backend.generate_story_from_chunk(chunk, role, story_type)
                    if result['status'] == 'success':
                        stories.append(result['story'])
                    else:
                        os.remove(filepath)
                        return jsonify({"error": result['message']}), 500

            # Limpiar el archivo temporal
            os.remove(filepath)

            # Crear un documento de Word en memoria
            print("📝 Creando documento Word...")
            doc = story_backend.create_word_document(stories)
            stories_buffer = io.BytesIO()
            doc.save(stories_buffer)
            stories_buffer.seek(0)

            print("✅ ¡Proceso completado exitosamente!")

            # Devolver el archivo .docx para su descarga
            return send_file(
                stories_buffer,
                as_attachment=True,
                download_name=f"{output_filename}.docx",
                mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )

        except Exception as e:
            if os.path.exists(filepath):
                os.remove(filepath)
            print(f"❌ Error en el procesamiento: {e}")
            return jsonify({"error": f"Error en el procesamiento del archivo: {e}"}), 500


# Endpoint adicional para obtener solo las historias (sin descarga)
@app.route('/api/story/preview', methods=['POST'])
def preview_stories():
    """Endpoint para previsualizar las historias sin generar el archivo"""
    if 'file' not in request.files:
        return jsonify({"error": "No se subió ningún archivo"}), 400

    file = request.files['file']
    role = request.form.get('role', 'Usuario')
    story_type = request.form.get('story_type', 'funcionalidad')

    if file.filename == '':
        return jsonify({"error": "No se seleccionó un archivo"}), 400

    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        try:
            text = story_backend.extract_text_from_file(filepath)

            # Usar la nueva función de generación mejorada
            result = story_backend.generate_story_from_text(text, role, story_type)

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
            if os.path.exists(filepath):
                os.remove(filepath)
            return jsonify({"error": f"Error en el procesamiento del archivo: {e}"}), 500


if __name__ == '__main__':
    app.run(debug=True)