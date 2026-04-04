@echo off
:: 1. Agregamos todo
git add .

:: 2. Mensaje de commit
set /p message="Introduce el mensaje del commit: "
git commit -m "%message%"

:: 3. Sincronizacion segura (Rebase)
echo Intentando sincronizar de forma segura...
git pull origin main --rebase

:: 4. Verificamos si el pull salio bien antes de subir
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Hubo un conflicto de versiones. 
    echo Por favor, revisa el index.html manualmente antes de seguir.
    pause
    exit
)

:: 5. Subida final
git push origin main
echo.
echo ¡Cambios subidos con éxito y sin riesgos!
pause