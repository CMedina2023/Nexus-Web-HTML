import os
import google.generativeai as genai
import docx
from pypdf import PdfReader
import csv
import json
import re
import io
import zipfile


# ----------------------------
# Utilidades de lectura
# ----------------------------
def extract_text_from_file(file_path):
    """Extrae texto de archivos .docx o .pdf."""
    if file_path.endswith('.docx'):
        doc = docx.Document(file_path)
        return "\n".join([para.text for para in doc.paragraphs])
    elif file_path.endswith('.pdf'):
        with open(file_path, 'rb') as f:
            reader = PdfReader(f)
            text = ""
            for page in reader.pages:
                text += page.extract_text() or ""
            return text
    else:
        raise ValueError("Formato de archivo no soportado. Usa .docx o .pdf.")

def split_document_into_chunks(text, max_chunk_size=4000):
    """
    Divide un texto largo en fragmentos más pequeños basados en la longitud,
    intentando no cortar en medio de una frase.
    """
    chunks = []
    current_chunk = ""
    # Dividir el texto por frases
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    for sentence in sentences:
        if len(current_chunk) + len(sentence) + 1 < max_chunk_size:
            current_chunk += sentence + " "
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence + " "
            
    if current_chunk:
        chunks.append(current_chunk.strip())
        
    return chunks

