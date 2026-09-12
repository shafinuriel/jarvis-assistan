from typing import List, Dict, Callable

class CodeTracker:
    def __init__(self):
        self.history: List[Dict] = []
        self.listeners: List[Callable] = []

    def add_record(self, code: str, output: str, error: str, is_success: bool):
        record = {
            "code": code,
            "output": output,
            "error": error,
            "success": is_success
        }
        self.history.append(record)
        
        # Передаем новый лог во все открытые графические окна (Code Monitor)
        for listener in self.listeners:
            try:
                listener(record)
            except Exception:
                pass

    def register_listener(self, callback: Callable):
        if callback not in self.listeners:
            self.listeners.append(callback)

    def get_last_record(self) -> Dict:
        return self.history[-1] if self.history else {}

# Глобальный объект трекера
tracker = CodeTracker()