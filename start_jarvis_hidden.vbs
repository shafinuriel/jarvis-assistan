Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)

' Запускаем через python (не pythonw) + скрываем окно консоли
WshShell.Run "cmd /c python main.py", 0, False