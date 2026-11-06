import subprocess
import sys
import platform
from pathlib import Path


def run(cmd, check=True):
    """Запуск команды с понятным выводом"""
    print(f"→ {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False)
    if check and result.returncode != 0:
        print(f"❌ Команда завершилась с ошибкой (код {result.returncode})")
        return False
    return True


print("=" * 50)
print("JARVIS Setup")
print("=" * 50)

# 1. Установка зависимостей
print("\n[1/3] Installing requirements...")

success = run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

if not success:
    print("\nПробую с флагом --break-system-packages...")
    success = run([
        sys.executable, "-m", "pip", "install", 
        "--break-system-packages", "-r", "requirements.txt"
    ])

if not success:
    print("\n❌ Не удалось установить зависимости.")
    print("Попробуй вручную:")
    print(f"   {sys.executable} -m pip install -r requirements.txt")
    sys.exit(1)

# 2. Playwright
print("\n[2/3] Installing Playwright browsers...")
try:
    run([sys.executable, "-m", "playwright", "install"], check=False)
except Exception as e:
    print(f"⚠ Playwright install warning: {e}")
    print("Можно установить позже командой: python -m playwright install")

# 3. Windows-специфика
if platform.system() == "Windows":
    print("\n[3/3] Checking pywin32...")
    try:
        import win32com.client  # noqa: F401
        print("✓ pywin32 OK")
    except ImportError:
        print("⚠ pywin32 не найден. Пробую переустановить...")
        run([sys.executable, "-m", "pip", "install", "--force-reinstall", "pywin32"], check=False)

print("\n" + "=" * 50)
print("✅ Setup complete!")
print("Start J.A.R.V.I.S. with command:")
print("   python main.py")
print("=" * 50)

