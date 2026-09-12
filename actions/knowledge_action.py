import random
from memory.vector_memory import learn_text, search_knowledge

def knowledge_action(parameters: dict, **kwargs) -> str:
    """Навык для работы с векторной базой данных."""
    action = parameters.get("action", "") # "learn" (изучить) или "search" (найти)
    text = parameters.get("text", "")
    
    try:
        if action == "learn":
            if not text:
                return "Ошибка: нет текста для сохранения."
            doc_id = f"документ_{random.randint(1000, 9999)}"
            return learn_text(doc_id, text)
            
        elif action == "search":
            if not text:
                return "Ошибка: нет текста для поиска."
            return search_knowledge(text)
            
        return "Неизвестное действие. Используйте action='learn' или 'search'."
    except Exception as e:
        return f"Произошла ошибка в векторной базе: {e}"