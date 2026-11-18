# -*- coding: utf-8 -*-
"""
원내 진료실 PC용:
1) 전자차트(EMR) 원클릭 복사용 텍스트 블록 생성기
2) 최종 로컬 보관용 HTML 리포트 생성기 (파일명 규칙: 이름-차수-차트번호_설문.html)
"""

import html
import json
from datetime import datetime
from typing import Dict, Any, List
from survey_definitions import SURVEY_CATALOG, evaluate_survey_response


def normalize_payload_surveys(record_or_payload: Dict[str, Any], fallback_type: str = "") -> List[Dict[str, Any]]:
    """
    survey_responses 테이블의 (scores, raw_answers) 구조 또는 기존 raw_payload 구조에서
    설문 결과 리스트를 정규화하고 survey_definitions.evaluate_survey_response 로 채점/보완합니다.
    """
    normalized = []

    # 1) survey_responses 테이블의 scores + raw_answers 구조 처리
    scores_obj = record_or_payload.get("scores")
    raw_answers_obj = record_or_payload.get("raw_answers")

    if isinstance(scores_obj, dict) or raw_answers_obj is not None:
        by_survey = {}
        if isinstance(raw_answers_obj, dict):
            if "by_survey" in raw_answers_obj and isinstance(raw_answers_obj["by_survey"], dict):
                by_survey = raw_answers_obj["by_survey"]
            elif "survey_code" in raw_answers_obj and "answers" in raw_answers_obj:
                by_survey[raw_answers_obj["survey_code"]] = raw_answers_obj

        surveys_in_scores = scores_obj.get("surveys", []) if isinstance(scores_obj, dict) else []
        if isinstance(surveys_in_scores, list) and len(surveys_in_scores) > 0:
            for s in surveys_in_scores:
                code = s.get("survey_code", "")
                raw_entry = by_survey.get(code, {})
                ans = raw_entry.get("answers", s.get("answers", []))
                # 만약 단일 설문이고 raw_answers_obj 자체가 리스트([0,1,2...])인 경우
                if not ans and isinstance(raw_answers_obj, list):
                    ans = raw_answers_obj
                meta_ans = raw_entry.get("meta_answers", s.get("meta_answers", {}))
                eval_res = evaluate_survey_response(code, ans, meta_ans)
                if "itemized_details" in raw_entry:
                    eval_res["itemized_details"] = raw_entry["itemized_details"]
                normalized.append(eval_res)
            return normalized

        # scores.surveys 가 없고 raw_answers 가 직접 배열이거나 코드별 딕셔너리인 경우
        if by_survey:
            for code, raw_entry in by_survey.items():
                ans = raw_entry.get("answers", raw_entry) if isinstance(raw_entry, dict) else raw_entry
                meta_ans = raw_entry.get("meta_answers", {}) if isinstance(raw_entry, dict) else {}
                normalized.append(evaluate_survey_response(code, ans, meta_ans))
            return normalized

        if isinstance(raw_answers_obj, list) and fallback_type:
            first_code = fallback_type.split(",")[0].strip().upper()
            normalized.append(evaluate_survey_response(first_code, raw_answers_obj, {}))
            return normalized

    # 2) 하위 호환: 기존 raw_payload.surveys 구조 처리
    surveys_raw = record_or_payload.get("surveys", [])
    if isinstance(surveys_raw, list) and len(surveys_raw) > 0:
        for s in surveys_raw:
            code = s.get("survey_code", "")
            ans = s.get("answers", [])
            meta_ans = s.get("meta_answers", {})
            eval_res = evaluate_survey_response(code, ans, meta_ans)
            if "itemized_details" in s:
                eval_res["itemized_details"] = s["itemized_details"]
            normalized.append(eval_res)
    elif fallback_type and "answers" in record_or_payload:
        eval_res = evaluate_survey_response(fallback_type, record_or_payload["answers"], record_or_payload.get("meta_answers", {}))
        normalized.append(eval_res)

    return normalized


