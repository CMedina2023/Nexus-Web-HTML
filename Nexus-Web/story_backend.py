import os
import google.generativeai as genai
import docx
from pypdf import PdfReader
import re


# -----------------------------
# Funciones auxiliares
# -----------------------------
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


def split_document_into_chunks(text, max_chunk_size=3000):
    """Divide el documento en chunks manejables."""
    # Primero intentar dividir por secciones/capítulos
    sections = re.split(r'\n\s*(?:[0-9]+\.|\b(?:CAPÍTULO|SECCIÓN|MÓDULO|FUNCIONALIDAD)\b)', text, flags=re.IGNORECASE)

    chunks = []
    current_chunk = ""

    for section in sections:
        if len(current_chunk) + len(section) < max_chunk_size:
            current_chunk += section
        else:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            current_chunk = section

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    # Si no hay divisiones claras, dividir por párrafos
    if len(chunks) == 1 and len(text) > max_chunk_size:
        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = ""

        for para in paragraphs:
            if len(current_chunk) + len(para) < max_chunk_size:
                current_chunk += para + "\n\n"
            else:
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                current_chunk = para + "\n\n"

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

    return chunks


def create_analysis_prompt(document_text, role, business_context=None):
    """Crea un prompt inicial para análisis de funcionalidades."""
    context_section = ""
    if business_context and business_context.strip():
        context_section = f"""
CONTEXTO ADICIONAL DE NEGOCIO:
{business_context}

IMPORTANTE: Debes tomar en cuenta TANTO los requerimientos del documento COMO el contexto adicional proporcionado.
"""

    return f"""
Eres un analista de negocios Senior. Tu tarea es IDENTIFICAR Y LISTAR todas las funcionalidades del siguiente documento.

DOCUMENTO A ANALIZAR:
{document_text}
{context_section}
INSTRUCCIONES:
1. Lee COMPLETAMENTE el documento
2. Identifica TODAS las funcionalidades mencionadas
3. Toma en cuenta el contexto adicional de negocio si se proporciona
4. Crea una LISTA NUMERADA de funcionalidades EXCLUSIVAMENTE para el rol: {role}.
5. Ignora cualquier funcionalidad que corresponda a otros roles diferentes a {role}.

FORMATO DE RESPUESTA:
Lista de Funcionalidades Identificadas:
1. [Nombre funcionalidad] - [Descripción breve]
2. [Nombre funcionalidad] - [Descripción breve]
...

Al final indica: "TOTAL FUNCIONALIDADES IDENTIFICADAS: [número]"

NO generes historias de usuario todavía, solo la lista de funcionalidades.
"""


def create_story_generation_prompt(functionalities_list, document_text, role, business_context, start_index,
                                   batch_size=5):
    """Crea prompt para generar historias de usuario por lotes."""
    end_index = min(start_index + batch_size, len(functionalities_list))
    selected_functionalities = functionalities_list[start_index:end_index]

    func_text = "\n".join([f"{i + start_index + 1}. {func}" for i, func in enumerate(selected_functionalities)])

    context_section = ""
    if business_context and business_context.strip():
        context_section = f"""
CONTEXTO ADICIONAL DE NEGOCIO (OBLIGATORIO CONSIDERAR):
{business_context}

IMPORTANTE: Las historias de usuario deben integrar TANTO la información del documento COMO las consideraciones del contexto adicional.
"""

    return f"""
Eres un analista de negocios Senior. Genera historias de usuario DETALLADAS para las siguientes funcionalidades específicas.

FUNCIONALIDADES A DESARROLLAR (Lote {start_index + 1} a {end_index}):
{func_text}

DOCUMENTO DE REFERENCIA (para contexto adicional):
{document_text[:2000]}...
{context_section}
FORMATO OBLIGATORIO para CADA funcionalidad:

```
╔════════════════════════════════════════════════════════════════════════════════
HISTORIA #{start_index + 1}: [Título de la funcionalidad]
════════════════════════════════════════════════════════════════════════════════

COMO: {role}
QUIERO: [funcionalidad específica y detallada]
PARA: [beneficio de negocio claro y medible]

CRITERIOS DE ACEPTACIÓN:

🔹 Escenario Principal:
   DADO que [contexto específico]
   CUANDO [acción concreta del usuario]
   ENTONCES [resultado esperado detallado]

🔹 Escenario Alternativo:
   DADO que [contexto alternativo]
   CUANDO [acción diferente]
   ENTONCES [resultado alternativo]

🔹 Validaciones:
   DADO que [condición de error]
   CUANDO [acción que genera error]
   ENTONCES [manejo de error esperado]

REGLAS DE NEGOCIO:
• [Regla específica 1]
• [Regla específica 2]

PRIORIDAD: [Alta/Media/Baja]
COMPLEJIDAD: [Simple/Moderada/Compleja]

════════════════════════════════════════════════════════════════════════════════
```

IMPORTANTE: 
- TODAS las historias deben generarse ÚNICAMENTE desde la perspectiva del rol **{role}**.
- Integra el contexto adicional de negocio en las reglas de negocio y criterios de aceptación.
- No inventes ni incluyas otros roles diferentes a {role}.
- Numera consecutivamente desde {start_index + 1}.
"""


