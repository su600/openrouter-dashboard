Dim sh, dir
Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.Run "cmd /c cd /d """ & dir & """ && pip install -q -r requirements.txt && pythonw main.py", 0, False
