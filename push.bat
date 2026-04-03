@echo off
:: Agrega cambios (respeta .gitignore)
git add .

:: Pide el mensaje
set /p message="Introduce el mensaje del commit: "

:: Ejecuta commit y push
git commit -m "%message%"
git push

echo Proceso finalizado.
pause