def build_emr_chart_text(
    chart_id: str,
    patient_name: str,
    visit_round: str,
    submitted_at: str,
    surveys: List[Dict[str, Any]],
    clinician_memo: str = "",
) -> str:
    """
    전자차트(EMR) 및 타 검사 프로그램에 바로 붙여넣을 수 있는 텍스트 블록을 생성합니다.
    """
    dt_str = submitted_at[:16].replace("T", " ") if submitted_at else datetime.now().strftime("%Y-%m-%d %H:%M")
    header_name = f"{patient_name} ({visit_round})" if patient_name else f"미매칭 ({visit_round})"

    lines = [
        f"==========================================",
        f"[자기보고식 심리/신체 설문 결과]",
        f"• 환 자 명 : {header_name}  |  차트번호: {chart_id}",
        f"• 검사일시 : {dt_str}",
        f"------------------------------------------",
        f"[1. 척도별 총점 및 중증도 요약]",
    ]

    for s in surveys:
        title = s.get("title", s.get("survey_code", ""))
        total = s.get("total_score", 0)
        max_s = s.get("max_score", 0)
        sev = s.get("severity", "")
        if s.get("is_checklist"):
            lines.append(f"■ {title} : 총 {total}개 항목 체크 [{sev}]")
            meta = s.get("meta_answers") or {}
            meta_str = ", ".join(f"{k}:{v}" for k, v in meta.items() if v)
            if meta_str:
                lines.append(f"   - 기본문진: {meta_str}")
            for sec_sum in s.get("section_summaries", []):
                lines.append(f"   - {sec_sum.get('summary_text', '')}")
        else:
            lines.append(f"■ {title} : {total} / {max_s}점  ▶ [{sev}]")
            subscales = s.get("subscales") or {}
            if subscales:
                sub_str = " / ".join(f"{k}: {v}" for k, v in subscales.items())
                lines.append(f"   - 소척도: {sub_str}")
            ans_arr = s.get("answers", [])
            lines.append(f"   - 응답배열: {json.dumps(ans_arr, ensure_ascii=False)}")

    # 주의 문항 하이라이트 섹션
    all_alerts = []
    for s in surveys:
        for al in s.get("alerts", []):
            all_alerts.append((s.get("short_title", s.get("survey_code")), al))

    lines.append(f"------------------------------------------")
    lines.append(f"[2. 주의 문항 및 핵심 증상 (2점 이상 / 위험문항)]")
    if not all_alerts:
        lines.append("• 특이 주의 문항 없음 (모두 기준치 미만)")
    else:
        for s_title, al in all_alerts:
            prefix = "🚨[긴급주의]" if al.get("is_critical") else "⚠️[주의]"
            lines.append(
                f"{prefix} [{s_title} #{al.get('item_no')}] {al.get('question')} ☞ {al.get('label')} ({al.get('score')}점)"
            )

    if clinician_memo.strip():
        lines.append(f"------------------------------------------")
        lines.append(f"[3. 진료실 메모]")
        lines.append(clinician_memo.strip())

    lines.append(f"==========================================")
    return "\n".join(lines)


