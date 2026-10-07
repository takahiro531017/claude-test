' 営業訪問管理アプリを、黒い画面を出さずに起動します。
' 社内ネットワークの他の端末からも使えるよう 0.0.0.0 で待ち受けます。
' ダブルクリックで起動(ブラウザも開く)。引数 silent を付けるとブラウザは開きません(自動起動用)。
Option Explicit
Dim sh, fso, dir, py, logf, q, cmd, rc, silent
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
q = Chr(34)
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir
silent = (WScript.Arguments.Count > 0)
py = dir & "\.venv\Scripts\python.exe"
logf = dir & "\data\server.log"

If Not fso.FileExists(py) Then
  MsgBox "アプリの準備が終わっていません。" & vbCrLf & "(.venv フォルダが見つかりません)", vbExclamation, "営業訪問管理"
  WScript.Quit 1
End If

' すでに動いているか確認(8000番ポートが使用中なら起動済み)
rc = sh.Run("cmd /c netstat -ano | findstr " & q & ":8000 " & q & " | findstr LISTENING >nul", 0, True)
If rc <> 0 Then
  cmd = "cmd /c " & q & q & py & q & " -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >> " & q & logf & q & " 2>&1" & q
  sh.Run cmd, 0, False
  WScript.Sleep 4000
End If

If Not silent Then sh.Run "http://127.0.0.1:8000/"