def create_advanced_prompt(document_text, role, story_type, business_context=None):
    """Crea el prompt avanzado basado en el tipo de historia solicitada."""

    context_section = ""
    if business_context and business_context.strip():
        context_section = f"""
CONTEXTO ADICIONAL DE NEGOCIO (CRÍTICO):
{business_context}

INTEGRACIÓN OBLIGATORIA: Debes incorporar este contexto en:
- Los criterios de aceptación
- Las reglas de negocio
- Los escenarios de validación
- Las consideraciones de prioridad
"""

    if story_type == 'historia de usuario' or story_type == 'funcionalidad':
        # Para documentos grandes, usar estrategia de chunks
        if len(document_text) > 5000:
            return "CHUNK_PROCESSING_NEEDED"

        # Para documentos medianos/pequeños, prompt optimizado
        prompt = f"""
Eres un analista de negocios Senior especializado en QA y análisis exhaustivo de requerimientos.

DOCUMENTO A ANALIZAR:
{document_text}
{context_section}
INSTRUCCIONES CRÍTICAS:

1. ANÁLISIS EXHAUSTIVO:
   - Identifica TODAS las funcionalidades del documento
   - Incluye ÚNICAMENTE las que correspondan al rol que se proporciona en la UI {role}
   - Integra el contexto adicional de negocio en cada historia

2. GENERACIÓN DE HISTORIAS PARA: **{role}**

FORMATO OBLIGATORIO:

```
╔════════════════════════════════════════════════════════════════════════════════
HISTORIA #{{número}}: [Título]
════════════════════════════════════════════════════════════════════════════════

COMO: {role}
QUIERO: [funcionalidad específica]
PARA: [beneficio de negocio]

CRITERIOS DE ACEPTACIÓN:

🔹 Escenario Principal:
   DADO que [contexto]
   CUANDO [acción]
   ENTONCES [resultado]

🔹 Escenario Alternativo:
   DADO que [contexto alternativo]
   CUANDO [acción diferente]
   ENTONCES [resultado alternativo]

🔹 Validaciones:
   DADO que [error]
   CUANDO [acción error]
   ENTONCES [manejo error]

REGLAS DE NEGOCIO:
• [Regla 1]
• [Regla 2]

PRIORIDAD: [Alta/Media/Baja]
COMPLEJIDAD: [Simple/Moderada/Compleja]

════════════════════════════════════════════════════════════════════════════════
```

EXPECTATIVA: Genera entre 10-50 historias según el contenido del documento.

IMPORTANTE: 
- Si el documento es extenso y sientes que podrías cortarte, termina la historia actual y agrega al final:
"CONTINÚA EN EL SIGUIENTE LOTE - FUNCIONALIDADES PENDIENTES: [lista las que faltan]"
- SIEMPRE integra el contexto adicional proporcionado en las historias generadas.
"""

    elif story_type == 'característica':
        prompt = f"""
Eres un analista de negocios Senior especializado en requisitos no funcionales.

DOCUMENTO A ANALIZAR:
{document_text}
{context_section}
Identifica TODOS los requisitos no funcionales (rendimiento, seguridad, usabilidad, etc.) y genera historias para el rol: {role}

FORMATO:

```
╔════════════════════════════════════════════════════════════════════════════════
HISTORIA NO FUNCIONAL #{{número}}: [Título]
════════════════════════════════════════════════════════════════════════════════

COMO: {role}
NECESITO: [requisito no funcional]
PARA: [garantizar calidad]

CRITERIOS DE ACEPTACIÓN:
• [Criterio medible 1]
• [Criterio medible 2]

MÉTRICAS:
• [Métrica objetivo]

CATEGORÍA: [Rendimiento/Seguridad/Usabilidad/etc.]
PRIORIDAD: [Alta/Media/Baja]

════════════════════════════════════════════════════════════════════════════════
```

IMPORTANTE: Integra el contexto adicional de negocio en los criterios y métricas.
"""

    else:
        # Para cualquier otro tipo, usar el formato funcional por defecto
        return create_advanced_prompt(document_text, role, 'funcionalidad', business_context)

    return prompt


