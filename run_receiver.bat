@echo off
chcp 65001 > nul
title 해아림한의원 무상태 설문 수신기 (원내 진료실용)
cd /d "%~dp0"
echo [해아림한의원 무상태 설문 수신 대시보드]를 시작합니다...
echo 대시보드 실행 시 자동으로 Supabase 활성 유지(Keep-Alive Ping)가 수행됩니다.
streamlit run app.py
pause

