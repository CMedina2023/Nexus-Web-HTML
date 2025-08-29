import os
import google.generativeai as genai
import google.api_core.exceptions as api_exceptions
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

def generar_matriz_test(contexto, flujo, texto_documento):
    """
    Genera una matriz de pruebas a partir de los datos proporcionados,
    usando el prompt más detallado de la versión original.
    """
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return {"status": "error", "message": "API Key no configurada."}

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash-latest")

        prompt = f"""
            Basándote en el siguiente contexto del sistema, flujo de prueba y texto de documento, genera una matriz de pruebas en formato JSON.
            La matriz de pruebas debe ser un array de objetos. Cada objeto JSON representa un caso de prueba y debe contener las siguientes claves, exactamente en este orden:

            - `id_caso_prueba`: un identificador único (ej. "TC001").
            - `titulo_caso_prueba`: una descripción concisa.
            - `precondiciones`: los requisitos para ejecutar el caso de prueba.
            - `pasos`: un array de strings que describen los pasos para ejecutar la prueba.
            - `resultado_esperado`: lo que se espera que suceda al finalizar los pasos.
            - `prioridad`: la importancia del caso de prueba (ej. 'Alta', 'Media', 'Baja').
            - `observaciones`: cualquier nota o comentario adicional.

            El JSON debe ser un array que contenga todos los casos de prueba generados. No incluyas ningún texto o explicación adicional fuera del objeto JSON.

            Considera el siguiente contexto y flujo para generar la matriz de pruebas:

            Contexto del sistema:
            {contexto}

            Flujo de prueba a considerar:
            {flujo}

            Texto del documento para generar los casos de prueba:
            {texto_documento}
        """

        response = model.generate_content(prompt)
        respuesta_limpia = re.search(r'```json\n([\s\S]*)\n```', response.text)
        if respuesta_limpia:
            json_str = respuesta_limpia.group(1).strip()
            return {"status": "success", "matrix": json.loads(json_str)}
        else:
            return {"status": "error", "message": "La IA no devolvió un JSON válido. Respuesta: " + response.text}

    except json.JSONDecodeError as e:
        return {"status": "error", "message": f"Error de formato JSON en la respuesta de la IA: {e}. Respuesta: {response.text}"}
    except api_exceptions.BlockedPromptException as e:
        return {"status": "error", "message": f"Error de seguridad: La solicitud fue bloqueada. {e}"}
    except Exception as e:
        return {"status": "error", "message": f"Error al comunicarse con la API de Gemini: {e}"}

def save_to_csv_buffer(data):
    """Guarda los datos de la matriz en un buffer de memoria como CSV."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=data[0].keys())
    writer.writeheader()
    writer.writerows(data)
    return output.getvalue().encode('utf-8')

def save_to_json_buffer(data):
    """Guarda los datos de la matriz en un buffer de memoria como JSON."""
    output = io.StringIO()
    json.dump(data, output, indent=4, ensure_ascii=False)
    return output.getvalue().encode('utf-8')