def generar_matriz_test(contexto, flujo, texto_documento, tipos_prueba=['funcional', 'no_funcional']):
    """
    Genera una matriz de pruebas a partir de los datos proporcionados,
    usando el prompt mejorado y el formato de la versión web.
    """
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return {"status": "error", "message": "API Key no configurada."}

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash-latest")

        # Prompt base y estructura de la respuesta
        prompt_base = """
            Eres un experto en Testing y Quality Assurance con experiencia en análisis de requerimientos y diseño de casos de prueba.

            TAREA: Analizar el siguiente requerimiento y generar casos de prueba completos para lograr la MÁXIMA COBERTURA posible.

            FORMATO DE RESPUESTA: Devuelve ÚNICAMENTE un array JSON válido con objetos que contengan exactamente estas claves:
            - `id_caso_prueba`: un identificador único (ej. "TC001").
            - `titulo_caso_prueba`: una descripción concisa.
            - `Descripcion`: una descripción detallada.
            - `Precondiciones`: los requisitos para ejecutar el caso de prueba.
            - "Tipo_de_prueba": (string) "Funcional" o "No Funcional"
            - "Nivel_de_prueba": (string) "UAT"
            - "Tipo_de_ejecucion": (string) "Manual"
            - `Pasos`: un array de strings que describen los pasos para ejecutar la prueba.
            - `Resultado_esperado`: un array de strings que describe lo que se espera que suceda al finalizar los pasos.
            - `Categoria`: (string) Para funcionales: "Flujo Principal", "Flujos Alternativos", "Casos Límite", "Casos de Error". Para no funcionales: "Rendimiento", "Seguridad", "Usabilidad", "Compatibilidad", "Confiabilidad"
            - "Ambiente": (string) "QA"
            - "Ciclo": (string) "Ciclo 1"
            - "issuetype": (string) "Test Case"
            - `Prioridad`: la importancia del caso de prueba (ej. 'Alta', 'Media', 'Baja').

            El JSON debe ser un array que contenga todos los casos de prueba generados. No incluyas ningún texto o explicación adicional fuera del objeto JSON.
            """

        # Construir prompt basado en tipos seleccionados
        incluir_funcionales = "funcional" in tipos_prueba
        incluir_no_funcionales = "no_funcional" in tipos_prueba

        if incluir_funcionales and incluir_no_funcionales:
            prompt_especifico = """
            TIPOS DE PRUEBAS A GENERAR (COBERTURA COMPLETA SIN LÍMITES):

            PASO 1 - ANÁLISIS DEL REQUERIMIENTO:
            Analiza el requerimiento para entender qué aspectos necesitan cobertura:

            ASPECTOS FUNCIONALES a cubrir si están presentes:
            - Flujos de trabajo y casos de uso
            - Validaciones y transformaciones de datos
            - Reglas de negocio y lógica
            - Interacciones y integraciones
            - Manejo de errores y excepciones

            ASPECTOS NO FUNCIONALES a cubrir si están presentes:
            - Rendimiento (tiempo, carga, throughput, escalabilidad)
            - Seguridad (autenticación, autorización, protección de datos)
            - Usabilidad (experiencia de usuario, accesibilidad)
            - Compatibilidad (plataformas, navegadores, dispositivos)
            - Confiabilidad (disponibilidad, recuperación, integridad)

            PASO 2 - GENERACIÓN DE CASOS:
            Para CADA aspecto identificado, genera TODOS los casos necesarios para cobertura completa:

            PRUEBAS FUNCIONALES (genera si hay aspectos funcionales):
            - Todos los flujos principales y alternativos
            - Todas las validaciones de entrada requeridas
            - Todos los casos límite y condiciones borde
            - Todos los escenarios de error posibles
            - Todas las integraciones con otros componentes

            PRUEBAS NO FUNCIONALES (genera si hay aspectos no funcionales):
            - Todos los escenarios de carga y rendimiento relevantes
            - Todos los vectores de seguridad aplicables
            - Todos los contextos de usabilidad necesarios
            - Todas las combinaciones de compatibilidad críticas
            - Todos los escenarios de fallo y recuperación

            PRINCIPIO FUNDAMENTAL:
            - La COBERTURA COMPLETA determina la cantidad de casos, no límites artificiales
            - Genera casos hasta cubrir exhaustivamente cada aspecto del requerimiento
            - Si un requerimiento es 100% de seguridad, genera 100% casos de seguridad
            - Si un requerimiento es 100% funcional, genera 100% casos funcionales
            - Si es mixto, cubre proporcionalmente según la complejidad de cada aspecto
            """
        elif incluir_funcionales:
            prompt_especifico = """
            TIPOS DE PRUEBAS A GENERAR (COBERTURA FUNCIONAL COMPLETA):

            PRUEBAS FUNCIONALES:
            - Flujo principal y todos los casos exitosos
            - Flujos alternativos y rutas de excepción
            - Validación exhaustiva de campos y datos
            - Casos límite, condiciones borde y extremas
            - Manejo completo de errores y excepciones
            - Estados del sistema y transiciones
            - Integración con componentes relacionados

            PRINCIPIO DE COBERTURA MÁXIMA:
            - Genera TODOS los casos funcionales necesarios para cobertura completa
            - No te limites por cantidad, prioriza la cobertura exhaustiva
            - Incluye casos para cada condición, rama y escenario posible
            """
        elif incluir_no_funcionales:
            prompt_especifico = """
            TIPOS DE PRUEBAS A GENERAR (COBERTURA NO FUNCIONAL COMPLETA):

            PRUEBAS NO FUNCIONALES:
            - RENDIMIENTO: Carga normal, picos, estrés, volumen, tiempo de respuesta
            - SEGURIDAD: Autenticación, autorización, validación, ataques, cifrado
            - USABILIDAD: Navegación, accesibilidad, experiencia, interfaces
            - COMPATIBILIDAD: Múltiples entornos, navegadores, dispositivos, versiones
            - CONFIABILIDAD: Disponibilidad, recuperación, integridad, tolerancia a fallos

            PRINCIPIO DE COBERTURA MÁXIMA:
            - Genera TODOS los casos no funcionales relevantes para el requerimiento
            - Especifica métricas precisas y medibles
            - Considera todos los contextos de uso y condiciones operativas
            """
        else:
            return {"status": "success", "matrix": []}
            
        # NUEVA LÓGICA: Procesar el documento por chunks
        chunks = split_document_into_chunks(texto_documento)
        full_response_text = ""
        
        for i, chunk in enumerate(chunks):
            # Construir el prompt para el fragmento actual
            prompt_contexto = f"""
            Considera el siguiente contexto y flujo para generar la matriz de pruebas:

            Contexto del sistema:
            {contexto}

            Flujo de prueba a considerar:
            {flujo}

            Fragmento {i+1} del documento (Total: {len(chunks)}):
            {chunk}

            INSTRUCCIONES FINALES:
            - Responde SOLO con el array JSON, sin texto adicional
            - Cada caso debe ser único y aportar valor específico
            - Los pasos deben ser claros y ejecutables por cualquier tester
            - Los resultados esperados deben ser verificables y específicos
            - La respuesta debe ser un JSON completo. Si hay más de un chunk, la respuesta final debe ser la unión de los JSONs de cada chunk.
            """
            
            prompt_completo = prompt_base + prompt_especifico + prompt_contexto
            
            response = model.generate_content(prompt_completo)
            
            # Acumular la respuesta de cada fragmento
            full_response_text += response.text

        # Procesar el resultado completo
        # Combina los JSON de cada respuesta en un solo array
        all_cases = []
        json_matches = re.findall(r'```json\n([\s\S]*?)\n```', full_response_text)
        
        for json_str in json_matches:
            try:
                matrix_data_chunk = json.loads(json_str.strip())
                if isinstance(matrix_data_chunk, list):
                    all_cases.extend(matrix_data_chunk)
            except json.JSONDecodeError as e:
                # Log o manejar el error si un chunk no devolvió un JSON válido
                print(f"Error decodificando JSON de un chunk: {e}")
                
        if all_cases:
            # Normalizar los datos para el conteo y guardado
            for case in all_cases:
                tipo_key = "Tipo_de_prueba"
                if tipo_key in case:
                    case[tipo_key] = case[tipo_key].lower()

            return {"status": "success", "matrix": all_cases}
        else:
            return {"status": "error", "message": "La IA no devolvió un JSON válido. Respuesta: " + full_response_text}

    except json.JSONDecodeError as e:
        return {"status": "error",
                "message": f"Error de formato JSON en la respuesta de la IA: {e}. Respuesta: {full_response_text}"}
    except Exception as e:
        error_message = str(e).lower()
        if "blocked" in error_message or "safety" in error_message:
            return {"status": "error", "message": f"Error de seguridad: La solicitud fue bloqueada por filtros de seguridad."}
        else:
            return {"status": "error", "message": f"Error al comunicarse con la API de Gemini: {e}"}


def save_to_csv_buffer(data):
    """Guarda los datos de la matriz en un buffer de memoria como CSV."""
    # Define los nombres de las columnas en el orden deseado
    fieldnames = [
        "id_caso_prueba",
        "titulo_caso_prueba",
        "Descripcion",
        "Precondiciones",
        "Tipo_de_prueba",
        "Nivel_de_prueba",
        "Tipo_de_ejecucion",
        "Pasos",
        "Resultado_esperado",
        "Categoria",
        "Ambiente",
        "Ciclo",
        "issuetype",
        "Prioridad"
    ]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for row in data:
        # Convierte los arrays de 'Pasos' y 'Resultado_esperado' a strings separados por "|"
        row['Pasos'] = " | ".join(row.get('Pasos', []))
        row['Resultado_esperado'] = " | ".join(row.get('Resultado_esperado', []))
        writer.writerow(row)

    return output.getvalue().encode('utf-8')


def save_to_json_buffer(data):
    """Guarda los datos de la matriz en un buffer de memoria como JSON."""
    output = io.StringIO()
    json.dump(data, output, indent=4, ensure_ascii=False)
    return output.getvalue().encode('utf-8')
