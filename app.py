# -*- coding: utf-8 -*-
"""
한의원 무상태(Stateless) 설문 중계 시스템 - 원내 진료실 PC용 뷰어 (Local Receiver)
실행 명령어: streamlit run app.py
"""

import csv
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple
from urllib.parse import urlencode

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv, set_key

from survey_definitions import SURVEY_CATALOG, SURVEY_PRESETS, evaluate_survey_response
from report_generator import (
    normalize_payload_surveys,
    build_emr_chart_text,
    generate_standalone_html_report,
)
from build_frontend import build_and_save_frontend

# ============================================================================
# 기본 페이지 설정 및 환경변수 로드
# ============================================================================
st.set_page_config(
    page_title="해아림 무상태 설문 수신기 (원내 진료실용)",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)


def get_config() -> Dict[str, str]:
    load_dotenv(dotenv_path=ENV_PATH, override=True)
    default_dir = str(Path(__file__).parent / "survey_data")
    return {
        "SUPABASE_URL": os.getenv("SUPABASE_URL", "").strip().rstrip("/"),
        "SUPABASE_ANON_KEY": os.getenv("SUPABASE_ANON_KEY", "").strip(),
        "LOCAL_SAVE_DIR": os.getenv("LOCAL_SAVE_DIR", default_dir).strip() or default_dir,
        "PATIENT_WEB_URL": os.getenv("PATIENT_WEB_URL", "https://hearimay-cell.github.io/clinic-survey").strip(),
    }


def ensure_directories(base_dir_str: str) -> Tuple[Path, Path]:
    """
    지정된 로컬 저장 폴더(공유폴더/원드라이브 폴더)와 하위 수신 대기 폴더(inbox_raw)를 생성합니다.
    """
    base_dir = Path(base_dir_str)
    inbox_dir = base_dir / "inbox_raw"
    base_dir.mkdir(parents=True, exist_ok=True)
    inbox_dir.mkdir(parents=True, exist_ok=True)
    return base_dir, inbox_dir


def is_supabase_configured(cfg: Dict[str, str]) -> bool:
    url = cfg.get("SUPABASE_URL", "")
    key = cfg.get("SUPABASE_ANON_KEY", "")
    return bool(url and key and "your-project-id" not in url and "your-anon" not in key)


def supabase_headers(anon_key: str) -> Dict[str, str]:
    """
    Supabase 최신 Publishable Key (`sb_publishable_...`) 및 기존 JWT `anon` Key (`eyJ...`) 모두 호환.
    `sb_publishable_...` 키 사용 시 Authorization: Bearer 헤더에 넣으면 PostgREST에서 JWT 형식 오류가 발생하므로
    `apikey` 헤더만 전송하고, 기존 `eyJ...` JWT 형식일 때만 Authorization 헤더를 함께 전송합니다.
    """
    key = anon_key.strip()
    headers = {
        "apikey": key,
        "Content-Type": "application/json",
    }
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


# ============================================================================
# Supabase 7일 미사용 일시정지(Pause) 방지용 자동 Health Check Ping
# ============================================================================
def send_supabase_keepalive_ping(cfg: Dict[str, str]) -> Tuple[bool, str]:
    """
    대시보드를 켤 때마다 자동으로 Supabase의 survey_responses 테이블에
    가벼운 조회(Health check ping)를 보내 무료 플랜의 7일 미사용 일시정지(Pause)를 방지합니다.
    """
    if not is_supabase_configured(cfg):
        return False, "Supabase 미설정 (.env에 URL과 anon Key를 입력해 주세요)"

    url = cfg["SUPABASE_URL"]
    key = cfg["SUPABASE_ANON_KEY"]
    headers = supabase_headers(key)

    try:
        relay_endpoint = f"{url}/rest/v1/survey_responses?select=id&limit=1"
        r_resp = requests.get(relay_endpoint, headers=headers, timeout=6)

        if r_resp.status_code in (200, 206):
            ts_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return True, f"survey_responses 테이블 정상 연결됨 (최근 활성 유지 Ping: {ts_str})"
        else:
            return False, f"연결 응답 오류 (HTTP {r_resp.status_code}: {r_resp.text[:120]})"
    except Exception as e:
        return False, f"네트워크/연결 오류: {str(e)}"


