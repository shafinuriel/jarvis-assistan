import os
import subprocess
import time
# Автоматически определяем путь к adb.exe внутри папки проекта
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADB_PATH = os.path.join(BASE_DIR, "platform-tools", "adb.exe")
def unlock_phone(pin_code=None):
    try:
        # 1.Будим экран телефона
        subprocess.run([ADB_PATH, "shell", "input", "keyevent", "224"], check=True)
        
        #2. Делаем свап снизу вверх (разблокрировка)
        subprocess.run([ADB_PATH, "shell", "input", "swipe", "500", "1800", "500", "400", "150"], check=True)
        time.sleep(0.5)
        
        #3. Вводим PIN-код, если он передан и нажимаем Enter (код 66)
        if pin_code:
            subprocess.run([ADB_PATH, "shell", "input", "text", str(pin_code)], check=True)
            subprocess.run([ADB_PATH, "shell", "input", "keyevent", "66"], check=True)
        return "Сэр, телефон успешно разблокирован."
    except Exception as e:
        return f"Ошибка при управлении телефоном: {e}"
def phone_action(parameters=None, player=None):
    pin = parameters.get("pin") if parameters else "Nuriel0305"
    return unlock_phone(pin_code=pin)
