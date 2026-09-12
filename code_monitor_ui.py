from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget, 
                             QTextEdit, QLabel, QPushButton, QSplitter)
from PyQt6.QtCore import Qt
from actions.code_tracker import tracker
from actions.code_tracker import CodeTracker

class CodeMonitorWindow(QDialog):
    def __init__(self, parent=None, request_fix_callback=None):
        super().__init__(parent)
        self.setWindowTitle("JARVIS | Системный Монитор Кода")
        self.resize(900, 600)
        self.setStyleSheet("background-color: #0d1117; color: #c9d1d9; font-family: Consolas;")
        
        self.request_fix_callback = request_fix_callback
        self.current_selected_record = None

        layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Левая часть: Список запусков
        left_widget = QListWidget()
        left_widget.setStyleSheet("background-color: #161b22; border: 1px solid #30363d;")
        left_widget.itemClicked.connect(self.load_details)
        self.list_widget = left_widget
        splitter.addWidget(left_widget)

        # Правая часть: Детали кода
        right_panel = QVBoxLayout()
        
        self.status_label = QLabel("Выберите лог слева...")
        self.status_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #58a6ff;")
        right_panel.addWidget(self.status_label)

        right_panel.addWidget(QLabel("Выполненный код:"))
        self.code_view = QTextEdit()
        self.code_view.setReadOnly(True)
        self.code_view.setStyleSheet("background-color: #161b22; border: 1px solid #30363d;")
        right_panel.addWidget(self.code_view)

        right_panel.addWidget(QLabel("Терминал / Ошибка:"))
        self.output_view = QTextEdit()
        self.output_view.setReadOnly(True)
        self.output_view.setStyleSheet("background-color: #161b22; border: 1px solid #30363d; color: #ff7b72;")
        right_panel.addWidget(self.output_view)

        # Кнопка отправки на исправление
        self.fix_btn = QPushButton("⚙️ Отправить Джарвису на модификацию")
        self.fix_btn.setStyleSheet("background-color: #238636; color: white; padding: 10px; font-weight: bold;")
        self.fix_btn.clicked.connect(self.request_fix)
        right_panel.addWidget(self.fix_btn)

        # Собираем окно
        right_widget = QDialog()
        right_widget.setLayout(right_panel)
        splitter.addWidget(right_widget)
        layout.addWidget(splitter)

        self.refresh_list()
        
        # Подписываем окно на новые логи в реальном времени:
        tracker.register_listener(lambda record: self.refresh_list())
    
    def refresh_list(self):
        self.list_widget.clear()
        for i, record in enumerate(tracker.history):
            status = "Успех" if record.get("success") else "Ошибка"
            self.list_widget.addItem(f"Запуск {i+1} | {status}")
    
    def load_details(self, item):
        index = self.list_widget.row(item)
        if index < 0 or index >= len(tracker.history):
            return

        record = tracker.history[index]
        self.current_selected_record = record

        # Статус
        status = "Успех" if record.get("success") else "Ошибка"
        self.status_label.setText(f"Статус: {status}")

        # Код
        self.code_view.setText(record.get("code", ""))

        # Вывод / Ошибка
        if record.get("success"):
            self.output_view.setText(record.get("output", ""))
        else:
            self.output_view.setText(record.get("error", "") or "Нет текста ошибки")

    def request_fix(self):
        if self.current_selected_record and self.request_fix_callback:
            prompt = (
                f"Джарвис, в последнем коде возникла проблема или нужно улучшение. "
                f"Ознакомься с исходным кодом:\n\n{self.current_selected_record['code']}\n\n"
                f"Вывод/Ошибка терминала:\n{self.current_selected_record['error'] or self.current_selected_record['output']}\n\n"
                f"Проанализируй и перепиши код правильно, затем выполни его снова."
            )
            self.request_fix_callback(prompt)
            self.close()
    
    def on_new_log_received(self, record: dict):
        # Отображение кода в верхнем правом блоке
        if hasattr(self, 'code_editor'):
            self.code_editor.setText(record.get('code', ''))
        
        # Отображение вывода или ошибки в нижнем правом блоке
        if hasattr(self, 'terminal_output'):
            out = record.get('output', '')
            err = record.get('error', '')
            text = out if record.get('success') else f"ОШИБКА:\n{err}"
            self.terminal_output.setText(text)