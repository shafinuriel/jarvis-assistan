import chromadb
from pathlib import Path
#Создаем папку для базы данныхв корне проекта
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "knowledge_db"

#Инциализируем оффлайн-клиент ChromaDB
try:
    chroma_client = chromadb.PersistentClient(path=str(DB_PATH))
    # Создаем илиподключаемся к коллекции (таблице) знаний
    collection = chroma_client.get_or_create_collection(name="jarvis_general")
except Exception as e:
    print(f"[ВЕКТОРНАЯ БАЗА] Ошибка инцилиазации: {e}")
    
def learn_text(doc_id: str,text: str) -> str:
    """Джарвис читает текст и сохраняет его в векторную базу"""
    try:
        collection.add(
            documents=[text],
            ids=[doc_id] # Уникальное имя документа (напримр, "правила_python")
        )
        return f"Сэр, материал '{doc_id}' успешно проанализирован и добавлен в базу."
    except Exception as e:
        return f"Ошибка при усвоении текста: {e}"
    
def search_knowledge(query: str) -> str:
    """Джарвис ищет ответ по смыслу запроса."""
    try:
        results = collection.query(
            query_texts=[query],
            n_results=1 # Возрашаем 1 самый подходяший фрагмент
        )
        
        # Если что-то найдено
        if results['documents'] and results['documents'][0]:
            found_text = results['documents'][0][0]
            return f"Вот что я нашел в своих архивах:\n{found_text}"
        
        return "В моих базах данных нет релевантной информации."
    except Exception as e:
        return f"Ошибка поиска по базе: {e}"

#  Тут код search_knowledge окончен если будшь что-то добавлять то до этого.