def process_large_document(document_text, role, story_type, business_context=None):
    """Procesa documentos grandes dividiéndolos en chunks."""
    try:
        api_key = os.getenv("GEMINI_API_KEY")

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash-latest")

        print("📄 Documento grande detectado. Iniciando análisis por fases...")

        # Debug para verificar parámetros
        print(f"🔍 Debug - business_context recibido: {business_context}")
        print(f"🔍 Debug - role: {role}")
        print(f"🔍 Debug - story_type: {story_type}")

        # Fase 1: Análisis de funcionalidades
        print("🔍 Fase 1: Identificando todas las funcionalidades...")
        analysis_prompt = create_analysis_prompt(document_text, role, business_context)

        analysis_response = model.generate_content(analysis_prompt, request_options={"timeout": 90})

        # Extraer lista de funcionalidades
        functionalities = []
        lines = analysis_response.text.split('\n')
        for line in lines:
            if re.match(r'^\d+\.', line.strip()):
                functionalities.append(line.strip())

        print(f"✅ Identificadas {len(functionalities)} funcionalidades")

        # Fase 2: Generar historias por lotes
        all_stories = []
        batch_size = 5  # Procesar 5 funcionalidades a la vez
        total_batches = (len(functionalities) + batch_size - 1) // batch_size

        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            print(
                f"🔨 Generando lote {batch_num + 1}/{total_batches} (funcionalidades {start_idx + 1}-{min(start_idx + batch_size, len(functionalities))})")

            story_prompt = create_story_generation_prompt(
                functionalities, document_text, role, business_context, start_idx, batch_size
            )

            try:
                story_response = model.generate_content(story_prompt, request_options={"timeout": 120})
                all_stories.append(story_response.text)
                print(f"✅ Lote {batch_num + 1} completado")
            except Exception as e:
                print(f"⚠️ Error en lote {batch_num + 1}: {e}")
                continue

        # Combinar todas las historias
        context_summary = ""
        if business_context and business_context.strip():
            # Verificar que no sea la API key
            if not business_context.startswith("AIza"):
                context_summary = f"""
CONTEXTO ADICIONAL APLICADO:
{business_context[:200]}{'...' if len(business_context) > 200 else ''}
{'-' * 70}
"""
            else:
                print("⚠️ ADVERTENCIA: Se detectó API key en business_context, ignorando...")
                context_summary = f"""
CONTEXTO ADICIONAL APLICADO: No proporcionado
{'-' * 70}
"""
        else:
            context_summary = f"""
CONTEXTO ADICIONAL APLICADO: No proporcionado
{'-' * 70}
"""

        final_content = f"""
ANÁLISIS COMPLETO - {len(functionalities)} FUNCIONALIDADES IDENTIFICADAS
{"=" * 70}
{context_summary}
FUNCIONALIDADES IDENTIFICADAS:
{chr(10).join(functionalities)}

{"=" * 70}
HISTORIAS DE USUARIO DETALLADAS
{"=" * 70}

{chr(10).join(all_stories)}

{"=" * 70}
RESUMEN FINAL
{"=" * 70}
✅ Total de funcionalidades procesadas: {len(functionalities)}
✅ Total de lotes generados: {total_batches}
✅ Contexto adicional: {'Aplicado' if business_context and not business_context.startswith("AIza") else 'No proporcionado'}
✅ Análisis completado exitosamente
"""

        print("🎉 Análisis completo finalizado exitosamente")
        return {"status": "success", "story": final_content}

    except Exception as e:
        print(f"❌ Error en procesamiento por chunks: {e}")
        return {"status": "error", "message": f"Error en procesamiento avanzado: {e}"}