# ============================================================================
# 클라우드 중계소(survey_responses) 폴링 -> 로컬 저장 -> 클라우드 즉시 삭제(휘발)
# ============================================================================
def poll_and_flush_cloud_buffer(cfg: Dict[str, str]) -> Tuple[int, int, str]:
    """
    Supabase의 survey_responses 테이블에서 새 응답을 모두 가져와 로컬 inbox_raw 폴더에
    JSON/CSV로 저장한 뒤, 클라우드 원본 데이터는 즉시 DELETE(휘발 처리)합니다.
    테이블 컬럼 구조: id, created_at, chart_id, survey_type, scores, raw_answers
    """
    if not is_supabase_configured(cfg):
        return 0, 0, "Supabase 설정이 아직 완료되지 않았습니다."

    base_dir, inbox_dir = ensure_directories(cfg["LOCAL_SAVE_DIR"])
    url = cfg["SUPABASE_URL"]
    key = cfg["SUPABASE_ANON_KEY"]
    headers = supabase_headers(key)

    try:
        fetch_url = f"{url}/rest/v1/survey_responses?select=*&order=created_at.asc"
        resp = requests.get(fetch_url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return 0, 0, f"클라우드 조회 실패 (HTTP {resp.status_code}): {resp.text[:150]}"

        rows = resp.json()
        if not rows:
            return 0, 0, "클라우드 중계소(survey_responses)에 대기 중인 새 설문이 없습니다 (잔여 데이터 0건)."

        downloaded_count = 0
        deleted_count = 0
        csv_path = base_dir / "survey_received_log.csv"
        csv_exists = csv_path.exists()

        for row in rows:
            row_id = row.get("id")
            row_id_str = str(row_id) if row_id is not None else ""
            chart_id = str(row.get("chart_id", "unknown")).strip()
            survey_type = str(row.get("survey_type", "UNKNOWN")).strip()
            created_at = str(row.get("created_at", datetime.now().isoformat()))

            scores_data = row.get("scores", {})
            if isinstance(scores_data, str):
                try:
                    scores_data = json.loads(scores_data)
                except Exception:
                    scores_data = {"summary_text": scores_data}

            raw_answers_data = row.get("raw_answers", {})
            if isinstance(raw_answers_data, str):
                try:
                    raw_answers_data = json.loads(raw_answers_data)
                except Exception:
                    raw_answers_data = {"raw_text": raw_answers_data}

            # 요약 문자열 추출
            score_summary = ""
            if isinstance(scores_data, dict):
                score_summary = str(scores_data.get("summary_text", "")).strip()
            if not score_summary:
                score_summary = json.dumps(scores_data, ensure_ascii=False)[:120]

            # 1) 로컬 inbox_raw 폴더에 JSON 저장
            safe_chart = re.sub(r'[\\/:*?"<>|]', "_", chart_id)
            ts_compact = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
            local_record = {
                "relay_id": row_id,
                "received_at": datetime.now().isoformat(),
                "created_at": created_at,
                "chart_id": chart_id,
                "survey_type": survey_type,
                "score_summary": score_summary,
                "scores": scores_data,
                "raw_answers": raw_answers_data,
                "patient_name": "",
                "visit_round": "1차",
                "matched_file": "",
                "raw_payload": {
                    "submitted_at": created_at,
                    "chart_id": chart_id,
                    "survey_type": survey_type,
                    "scores": scores_data,
                    "raw_answers": raw_answers_data,
                },
            }
            json_file = inbox_dir / f"inbox_{ts_compact}_chart-{safe_chart}_id-{row_id_str}.json"
            json_file.write_text(json.dumps(local_record, ensure_ascii=False, indent=2), encoding="utf-8")

            # 2) 로컬 누적 CSV 로그에도 한 줄 기록
            with open(csv_path, mode="a", newline="", encoding="utf-8-sig") as cf:
                writer = csv.writer(cf)
                if not csv_exists:
                    writer.writerow(["수령일시", "제출일시", "차트번호", "설문종류", "채점요약(scores)", "문항응답배열(raw_answers)", "원본JSON파일명"])
                    csv_exists = True
                writer.writerow([
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    created_at[:19].replace("T", " "),
                    chart_id,
                    survey_type,
                    score_summary,
                    json.dumps(raw_answers_data, ensure_ascii=False),
                    json_file.name,
                ])

            downloaded_count += 1

            # 3) 로컬 파일 생성 확인 직후 클라우드 원본 즉시 DELETE (휘발 처리!)
            if json_file.exists() and row_id is not None:
                del_url = f"{url}/rest/v1/survey_responses?id=eq.{row_id}"
                del_resp = requests.delete(del_url, headers=headers, timeout=8)
                if del_resp.status_code in (200, 204):
                    deleted_count += 1

        return (
            downloaded_count,
            deleted_count,
            f"✅ 새 설문 {downloaded_count}건 로컬 다운로드 완료 및 클라우드(survey_responses) 원본 {deleted_count}건 즉시 삭제(휘발) 완료!",
        )
    except Exception as e:
        return 0, 0, f"폴링/삭제 중 오류 발생: {str(e)}"


# ============================================================================
# 모의(샘플) 설문 생성기 (Supabase 설정 전에도 즉시 테스트 가능)
# ============================================================================
def create_sample_inbox_record(cfg: Dict[str, str]) -> Path:
    _, inbox_dir = ensure_directories(cfg["LOCAL_SAVE_DIR"])
    chart_id = str(datetime.now().strftime("%m%d%H"))
    sample_surveys = [
        evaluate_survey_response("BAI", [1, 2, 1, 2, 2, 1, 3, 1, 1, 2, 2, 1, 1, 0, 2, 1, 2, 2, 0, 1, 1]),
        evaluate_survey_response("PHQ9", [2, 2, 3, 1, 1, 2, 2, 1, 2]),  # 9번 문항 2점 포함 (주의 문항 하이라이트 테스트용)
        evaluate_survey_response("ISI", [3, 2, 2, 3, 3, 2, 3]),
    ]
    summary_text = " | ".join(f"{s['short_title']}: {s['total_score']}/{s['max_score']}점({s['severity']})" for s in sample_surveys)
    now_iso = datetime.now().isoformat()
    scores_obj = {
        "submitted_at": now_iso,
        "summary_text": summary_text,
        "surveys": sample_surveys,
    }
    raw_answers_obj = {
        "by_survey": {
            s["survey_code"]: {"answers": s["answers"]} for s in sample_surveys
        }
    }
    sample_record = {
        "relay_id": f"sample-{int(time.time())}",
        "received_at": now_iso,
        "created_at": now_iso,
        "chart_id": chart_id,
        "survey_type": "BAI,PHQ9,ISI",
        "score_summary": summary_text,
        "scores": scores_obj,
        "raw_answers": raw_answers_obj,
        "patient_name": "",
        "visit_round": "1차",
        "matched_file": "",
        "raw_payload": {
            "submitted_at": now_iso,
            "chart_id": chart_id,
            "survey_type": "BAI,PHQ9,ISI",
            "scores": scores_obj,
            "raw_answers": raw_answers_obj,
            "surveys": sample_surveys,
        },
    }
    ts_compact = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = inbox_dir / f"inbox_{ts_compact}_chart-{chart_id}_sample.json"
    out_file.write_text(json.dumps(sample_record, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_file


def load_local_inbox_records(cfg: Dict[str, str]) -> List[Dict[str, Any]]:
    _, inbox_dir = ensure_directories(cfg["LOCAL_SAVE_DIR"])
    files = sorted(inbox_dir.glob("inbox_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    records = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data["_file_path"] = str(f)
            data["_file_name"] = f.name
            records.append(data)
        except Exception:
            continue
    return records


# ============================================================================
# 메인 UI 구성
# ============================================================================
cfg = get_config()

# 앱 시작 시(세션 최초 1회 + 수동 갱신 시) 자동으로 Supabase Keep-Alive Ping 발송
if "keepalive_done" not in st.session_state:
    ok, msg = send_supabase_keepalive_ping(cfg)
    st.session_state["keepalive_ok"] = ok
    st.session_state["keepalive_msg"] = msg
    st.session_state["keepalive_done"] = True

# 커스텀 CSS
st.markdown(
    """
    <style>
    .status-banner {
        padding: 12px 18px;
        border-radius: 12px;
        margin-bottom: 16px;
        font-weight: 700;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .status-ok {
        background-color: #ecfdf5;
        border: 1.5px solid #10b981;
        color: #065f46;
    }
    .status-warn {
        background-color: #fffbeb;
        border: 1.5px solid #f59e0b;
        color: #92400e;
    }
    .critical-alert-box {
        background-color: #fef2f2;
        border: 2px solid #ef4444;
        border-radius: 12px;
        padding: 14px 18px;
        color: #991b1b;
        margin-bottom: 12px;
    }
    .warning-item-card {
        background-color: #fff7ed;
        border-left: 5px solid #f97316;
        padding: 10px 14px;
        border-radius: 8px;
        margin-bottom: 8px;
        color: #9a3412;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================================
# 좌측 사이드바: 로컬 저장 폴더 설정 & Supabase 연동 관리
# ============================================================================
with st.sidebar:
    st.markdown("## 🌿 원내 설문 수신기 설정")
    st.caption("클라우드 개인정보 Zero · 즉시 휘발(Stateless) 시스템")

    st.markdown("### 📁 1. 최종 결과 저장 폴더 지정")
    st.caption("원내 공유폴더(예: `\\\\Server\\설문`) 또는 원드라이브 폴더 경로를 입력하세요.")
    new_save_dir = st.text_input("로컬 저장 폴더 경로", value=cfg["LOCAL_SAVE_DIR"])

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        if st.button("💾 경로 저장", use_container_width=True):
            try:
                ensure_directories(new_save_dir)
                if not ENV_PATH.exists():
                    ENV_PATH.write_text("", encoding="utf-8")
                set_key(str(ENV_PATH), "LOCAL_SAVE_DIR", new_save_dir)
                st.success("저장 경로가 반영되었습니다!")
                st.rerun()
            except Exception as e:
                st.error(f"폴더 생성 실패: {e}")
    with col_s2:
        if st.button("📂 폴더 열기", use_container_width=True):
            try:
                base_dir, _ = ensure_directories(cfg["LOCAL_SAVE_DIR"])
                os.startfile(str(base_dir))
            except Exception as e:
                st.warning(f"탐색기 열기 오류: {e}")

    st.divider()

    st.markdown("### ☁️ 2. Supabase 중계소 설정")
    with st.expander("🔑 URL 및 anon Key 설정 (.env 연동)", expanded=not is_supabase_configured(cfg)):
        sb_url_in = st.text_input("SUPABASE_URL", value=cfg["SUPABASE_URL"], placeholder="https://xxxx.supabase.co")
        sb_key_in = st.text_input("SUPABASE_ANON_KEY", value=cfg["SUPABASE_ANON_KEY"], type="password")
        web_url_in = st.text_input("환자용 웹 배포 주소 (Cloudflare Pages)", value=cfg["PATIENT_WEB_URL"])

        if st.button("✅ 설정 저장 및 환자용 HTML 자동 갱신", use_container_width=True, type="primary"):
            if not ENV_PATH.exists():
                ENV_PATH.write_text("", encoding="utf-8")
            set_key(str(ENV_PATH), "SUPABASE_URL", sb_url_in.strip().rstrip("/"))
            set_key(str(ENV_PATH), "SUPABASE_ANON_KEY", sb_key_in.strip())
            set_key(str(ENV_PATH), "PATIENT_WEB_URL", web_url_in.strip().rstrip("/"))
            # 환자용 frontend/index.html 에도 자동으로 키 반영
            build_and_save_frontend()
            cfg = get_config()
            ok, msg = send_supabase_keepalive_ping(cfg)
            st.session_state["keepalive_ok"] = ok
            st.session_state["keepalive_msg"] = msg
            st.success("`.env` 저장 및 `frontend/index.html` 갱신 완료!")
            st.rerun()

    if st.button("💓 Supabase 활성 유지 Ping 수동 전송", use_container_width=True):
        ok, msg = send_supabase_keepalive_ping(cfg)
        st.session_state["keepalive_ok"] = ok
        st.session_state["keepalive_msg"] = msg
        if ok:
            st.toast("Supabase 활성 유지 Ping 완료!", icon="🟢")
        else:
            st.toast(msg, icon="⚠️")

    st.divider()
    st.markdown("### 🧪 테스트 도구")
    if st.button("➕ 샘플 환자 설문 생성 (모의 수신)", use_container_width=True):
        sample_file = create_sample_inbox_record(cfg)
        st.toast(f"샘플 설문 수신 완료: {sample_file.name}", icon="✅")
        st.rerun()


# ============================================================================
# 상단 헤더 및 Supabase Health Check 배너
# ============================================================================
st.markdown("## 🏥 해아림한의원 무상태(Stateless) 설문 진료실 대시보드")

if st.session_state.get("keepalive_ok"):
    st.markdown(
        f"""
        <div class="status-banner status-ok">
            <span>🟢 <strong>Supabase 클라우드 중계소 활성 상태</strong> — {st.session_state.get('keepalive_msg')}</span>
            <span style="font-size:0.85rem;">7일 미사용 일시정지(Pause) 자동 방지 작동 중</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f"""
        <div class="status-banner status-warn">
            <span>🟡 <strong>Supabase 연동 안내:</strong> {st.session_state.get('keepalive_msg')}</span>
            <span style="font-size:0.85rem;">좌측 사이드바에서 [샘플 환자 설문 생성]으로 모든 기능을 바로 체험할 수 있습니다</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

# 메인 탭 구성
tab_receiver, tab_archive, tab_kakao, tab_guide = st.tabs([
    "📥 1. 설문 수신 및 진료실 뷰어 (이름 매칭·EMR 복사)",
    "🗂️ 2. 저장된 완료 차트 보관함 (.html/.json)",
    "💬 3. 카톡 설문 링크 생성기 & 배포 파일",
    "🛠️ 4. Supabase 1분 초기 설정 가이드 (SQL 포함)",
])

# ============================================================================
# [탭 1] 설문 수신 및 진료실 뷰어
# ============================================================================
with tab_receiver:
    top_c1, top_c2, top_c3 = st.columns([2.2, 1.3, 1.5])
    with top_c1:
        if st.button("🔄 클라우드 새 설문 수령 (조회 후 클라우드 원본 즉시 삭제)", type="primary", use_container_width=True):
            dl_cnt, del_cnt, status_msg = poll_and_flush_cloud_buffer(cfg)
            st.session_state["last_poll_msg"] = status_msg
            if dl_cnt > 0:
                st.toast(status_msg, icon="🎉")
            else:
                st.toast(status_msg, icon="ℹ️")
    with top_c2:
        auto_poll = st.toggle("⏱️ 15초마다 자동 수령", value=False)
    with top_c3:
        st.caption(f"📁 현재 저장 경로:\n`{cfg['LOCAL_SAVE_DIR']}`")

    if st.session_state.get("last_poll_msg"):
        st.info(st.session_state["last_poll_msg"])

    inbox_records = load_local_inbox_records(cfg)

    if not inbox_records:
        st.warning(
            "현재 로컬 수신함에 설문 데이터가 없습니다. 상단의 **[🔄 클라우드 새 설문 수령]** 버튼을 누르시거나, "
            "좌측 사이드바 하단의 **[➕ 샘플 환자 설문 생성]** 버튼을 눌러 진료실 화면을 바로 테스트해 보세요!"
        )
    else:
        st.markdown("---")
        left_col, right_col = st.columns([1.15, 2.35], gap="large")

        with left_col:
            st.markdown(f"### 📋 수신된 설문 목록 ({len(inbox_records)}건)")
            filter_unmatched = st.checkbox("이름 미매칭(신규) 설문만 보기", value=False)
            filtered_records = [
                r for r in inbox_records
                if (not filter_unmatched) or (not r.get("patient_name"))
            ]

            if not filtered_records:
                st.info("조건에 해당하는 설문이 없습니다.")
                selected_record = None
            else:
                options_labels = []
                for idx, rec in enumerate(filtered_records):
                    c_id = rec.get("chart_id", "-")
                    p_name = rec.get("patient_name", "").strip()
                    v_round = rec.get("visit_round", "1차")
                    s_type = rec.get("survey_type", "")
                    dt_short = rec.get("created_at", "")[:16].replace("T", " ")
                    status_tag = f"✅ {p_name}({v_round})" if p_name else "🆕 이름 미매칭"
                    options_labels.append(f"[{status_tag}] 차트:{c_id} | {s_type} ({dt_short})")

                selected_idx = st.radio(
                    "조회할 환자 설문 선택",
                    options=range(len(filtered_records)),
                    format_func=lambda i: options_labels[i],
                    label_visibility="collapsed",
                )
                selected_record = filtered_records[selected_idx]

                # 선택된 설문 환자 이름 매칭 및 최종 파일 저장 폼
                st.markdown("#### 👤 환자 이름 매칭 및 최종 결과 저장")
                st.caption("환자 이름은 원내 PC에만 저장되며 클라우드로 절대 전송되지 않습니다.")

                with st.form("match_save_form", clear_on_submit=False):
                    f_name = st.text_input(
                        "환자 이름 (필수)",
                        value=selected_record.get("patient_name", ""),
                        placeholder="예: 홍길동",
                    )
                    col_r1, col_r2 = st.columns(2)
                    with col_r1:
                        f_round = st.text_input(
                            "검사 차수",
                            value=selected_record.get("visit_round", "1차"),
                            placeholder="예: 1차, 초진, 2차",
                        )
                    with col_r2:
                        f_chart = st.text_input(
                            "차트번호 확인/수정",
                            value=selected_record.get("chart_id", ""),
                        )
                    f_memo = st.text_area(
                        "진료실 메모 (선택, EMR 복사 및 HTML에 포함)",
                        value=selected_record.get("clinician_memo", ""),
                        height=68,
                    )

                    save_submitted = st.form_submit_button(
                        "💾 최종 결과 파일 저장 (이름-차수-차트번호_설문.html)",
                        type="primary",
                        use_container_width=True,
                    )

                    if save_submitted:
                        clean_name = re.sub(r'[\\/:*?"<>|]', "", f_name.strip())
                        clean_round = re.sub(r'[\\/:*?"<>|]', "", f_round.strip() or "1차")
                        clean_chart = re.sub(r'[\\/:*?"<>|]', "", f_chart.strip() or "0000")

                        if not clean_name:
                            st.error("환자 이름을 입력해 주세요!")
                        else:
                            base_dir, _ = ensure_directories(cfg["LOCAL_SAVE_DIR"])
                            base_filename = f"{clean_name}-{clean_round}-{clean_chart}_설문"
                            html_out_path = base_dir / f"{base_filename}.html"
                            json_out_path = base_dir / f"{base_filename}.json"

                            raw_payload = selected_record.get("raw_payload", {})
                            surveys_eval = normalize_payload_surveys(raw_payload, selected_record.get("survey_type", ""))
                            emr_txt = build_emr_chart_text(
                                chart_id=clean_chart,
                                patient_name=clean_name,
                                visit_round=clean_round,
                                submitted_at=selected_record.get("created_at", ""),
                                surveys=surveys_eval,
                                clinician_memo=f_memo,
                            )
                            html_report = generate_standalone_html_report(
                                chart_id=clean_chart,
                                patient_name=clean_name,
                                visit_round=clean_round,
                                submitted_at=selected_record.get("created_at", ""),
                                surveys=surveys_eval,
                                emr_text=emr_txt,
                                clinician_memo=f_memo,
                            )

                            # 1) HTML 리포트 파일 저장
                            html_out_path.write_text(html_report, encoding="utf-8")

                            # 2) 원본 레코드 업데이트 및 최종 JSON 저장
                            selected_record["patient_name"] = clean_name
                            selected_record["visit_round"] = clean_round
                            selected_record["chart_id"] = clean_chart
                            selected_record["clinician_memo"] = f_memo
                            selected_record["matched_file"] = str(html_out_path)

                            json_out_path.write_text(
                                json.dumps(selected_record, ensure_ascii=False, indent=2),
                                encoding="utf-8",
                            )
                            # inbox_raw 원본 파일도 매칭 상태 업데이트
                            inbox_file_path = Path(selected_record["_file_path"])
                            if inbox_file_path.exists():
                                inbox_file_path.write_text(
                                    json.dumps(selected_record, ensure_ascii=False, indent=2),
                                    encoding="utf-8",
                                )

                            st.success(f"저장 완료!\n- `{html_out_path.name}`\n- `{json_out_path.name}`")
                            st.rerun()

                # 수신함에서 삭제 버튼
                if st.button("🗑️ 이 수신 기록 삭제", use_container_width=True):
                    p = Path(selected_record["_file_path"])
                    if p.exists():
                        p.unlink()
                    st.rerun()

        # 우측 컬럼: 임상 시각화 대시보드 (a. 바 차트, b. 주의 문항 하이라이트, c. EMR 원클릭 복사)
        with right_col:
            if selected_record:
                raw_payload = selected_record.get("raw_payload", {})
                surveys_eval = normalize_payload_surveys(raw_payload, selected_record.get("survey_type", ""))
                p_name_disp = selected_record.get("patient_name") or "이름 미입력(좌측에서 매칭)"
                v_round_disp = selected_record.get("visit_round", "1차")
                c_id_disp = selected_record.get("chart_id", "-")
                dt_disp = selected_record.get("created_at", "")[:19].replace("T", " ")

                st.markdown(
                    f"### 🩺 설문 임상 분석 결과 — **{p_name_disp}** ({v_round_disp}) | 차트번호: `{c_id_disp}`"
                )
                st.caption(f"제출 일시: {dt_disp} | 설문 구성: `{selected_record.get('survey_type')}`")

                # --------------------------------------------------------------
                # [기능 b] 주의 문항 하이라이트 (PHQ-9 9번 자살사고 및 2점 이상 핵심 증상)
                # --------------------------------------------------------------
                all_alerts = []
                critical_suicide_alerts = []
                for s in surveys_eval:
                    s_short = s.get("short_title", s.get("survey_code", ""))
                    for al in s.get("alerts", []):
                        item_entry = (s_short, s.get("survey_code"), al)
                        all_alerts.append(item_entry)
                        if s.get("survey_code") == "PHQ9" and al.get("item_no") == 9:
                            critical_suicide_alerts.append(item_entry)

                if critical_suicide_alerts:
                    for s_short, _, al in critical_suicide_alerts:
                        st.markdown(
                            f"""
                            <div class="critical-alert-box">
                                <div style="font-size:1.08rem; font-weight:900; margin-bottom:4px;">
                                    🚨 [최우선 임상 경보] PHQ-9 9번 문항(자살/자해 사고) 양성 반응!
                                </div>
                                <div>• 문항: <strong>{al.get('question')}</strong></div>
                                <div>• 환자 응답: <span style="background:#dc2626; color:#fff; padding:2px 8px; border-radius:6px; font-weight:800;">{al.get('label')} ({al.get('score')}점)</span></div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                # --------------------------------------------------------------
                # [기능 a] 척도별 점수 바 차트 및 임상적 절단점(Cut-off) 기준 중증도 색상 표시
                # --------------------------------------------------------------
                st.markdown("#### 📊 1. 척도별 총점 및 임상 절단점(Cut-off) 중증도")

                # 상단 요약 카드
                metric_cols = st.columns(max(len(surveys_eval), 1))
                for idx, s in enumerate(surveys_eval):
                    with metric_cols[idx]:
                        color = s.get("color", "#10b981")
                        st.markdown(
                            f"""
                            <div style="border:2px solid {color}; background:{color}12; border-radius:12px; padding:12px 14px; margin-bottom:10px;">
                                <div style="font-size:0.85rem; font-weight:700; color:#334155;">{s.get('title')}</div>
                                <div style="font-size:1.65rem; font-weight:900; color:{color}; margin:4px 0;">
                                    {s.get('total_score')} <span style="font-size:0.9rem; color:#64748b; font-weight:600;">/ {s.get('max_score')}점</span>
                                </div>
                                <div style="display:inline-block; background:{color}; color:#fff; font-size:0.78rem; font-weight:800; padding:2px 9px; border-radius:99px;">
                                    {s.get('severity')}
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                # Plotly 가로형 점수 비율 바 차트 (중증도 색상 반영)
                chart_labels = []
                chart_pcts = []
                chart_texts = []
                chart_colors = []

                for s in reversed(surveys_eval):
                    total = s.get("total_score", 0)
                    max_s = max(s.get("max_score", 1), 1)
                    pct = min(100.0, round((total / max_s) * 100, 1))
                    chart_labels.append(s.get("short_title", s.get("title", "")))
                    chart_pcts.append(pct)
                    chart_texts.append(f"{total}/{max_s}점 ({s.get('severity')})")
                    chart_colors.append(s.get("color", "#10b981"))

                fig = go.Figure(
                    go.Bar(
                        x=chart_pcts,
                        y=chart_labels,
                        orientation="h",
                        text=chart_texts,
                        textposition="auto",
                        marker=dict(color=chart_colors, line=dict(color="#ffffff", width=1.5)),
                        hovertemplate="%{y}: %{text} (만점 대비 %{x}%)<extra></extra>",
                    )
                )
                fig.update_layout(
                    height=max(180, len(surveys_eval) * 62 + 50),
                    margin=dict(l=10, r=20, t=10, b=20),
                    xaxis=dict(title="만점 대비 백분율 (%)", range=[0, 105], showgrid=True, gridcolor="#e2e8f0"),
                    yaxis=dict(title=""),
                    plot_bgcolor="#ffffff",
                    paper_bgcolor="#ffffff",
                    font=dict(family="Pretendard, Malgun Gothic, sans-serif", size=13),
                )
                st.plotly_chart(fig, use_container_width=True)

                # --------------------------------------------------------------
                # 주의 문항 리스트 상세 표시
                # --------------------------------------------------------------
                st.markdown("#### 🚨 2. 주의 문항 하이라이트 (2점 이상 핵심 증상)")
                if not all_alerts:
                    st.success("✓ 2점 이상 체크된 주의 문항이 없습니다.")
                else:
                    for s_short, s_code, al in all_alerts:
                        is_crit = al.get("is_critical", False)
                        bg_color = "#fef2f2" if is_crit else "#fff7ed"
                        border_color = "#ef4444" if is_crit else "#f97316"
                        text_color = "#991b1b" if is_crit else "#9a3412"
                        badge_txt = "🚨 핵심위험" if is_crit else "⚠️ 2점+ 주의"
                        st.markdown(
                            f"""
                            <div style="background:{bg_color}; border-left:5px solid {border_color}; padding:10px 14px; border-radius:8px; margin-bottom:7px; color:{text_color}; display:flex; justify-content:space-between; align-items:center; gap:10px;">
                                <div>
                                    <span style="font-weight:800; background:{border_color}; color:#fff; padding:2px 7px; border-radius:5px; font-size:0.76rem; margin-right:6px;">{badge_txt}</span>
                                    <strong>[{s_short} #{al.get('item_no')}]</strong> {al.get('question')}
                                </div>
                                <div style="font-weight:800; white-space:nowrap;">
                                    {al.get('label')} ({al.get('score')}점)
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                # --------------------------------------------------------------
                # [기능 c] 전자차트(EMR) 기록용 텍스트 원클릭 복사 블록
                # --------------------------------------------------------------
                st.markdown("#### 📋 3. [차트 기록용 텍스트 원클릭 복사] (EMR 붙여넣기용)")
                emr_text_block = build_emr_chart_text(
                    chart_id=c_id_disp,
                    patient_name=selected_record.get("patient_name", ""),
                    visit_round=v_round_disp,
                    submitted_at=selected_record.get("created_at", ""),
                    surveys=surveys_eval,
                    clinician_memo=selected_record.get("clinician_memo", ""),
                )

                # 원클릭 클립보드 복사 HTML 버튼 + st.code 블록 동시 제공
                escaped_js_text = json.dumps(emr_text_block, ensure_ascii=False)
                components.html(
                    f"""
                    <div style="display:flex; align-items:center; gap:10px; font-family:sans-serif;">
                        <button id="emrCopyBtn" onclick='navigator.clipboard.writeText({escaped_js_text}).then(() => {{
                            const b = document.getElementById("emrCopyBtn");
                            b.innerText = "✅ 클립보드에 복사되었습니다! (전자차트에서 Ctrl+V)";
                            b.style.background = "#15803d";
                            setTimeout(() => {{
                                b.innerText = "📋 차트 기록용 텍스트 원클릭 복사하기";
                                b.style.background = "#0f766e";
                            }}, 2500);
                        }})'
                        style="background:#0f766e; color:#ffffff; border:none; border-radius:10px; padding:11px 20px; font-size:0.95rem; font-weight:800; cursor:pointer; box-shadow:0 2px 6px rgba(15,118,110,0.25);">
                            📋 차트 기록용 텍스트 원클릭 복사하기
                        </button>
                        <span style="font-size:0.84rem; color:#475569;">우측 상단 복사 아이콘 또는 이 버튼을 클릭한 뒤 전자차트(EMR)에 바로 붙여넣으세요.</span>
                    </div>
                    """,
                    height=52,
                )
                st.code(emr_text_block, language="text")

                # 문항별 원본 응답 상세 아코디언
                with st.expander("🔍 문항별 전체 응답 내역 및 원본 배열(JSON) 보기", expanded=False):
                    for s in surveys_eval:
                        st.markdown(f"**■ {s.get('title')}** — 총점: `{s.get('total_score')}/{s.get('max_score')}점` ({s.get('severity')})")
                        if s.get("is_checklist"):
                            for sec_sum in s.get("section_summaries", []):
                                st.write(f"- {sec_sum.get('summary_text')}")
                        else:
                            spec = SURVEY_CATALOG.get(s.get("survey_code", ""), {})
                            questions = spec.get("questions", [])
                            answers = s.get("answers", [])
                            rows_data = []
                            for idx, sc in enumerate(answers):
                                opts = spec.get("custom_options_by_index", {}).get(idx, spec.get("options", []))
                                opt_lbl = next((o["label"] for o in opts if o["value"] == sc), f"{sc}점")
                                rows_data.append({
                                    "문항번호": idx + 1,
                                    "문항 내용": questions[idx] if idx < len(questions) else f"문항 {idx+1}",
                                    "환자 선택": opt_lbl,
                                    "점수": sc,
                                })
                            st.dataframe(pd.DataFrame(rows_data), use_container_width=True, hide_index=True)

    # 자동 폴링 켜져 있을 때 주기적 새로고침
    if auto_poll:
        time.sleep(15)
        poll_and_flush_cloud_buffer(cfg)
        st.rerun()


# ============================================================================
# [탭 2] 저장된 완료 차트 보관함 (.html / .json)
# ============================================================================
with tab_archive:
    st.markdown("### 🗂️ 로컬 폴더에 최종 저장된 설문 리포트 (`이름-차수-차트번호_설문.html`)")
    base_dir, _ = ensure_directories(cfg["LOCAL_SAVE_DIR"])
    html_files = sorted(base_dir.glob("*_설문.html"), key=lambda p: p.stat().st_mtime, reverse=True)

    st.info(f"저장 위치: `{base_dir}` (총 {len(html_files)}건의 완료된 설문 리포트가 보관 중입니다)")

    if not html_files:
        st.caption("아직 이름 매칭 후 최종 저장된 `.html` 파일이 없습니다. [탭 1]에서 환자 이름을 입력하고 저장해 보세요.")
    else:
        search_q = st.text_input("🔍 환자 이름 또는 차트번호로 검색", placeholder="예: 홍길동 또는 10293")
        filtered_htmls = [f for f in html_files if search_q.strip() in f.name] if search_q.strip() else html_files

        for hf in filtered_htmls:
            c1, c2, c3, c4 = st.columns([3, 1.5, 1.2, 1.2])
            mtime_str = datetime.fromtimestamp(hf.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            with c1:
                st.markdown(f"📄 **`{hf.name}`**")
            with c2:
                st.caption(f"저장일시: {mtime_str}")
            with c3:
                if st.button("🌐 브라우저로 열기", key=f"open_{hf.name}", use_container_width=True):
                    os.startfile(str(hf))
            with c4:
                st.download_button(
                    "📥 HTML 다운로드",
                    data=hf.read_bytes(),
                    file_name=hf.name,
                    mime="text/html",
                    key=f"dl_{hf.name}",
                    use_container_width=True,
                )


# ============================================================================
# [탭 3] 카톡 설문 링크 생성기 & 환자용 배포 파일 다운로드
# ============================================================================
with tab_kakao:
    st.markdown("### 💬 카카오톡 발송용 환자 설문 링크 생성기")
    st.caption("차트번호와 설문 종류만 지정하여 카톡으로 전송합니다. (환자는 로그인이나 이름 입력 없이 즉시 응답)")

    k_col1, k_col2 = st.columns([1.2, 1.8], gap="large")
    with k_col1:
        k_chart_id = st.text_input("환자 차트번호 입력", value="10293", placeholder="예: 10293")
        preset_choice = st.selectbox(
            "빠른 설문 세트 선택",
            options=["직접 선택"] + list(SURVEY_PRESETS.keys()),
            index=1,
        )

        default_codes = SURVEY_PRESETS.get(preset_choice, ["BAI", "PHQ9", "ISI"])
        selected_codes = st.multiselect(
            "포함할 설문 종류 (?type= 파라미터)",
            options=list(SURVEY_CATALOG.keys()),
            default=default_codes,
            format_func=lambda c: f"{c} - {SURVEY_CATALOG[c]['title']}",
        )

    with k_col2:
        base_web = cfg["PATIENT_WEB_URL"].rstrip("/")
        type_str = ",".join(selected_codes) if selected_codes else "BAI,PHQ9,ISI"
        query_str = urlencode({"id": k_chart_id.strip(), "type": type_str})
        # 쉼표는 그대로 보이게 처리
        query_str = f"id={k_chart_id.strip()}&type={type_str}"
        final_url = f"{base_web}/?{query_str}"

        survey_names = ", ".join(SURVEY_CATALOG[c]["short_title"] for c in selected_codes)
        kakao_msg = (
            f"[해아림한의원 진료 전 설문 안내]\n"
            f"안녕하세요. 정확한 진료를 위해 내원/진료 전 아래 링크를 눌러 자가보고 설문을 작성해 주세요.\n\n"
            f"• 차트번호: {k_chart_id.strip()}\n"
            f"• 설문항목: {survey_names}\n"
            f"• 설문링크: {final_url}\n\n"
            f"※ 개인정보 보호를 위해 성함이나 연락처는 입력하지 않으셔도 됩니다."
        )

        st.markdown("#### 🔗 생성된 설문 URL")
        st.code(final_url, language="text")

        st.markdown("#### 💬 카카오톡 안내 문구 (복사해서 카톡에 붙여넣기)")
        st.code(kakao_msg, language="text")

    st.divider()
    st.markdown("### 🚀 Cloudflare Pages 배포용 단일 HTML 파일 (`frontend/index.html`)")
    st.write(
        "좌측 사이드바 또는 `.env`에 입력하신 Supabase URL과 anon Key가 자동으로 주입된 환자용 모바일 웹 파일입니다. "
        "Cloudflare Pages에서 `frontend` 폴더(또는 아래 `index.html` 파일)를 업로드하시면 바로 작동합니다."
    )
    frontend_path = build_and_save_frontend()
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        st.download_button(
            "📥 환자용 모바일 웹 (index.html) 다운로드",
            data=frontend_path.read_bytes(),
            file_name="index.html",
            mime="text/html",
            type="primary",
            use_container_width=True,
        )
    with col_f2:
        if st.button("🖥️ 내 PC 브라우저에서 환자용 모바일 웹 미리보기", use_container_width=True):
            os.startfile(str(frontend_path))


# ============================================================================
# [탭 4] Supabase 1분 초기 설정 가이드 (SQL 포함)
# ============================================================================
with tab_guide:
    st.markdown("### 🛠️ Supabase 처음 사용자를 위한 2단계 설정 안내")
    st.markdown(
        """
        #### 1단계: Supabase의 `[SQL Editor]`에 복사해서 붙여넣고 `Run`만 누르기
        1. [Supabase 웹사이트](https://supabase.com)에 로그인 후 새 프로젝트(무료 플랜)를 만듭니다.
        2. 좌측 메뉴에서 **`SQL Editor`** 아이콘을 클릭한 뒤 **`+ New query`** 버튼을 누릅니다.
        3. 아래 SQL 블록 우측 상단의 **복사 아이콘**을 눌러 전체 복사한 뒤 붙여넣고, 우측 하단 초록색 **`Run`** 버튼을 누르면 **설문 중계 테이블(`survey_relay`), 7일 일시정지 방지 테이블(`system_heartbeat`), 권한(RLS) 정책이 한 번에 생성**됩니다.
        """
    )
    sql_path = Path(__file__).parent / "supabase_setup.sql"
    if sql_path.exists():
        st.code(sql_path.read_text(encoding="utf-8"), language="sql")

    st.markdown(
        """
        ---
        #### 2단계: Supabase에서 `URL`과 `anon Key`를 찾아 내 PC의 `.env`에 넣기
        1. Supabase 프로젝트 좌측 하단의 **⚙️ `Project Settings` (톱니바퀴 아이콘)** → **`API`** (또는 **`Data API`**) 메뉴를 클릭합니다.
        2. 화면 상단 **`Project URL`** 항목에 있는 `https://xxxxxxxxxxxx.supabase.co` 주소를 복사합니다.
        3. 바로 아래 **`Project API keys`** 항목에서 **`anon` (`public`)** 키 (`eyJhbGci...`로 시작하는 긴 문자열)를 복사합니다.
        4. 본 대시보드 **좌측 사이드바의 `[2. Supabase 중계소 설정]`** 입력란에 두 값을 붙여넣고 **[✅ 설정 저장 및 환자용 HTML 자동 갱신]** 버튼을 누르시거나, 작업 폴더의 `.env` 파일에 붙여넣으시면 모든 설정이 끝납니다!
        """
    )

