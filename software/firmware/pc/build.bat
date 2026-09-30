@echo off
rem Builds the PC backend of the shared face core (face_pc.exe) with MSVC (Visual Studio Build Tools 2022).
rem Usage: pc\build.bat            (from anywhere; output in pc\build\)
setlocal
set HERE=%~dp0
set SRCLIB=%HERE%..\lib
set OUT=%HERE%build
if not exist "%OUT%" mkdir "%OUT%"
set VCVARS=C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat
if not exist "%VCVARS%" (
  echo MSVC Build Tools not found at "%VCVARS%". Install "Visual Studio Build Tools 2022" with the C++ workload.
  exit /b 1
)
call "%VCVARS%" >nul
cl /nologo /O2 /std:c++17 /EHsc /W3 /wd4244 /wd4305 /D_CRT_SECURE_NO_WARNINGS ^
  /I"%SRCLIB%\spike_face\src" /I"%SRCLIB%\spike_life\src" /I"%SRCLIB%\spike_body\src" /I"%SRCLIB%\spike_link\src" /I"%HERE%." ^
  "%HERE%face_pc.cpp" "%HERE%link_test.cpp" "%HERE%gait_test.cpp" "%SRCLIB%\spike_face\src\*.cpp" "%SRCLIB%\spike_life\src\*.cpp" ^
  "%SRCLIB%\spike_body\src\*.cpp" "%SRCLIB%\spike_link\src\*.cpp" ^
  /Fo"%OUT%\\" /Fe"%OUT%\face_pc.exe" /link bcrypt.lib
if errorlevel 1 exit /b 1
echo built %OUT%\face_pc.exe
endlocal