def generate_standalone_html_report(
    chart_id: str,
    patient_name: str,
    visit_round: str,
    submitted_at: str,
    surveys: List[Dict[str, Any]],
    emr_text: str,
    clinician_memo: str = "",
) -> str:
    """
    로컬 폴더(공유폴더/원드라이브)에 `이름-차수-차트번호_설문.html` 로 저장되는
    독립 실행형(단일 파일) 임상 결과 보고서 HTML을 생성합니다.
    """
    dt_str = submitted_at[:19].replace("T", " ") if submitted_at else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    safe_name = html.escape(patient_name or "미입력")
    safe_round = html.escape(visit_round or "1차")
    safe_chart = html.escape(chart_id or "-")
    safe_emr = html.escape(emr_text)

    # 척도별 점수 바 카드 생성
    score_cards_html = ""
    for s in surveys:
        title = html.escape(s.get("title", ""))
        total = s.get("total_score", 0)
        max_s = max(s.get("max_score", 1), 1)
        pct = min(100, round((total / max_s) * 100))
        sev = html.escape(s.get("severity", ""))
        color = s.get("color", "#0f766e")

        sub_html = ""
        if s.get("subscales"):
            badges = [
                f"<span class='sub-badge'>{html.escape(k)}: <strong>{html.escape(str(v))}</strong></span>"
                for k, v in s["subscales"].items()
            ]
            sub_html = f"<div class='sub-wrap'>{''.join(badges)}</div>"

        score_cards_html += f"""
        <div class="score-card">
          <div class="score-card-top">
            <div class="score-title">{title}</div>
            <div class="sev-badge" style="background:{color}18; color:{color}; border:1.5px solid {color};">
              {sev}
            </div>
          </div>
          <div class="score-num-row">
            <span class="score-big" style="color:{color};">{total}</span>
            <span class="score-max">/ {max_s}점 ({pct}%)</span>
          </div>
          <div class="bar-bg">
            <div class="bar-fill" style="width:{pct}%; background:{color};"></div>
          </div>
          {sub_html}
        </div>
        """

    # 주의 문항 하이라이트 HTML
    alerts_rows_html = ""
    for s in surveys:
        s_short = html.escape(s.get("short_title", s.get("title", "")))
        for al in s.get("alerts", []):
            is_crit = al.get("is_critical", False)
            row_cls = "alert-item critical" if is_crit else "alert-item warning"
            tag = "🚨 핵심위험" if is_crit else "⚠️ 2점+ 주의"
            alerts_rows_html += f"""
            <div class="{row_cls}">
              <span class="alert-tag">{tag}</span>
              <strong style="margin-right:6px;">[{s_short} #{al.get('item_no')}]</strong>
              <span style="flex:1;">{html.escape(str(al.get('question', '')))}</span>
              <span class="alert-score">{html.escape(str(al.get('label', '')))} ({al.get('score')}점)</span>
            </div>
            """

    if not alerts_rows_html:
        alerts_rows_html = '<div style="padding:14px; color:#15803d; background:#f0fdf4; border-radius:10px; font-weight:600;">✓ 2점 이상 체크된 주의 문항이 없습니다.</div>'

    # 설문별 상세 문항 테이블 HTML
    details_html = ""
    for s in surveys:
        code = s.get("survey_code", "")
        spec = SURVEY_CATALOG.get(code, {})
        title = html.escape(s.get("title", code))

        if s.get("is_checklist"):
            sec_rows = ""
            for sec_sum in s.get("section_summaries", []):
                sec_rows += f"""
                <tr>
                  <td style="font-weight:700; width:28%;">{html.escape(sec_sum.get('section', ''))}</td>
                  <td>{html.escape(', '.join(sec_sum.get('items', [])))} {html.escape(sec_sum.get('other', ''))}</td>
                  <td style="text-align:center; font-weight:700; width:90px;">{sec_sum.get('count', 0)}개</td>
                </tr>
                """
            if not sec_rows:
                sec_rows = '<tr><td colspan="3" style="text-align:center; color:#64748b;">선택된 항목 없음</td></tr>'

            details_html += f"""
            <div class="detail-section">
              <h3>{title} - 체크 항목 상세</h3>
              <table class="detail-table">
                <thead>
                  <tr><th>분류</th><th>체크된 증상</th><th>개수</th></tr>
                </thead>
                <tbody>{sec_rows}</tbody>
              </table>
            </div>
            """
        else:
            questions = spec.get("questions", [])
            answers = s.get("answers", [])
            threshold = spec.get("alert_threshold", 2)
            critical_set = set(spec.get("critical_items", []))
            rows = ""
            for idx, score in enumerate(answers):
                item_no = idx + 1
                q_text = questions[idx] if idx < len(questions) else f"문항 {item_no}"
                opts = spec.get("custom_options_by_index", {}).get(idx, spec.get("options", []))
                opt_label = next((o["label"] for o in opts if o["value"] == score), f"{score}점")

                is_high = (code == "PHQ9" and item_no == 9 and score >= 1) or (score >= threshold) or (item_no in critical_set and score >= 2)
                tr_style = "background:#fef2f2; color:#991b1b; font-weight:700;" if is_high else ""
                badge_html = '<span style="color:#dc2626; font-weight:800;">●</span> ' if is_high else ""

                rows += f"""
                <tr style="{tr_style}">
                  <td style="text-align:center; width:56px;">{item_no}</td>
                  <td>{badge_html}{html.escape(q_text)}</td>
                  <td style="width:180px;">{html.escape(opt_label)}</td>
                  <td style="text-align:center; width:70px; font-weight:700;">{score}점</td>
                </tr>
                """

            details_html += f"""
            <div class="detail-section">
              <h3>{title} - 문항별 응답 상세 (원본 배열: {html.escape(json.dumps(answers))})</h3>
              <table class="detail-table">
                <thead>
                  <tr><th>번호</th><th>문항 내용</th><th>환자 응답</th><th>점수</th></tr>
                </thead>
                <tbody>{rows}</tbody>
              </table>
            </div>
            """

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <title>{safe_name}-{safe_round}-{safe_chart}_설문결과</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Pretendard", "Malgun Gothic", sans-serif;
      background: #f1f5f9;
      color: #0f172a;
      margin: 0;
      padding: 24px;
      line-height: 1.5;
    }}
    .report-wrap {{
      max-width: 960px;
      margin: 0 auto;
      background: #ffffff;
      border-radius: 16px;
      padding: 32px;
      box-shadow: 0 4px 20px rgba(15, 23, 42, 0.08);
    }}
    .report-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      border-bottom: 2px solid #0f766e;
      padding-bottom: 18px;
      margin-bottom: 24px;
    }}
    .patient-meta {{
      display: flex;
      gap: 14px;
      flex-wrap: wrap;
      margin-top: 8px;
    }}
    .meta-pill {{
      background: #f0fdfa;
      border: 1px solid #99f6e4;
      color: #115e59;
      padding: 5px 12px;
      border-radius: 8px;
      font-size: 0.92rem;
      font-weight: 700;
    }}
    .score-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(270px, 1fr));
      gap: 16px;
      margin-bottom: 26px;
    }}
    .score-card {{
      border: 1px solid #e2e8f0;
      border-radius: 14px;
      padding: 18px;
      background: #fafafa;
    }}
    .score-card-top {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
      margin-bottom: 10px;
    }}
    .score-title {{
      font-weight: 800;
      font-size: 1rem;
    }}
    .sev-badge {{
      padding: 3px 10px;
      border-radius: 999px;
      font-size: 0.8rem;
      font-weight: 800;
      white-space: nowrap;
    }}
    .score-num-row {{
      display: flex;
      align-items: baseline;
      gap: 6px;
      margin-bottom: 8px;
    }}
    .score-big {{
      font-size: 1.9rem;
      font-weight: 900;
    }}
    .score-max {{
      font-size: 0.9rem;
      color: #64748b;
      font-weight: 600;
    }}
    .bar-bg {{
      width: 100%;
      height: 10px;
      background: #e2e8f0;
      border-radius: 99px;
      overflow: hidden;
    }}
    .bar-fill {{
      height: 100%;
      border-radius: 99px;
    }}
    .sub-wrap {{
      margin-top: 10px;
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }}
    .sub-badge {{
      font-size: 0.78rem;
      background: #fff;
      border: 1px solid #cbd5e1;
      padding: 2px 8px;
      border-radius: 6px;
    }}
    .section-box {{
      margin-bottom: 26px;
    }}
    .section-title {{
      font-size: 1.1rem;
      font-weight: 800;
      margin: 0 0 12px 0;
      color: #0f172a;
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .alert-item {{
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 14px;
      border-radius: 10px;
      margin-bottom: 8px;
      font-size: 0.92rem;
    }}
    .alert-item.critical {{
      background: #fef2f2;
      border: 1.5px solid #ef4444;
      color: #991b1b;
    }}
    .alert-item.warning {{
      background: #fff7ed;
      border: 1px solid #fdba74;
      color: #9a3412;
    }}
    .alert-tag {{
      font-weight: 800;
      font-size: 0.78rem;
      padding: 2px 8px;
      border-radius: 6px;
      background: rgba(239, 68, 68, 0.12);
      white-space: nowrap;
    }}
    .alert-score {{
      font-weight: 800;
      white-space: nowrap;
    }}
    .emr-box {{
      background: #0f172a;
      color: #f8fafc;
      border-radius: 12px;
      padding: 16px;
      font-family: "Consolas", "Monaco", monospace;
      font-size: 0.88rem;
      white-space: pre-wrap;
      position: relative;
    }}
    .copy-btn {{
      background: #0f766e;
      color: #fff;
      border: none;
      padding: 8px 16px;
      border-radius: 8px;
      font-weight: 700;
      cursor: pointer;
      font-size: 0.88rem;
    }}
    .detail-section {{
      margin-top: 24px;
    }}
    .detail-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.9rem;
    }}
    .detail-table th, .detail-table td {{
      border: 1px solid #cbd5e1;
      padding: 9px 12px;
      text-align: left;
    }}
    .detail-table th {{
      background: #f8fafc;
      font-weight: 800;
    }}
    @media print {{
      body {{ background: #fff; padding: 0; }}
      .report-wrap {{ box-shadow: none; padding: 10px; }}
      .no-print {{ display: none !important; }}
    }}
  </style>
</head>
<body>
  <div class="report-wrap">
    <div class="report-header">
      <div>
        <div style="font-size:0.85rem; font-weight:700; color:#0f766e;">해아림한의원 자기보고식 심리·신체 설문 결과지</div>
        <h1 style="margin:4px 0 6px; font-size:1.6rem;">{safe_name} 님 ({safe_round}) 설문 리포트</h1>
        <div class="patient-meta">
          <span class="meta-pill">차트번호: {safe_chart}</span>
          <span class="meta-pill">검사차수: {safe_round}</span>
          <span class="meta-pill">제출일시: {html.escape(dt_str)}</span>
        </div>
      </div>
      <div class="no-print" style="display:flex; gap:8px;">
        <button class="copy-btn" onclick="copyEmrText()">📋 EMR 차트 텍스트 복사</button>
        <button class="copy-btn" style="background:#475569;" onclick="window.print()">🖨️ 인쇄하기</button>
      </div>
    </div>

    <div class="section-box">
      <div class="section-title">📊 1. 척도별 점수 및 임상 중증도 (Cut-off 기준)</div>
      <div class="score-grid">
        {score_cards_html}
      </div>
    </div>

    <div class="section-box">
      <div class="section-title">🚨 2. 주의 문항 하이라이트 (2점 이상 핵심 증상 및 위험 문항)</div>
      {alerts_rows_html}
    </div>

    <div class="section-box">
      <div class="section-title" style="justify-content:space-between;">
        <span>📋 3. 전자차트(EMR) 기록용 텍스트 블록</span>
        <button class="copy-btn no-print" onclick="copyEmrText()" id="copyBtnLabel">원클릭 복사</button>
      </div>
      <div class="emr-box" id="emrTextBlock">{safe_emr}</div>
    </div>

    {details_html}
  </div>

  <script>
    function copyEmrText() {{
      const text = document.getElementById("emrTextBlock").innerText;
      navigator.clipboard.writeText(text).then(() => {{
        const btn = document.getElementById("copyBtnLabel");
        if (btn) {{
          btn.textContent = "✓ 복사 완료!";
          setTimeout(() => btn.textContent = "원클릭 복사", 2000);
        }}
        alert("전자차트(EMR) 기록용 텍스트가 클립보드에 복사되었습니다. 차트에 붙여넣기(Ctrl+V) 하세요.");
      }});
    }}
  </script>
</body>
</html>
"""
