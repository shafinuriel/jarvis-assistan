import os
import sys
import json
import subprocess

def run_diagnostic():
    print("=== [JARVIS] Запуск полной диагностики системы ===")
    errors = 0

    # 1. Проверка структуры ключевых папок
    required_dirs = ["sandbox", "auto_skill", "config", "core", "memory"]
    for d in required_dirs:
        if os.path.exists(d):
            print(f"[OK] Папка найдена: {d}/")
        else:
            print(f"[ВНИМАНИЕ] Папка не найдена: {d}/ (создаем...)")
            os.makedirs(d, exist_ok=True)

    # 2. Проверка конфигурации API ключа
    api_path = os.path.join("config", "api_keys.json")
    if os.path.exists(api_path):
        try:
            with open(api_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("gemini_api_key"):
                    print("[OK] Файл конфигурации API и ключ обнаружены.")
                else:
                    print("[ОШИБКА] Ключ 'gemini_api_key' в api_keys.json пустой!")
                    errors += 1
        except Exception as e:
            print(f"[ОШИБКА] Не удалось прочитать api_keys.json: {e}")
            errors += 1
    else:
        print(f"[ОШИБКА] Файл конфигурации не найден по пути: {api_path}")
        errors += 1

    # 3. Тест песочницы (subprocess + UTF-8 щит)
    sandbox_script = os.path.join("sandbox", "diag_test.py")
    try:
        with open(sandbox_script, "w", encoding="utf-8") as f:
            f.write("print('Sandbox test OK')")

        res = subprocess.run(
            [sys.executable, "-X", "utf8", "diag_test.py"],
            capture_output=True,
            timeout=3,
            cwd="sandbox"
        )
        output = res.stdout.decode("utf-8", errors="replace").strip()
        
        if "Sandbox test OK" in output:
            print("[OK] Песочница исполнения кода работает стабильно.")
        else:
            print(f"[ОШИБКА] Песочница вернула странный вывод: {output}")
            errors += 1

        if os.path.exists(sandbox_script):
            os.remove(sandbox_script)
    except Exception as e:
        print(f"[ОШИБКА] Сбой при тестировании песочницы: {e}")
        errors += 1

    # Итог
    print("==================================================")
    if errors == 0:
        print("Результат: Все системы в норме. Проект полностью готов к работе!")
    else:
        print(f"Результат: Диагностика выявила проблем: {errors}. Требуется внимание.")

if __name__ == "__main__":
    run_diagnostic()