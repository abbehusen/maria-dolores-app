@echo off
setlocal
cd /d "%~dp0"
if exist ".venv-build\Scripts\python.exe" goto validar_ambiente

rem Primeiro tenta o Python ativo, inclusive Conda/Miniforge.
python -c "import sys,struct; sys.exit(0 if sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8 else 1)" >nul 2>nul
if not errorlevel 1 (
  python -m venv .venv-build
  if errorlevel 1 goto erro
  goto validar_ambiente
)

rem Depois tenta o Python Launcher, se estiver instalado.
py -3.12 -c "import struct; raise SystemExit(0 if struct.calcsize('P') == 8 else 1)" >nul 2>nul
if not errorlevel 1 (
  py -3.12 -m venv .venv-build
  if errorlevel 1 goto erro
  goto validar_ambiente
)

echo Nao foi encontrado Python 3.12 de 64 bits ativo.
echo Se usa Conda ou Miniforge, abra o prompt correspondente e execute:
echo   conda create -n fe_flow_build python=3.12 -y
echo   conda activate fe_flow_build
echo Depois entre nesta pasta e execute GERAR_EXE.bat novamente.
echo Pasta: %CD%
pause
exit /b 1

:validar_ambiente
".venv-build\Scripts\python.exe" -c "import sys,struct; print('Python:',sys.version); sys.exit(0 if sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8 else 1)"
if errorlevel 1 (
  echo A pasta .venv-build existente usa um Python incompativel.
  echo Renomeie essa pasta e execute este script novamente com Python 3.12 de 64 bits.
  pause
  exit /b 1
)
".venv-build\Scripts\python.exe" -m pip install -r requirements.txt pyinstaller==6.22.0
if errorlevel 1 goto erro
".venv-build\Scripts\python.exe" -m PyInstaller --noconfirm --clean FeAbbehusenFlow.spec
if errorlevel 1 goto erro
copy /Y "EXECUTAVEL_WINDOWS.md" "dist\FeAbbehusenFlow\LEIA-ME.md" >nul
 echo.
 echo Pronto: dist\FeAbbehusenFlow\FeAbbehusenFlow.exe
 echo Copie a pasta FeAbbehusenFlow inteira para o outro computador.
 echo Os dados ficam separados, em LOCALAPPDATA\FeAbbehusenFlow\data.
 pause
 exit /b 0
:erro
 echo.
 echo A geracao falhou. Confira a mensagem acima.
 pause
 exit /b 1