def generate_story_from_chunk(chunk, role, story_type, business_context=None):
    """
    Genera una historia de usuario a partir de un fragmento de texto usando la API de Gemini.
    Versión mejorada con prompts avanzados y contexto de negocio.
    """
    try:
        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            return {"status": "error", "message": "API Key no configurada."}

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash-latest")

        # Crear prompt avanzado y detectar si necesita procesamiento especial
        prompt = create_advanced_prompt(chunk, role, story_type, business_context)

        # Si el documento requiere procesamiento por chunks
        if prompt == "CHUNK_PROCESSING_NEEDED":
            # Pasar los parámetros en el orden correcto
            return process_large_document(chunk, role, story_type, business_context)

        # Generar contenido con el prompt avanzado
        response = model.generate_content(prompt, request_options={"timeout": 90})

        # Limpiar la respuesta
        story_text = response.text.strip()

        # Verificar si la respuesta se cortó
        if "La generación completa" in story_text or "Este ejemplo ilustra" in story_text:
            print("⚠️ Respuesta posiblemente incompleta detectada")

        return {"status": "success", "story": story_text}

    except Exception as e:
        return {"status": "error", "message": f"Error en la generación: {e}"}


def create_word_document(stories):
    """Crea un documento de Word en memoria con las historias generadas."""
    doc = docx.Document()

    # Título principal
    title = doc.add_heading('Historias de Usuario Generadas', level=1)

    # Agregar cada historia
    for i, story in enumerate(stories, 1):
        # Si la historia contiene el formato completo, mantenerlo
        if "HISTORIA #" in story or "═" in story:
            # Agregar la historia completa tal como viene
            doc.add_paragraph(story)
        else:
            # Si es una historia simple, agregar un formato básico
            doc.add_heading(f'Historia #{i}', level=2)
            doc.add_paragraph(story)

        # Agregar separador entre historias
        doc.add_paragraph()
        doc.add_paragraph("─" * 50)
        doc.add_paragraph()

    return doc


# Función de compatibilidad para mantener la API existente
def generate_story_from_text(text, role, story_type, business_context=None):
    """
    Función wrapper para mantener compatibilidad con la API existente
    pero usando el nuevo sistema de chunks mejorado con contexto de negocio.
    """
    chunks = split_document_into_chunks(text)
    stories = []

    for chunk in chunks:
        result = generate_story_from_chunk(chunk, role, story_type, business_context)
        if result['status'] == 'success':
            stories.append(result['story'])
        else:
            return result  # Retorna el error

    return {"status": "success", "stories": stories}


# Nueva función principal que incluye contexto de negocio
def generate_stories_with_context(document_text, role, story_type, business_context=None):
    """
    Función principal para generar historias de usuario con contexto de negocio.

    Args:
        document_text (str): Contenido del documento a analizar
        role (str): Rol del usuario (Usuario, Administrador, etc.)
        story_type (str): Tipo de historias (funcionalidad, característica)
        business_context (str, optional): Contexto adicional de negocio

    Returns:
        dict: Resultado de la generación con status y contenido
    """
    return generate_story_from_text(document_text, role, story_type, business_context)

