# -*- coding: utf-8 -*-
"""
survey_definitions.py 의 설문 카탈로그와 .env 의 Supabase 설정을 결합하여
Cloudflare Pages 배포용 단일 HTML/JS 파일 (frontend/index.html)을 생성하는 빌더 모듈입니다.
"""

import json
import os
from pathlib import Path
from dotenv import load_dotenv
from survey_definitions import SURVEY_CATALOG, SURVEY_PRESETS


def generate_frontend_html(supabase_url: str = "", supabase_anon_key: str = "") -> str:
    catalog_json = json.dumps(SURVEY_CATALOG, ensure_ascii=False)
    presets_json = json.dumps(SURVEY_PRESETS, ensure_ascii=False)

    html_template = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
  <title>해아림한의원 모바일 자가보고 설문</title>
  <style>
    :root {{
      --primary: #0f766e;
      --primary-dark: #115e59;
      --primary-light: #ccfbf1;
      --primary-soft: #f0fdfa;
      --bg: #f8fafc;
      --card-bg: #ffffff;
      --text: #0f172a;
      --text-muted: #475569;
      --border: #e2e8f0;
      --danger: #ef4444;
      --warning: #f59e0b;
      --success: #10b981;
      --radius: 16px;
    }}

    * {{
      box-sizing: border-box;
      -webkit-tap-highlight-color: transparent;
    }}

    body {{
      margin: 0;
      padding: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Pretendard", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding-bottom: 90px;
    }}

    /* 상단 고정 헤더 & 진행률 바 */
    .sticky-header {{
      position: sticky;
      top: 0;
      z-index: 100;
      background: rgba(255, 255, 255, 0.96);
      backdrop-filter: blur(8px);
      border-bottom: 1px solid var(--border);
      box-shadow: 0 2px 10px rgba(15, 23, 42, 0.05);
    }}

    .header-inner {{
      max-width: 640px;
      margin: 0 auto;
      padding: 12px 16px 10px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
    }}

    .brand-title {{
      font-size: 1.05rem;
      font-weight: 800;
      color: var(--primary-dark);
      display: flex;
      align-items: center;
      gap: 6px;
    }}

    .chart-badge {{
      background: var(--primary-soft);
      border: 1.5px solid var(--primary);
      color: var(--primary-dark);
      font-weight: 700;
      font-size: 0.88rem;
      padding: 4px 10px;
      border-radius: 999px;
      white-space: nowrap;
    }}

    .progress-wrap {{
      max-width: 640px;
      margin: 0 auto;
      padding: 0 16px 10px;
    }}

    .progress-meta {{
      display: flex;
      justify-content: space-between;
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--text-muted);
      margin-bottom: 5px;
    }}

    .progress-bar-bg {{
      width: 100%;
      height: 8px;
      background: #e2e8f0;
      border-radius: 999px;
      overflow: hidden;
    }}

    .progress-bar-fill {{
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, #0d9488, #10b981);
      border-radius: 999px;
      transition: width 0.3s ease;
    }}

    .container {{
      max-width: 640px;
      margin: 0 auto;
      padding: 16px;
    }}

    /* 개인정보 미수집 안내 및 차트번호 입력 카드 */
    .info-card {{
      background: var(--card-bg);
      border-radius: var(--radius);
      padding: 18px;
      border: 1px solid var(--border);
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
      margin-bottom: 16px;
    }}

    .privacy-notice {{
      background: #f0fdf4;
      border: 1px solid #bbf7d0;
      color: #166534;
      border-radius: 12px;
      padding: 11px 14px;
      font-size: 0.85rem;
      font-weight: 600;
      margin-bottom: 14px;
      display: flex;
      align-items: flex-start;
      gap: 8px;
    }}

    .field-group {{
      margin-bottom: 12px;
    }}

    .field-group:last-child {{
      margin-bottom: 0;
    }}

    .field-label {{
      display: block;
      font-size: 0.9rem;
      font-weight: 700;
      margin-bottom: 6px;
      color: var(--text);
    }}

    .chart-input {{
      width: 100%;
      font-size: 1.15rem;
      font-weight: 700;
      padding: 13px 15px;
      border: 2px solid #cbd5e1;
      border-radius: 12px;
      outline: none;
      transition: border-color 0.2s, box-shadow 0.2s;
      background: #fff;
      color: var(--text);
    }}

    .chart-input:focus {{
      border-color: var(--primary);
      box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.15);
    }}

    /* 설문 종류 선택 칩 (URL에 type이 없거나 추가 선택 시) */
    .survey-selector {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 8px;
    }}

    .survey-chip {{
      padding: 9px 13px;
      border-radius: 10px;
      border: 1.5px solid #cbd5e1;
      background: #fff;
      font-size: 0.88rem;
      font-weight: 600;
      color: var(--text-muted);
      cursor: pointer;
      user-select: none;
      transition: all 0.15s;
    }}

    .survey-chip.active {{
      background: var(--primary);
      color: #fff;
      border-color: var(--primary);
      box-shadow: 0 2px 6px rgba(15, 118, 110, 0.25);
    }}

    /* 설문 섹션 헤더 */
    .survey-section-header {{
      background: linear-gradient(135deg, #0f766e 0%, #115e59 100%);
      color: #fff;
      border-radius: var(--radius);
      padding: 18px 20px;
      margin: 24px 0 14px;
      box-shadow: 0 4px 12px rgba(15, 118, 110, 0.15);
    }}

    .survey-section-title {{
      font-size: 1.2rem;
      font-weight: 800;
      margin: 0 0 6px 0;
    }}

    .survey-section-desc {{
      font-size: 0.9rem;
      opacity: 0.92;
      margin: 0;
      line-height: 1.45;
    }}

    /* 개별 문항 카드 */
    .question-card {{
      background: var(--card-bg);
      border-radius: var(--radius);
      padding: 18px 16px;
      margin-bottom: 14px;
      border: 2px solid var(--border);
      box-shadow: 0 2px 5px rgba(15, 23, 42, 0.03);
      transition: border-color 0.25s, transform 0.2s, box-shadow 0.25s;
      scroll-margin-top: 110px;
    }}

    .question-card.answered {{
      border-color: #99f6e4;
      background: #ffffff;
    }}

    .question-card.unanswered-error {{
      border-color: var(--danger);
      background: #fef2f2;
      animation: shake 0.35s ease;
    }}

    @keyframes shake {{
      0%, 100% {{ transform: translateX(0); }}
      25% {{ transform: translateX(-5px); }}
      75% {{ transform: translateX(5px); }}
    }}

    .question-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 8px;
      margin-bottom: 14px;
    }}

    .question-text {{
      font-size: 1.03rem;
      font-weight: 700;
      color: var(--text);
      line-height: 1.45;
      word-break: keep-all;
    }}

    .status-dot {{
      flex-shrink: 0;
      width: 24px;
      height: 24px;
      border-radius: 50%;
      background: #f1f5f9;
      color: #94a3b8;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 0.78rem;
      font-weight: 800;
    }}

    .question-card.answered .status-dot {{
      background: var(--success);
      color: #fff;
    }}

    /* 모바일 터치 최적화 대형 라디오 버튼 리스트 */
    .options-list {{
      display: flex;
      flex-direction: column;
      gap: 9px;
    }}

    .option-btn {{
      display: flex;
      align-items: center;
      width: 100%;
      min-height: 54px;
      padding: 12px 15px;
      border-radius: 12px;
      border: 2px solid #e2e8f0;
      background: #f8fafc;
      cursor: pointer;
      transition: all 0.15s ease;
      text-align: left;
      font-size: 0.98rem;
      font-weight: 600;
      color: #334155;
      gap: 12px;
      user-select: none;
    }}

    .option-btn:active {{
      transform: scale(0.985);
    }}

    .option-radio-circle {{
      width: 24px;
      height: 24px;
      border-radius: 50%;
      border: 2px solid #94a3b8;
      background: #fff;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      transition: all 0.15s;
    }}

    .option-radio-inner {{
      width: 12px;
      height: 12px;
      border-radius: 50%;
      background: transparent;
      transition: all 0.15s;
    }}

    .option-btn.selected {{
      border-color: var(--primary);
      background: var(--primary-soft);
      color: var(--primary-dark);
      font-weight: 700;
      box-shadow: 0 2px 8px rgba(15, 118, 110, 0.12);
    }}

    .option-btn.selected .option-radio-circle {{
      border-color: var(--primary);
      background: var(--primary);
    }}

    .option-btn.selected .option-radio-inner {{
      background: #fff;
    }}

    .option-score-badge {{
      margin-left: auto;
      font-size: 0.78rem;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 99px;
      background: #e2e8f0;
      color: #475569;
      flex-shrink: 0;
    }}

    .option-btn.selected .option-score-badge {{
      background: var(--primary);
      color: #fff;
    }}

    /* 체크리스트형 (틱 초진 / 한방진단검사지) 터치 그리드 */
    .checklist-grid {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 8px;
    }}

    @media (min-width: 440px) {{
      .checklist-grid.two-col {{
        grid-template-columns: 1fr 1fr;
      }}
    }}

    .check-item-btn {{
      display: flex;
      align-items: center;
      gap: 10px;
      min-height: 50px;
      padding: 11px 13px;
      border-radius: 12px;
      border: 2px solid #e2e8f0;
      background: #f8fafc;
      font-size: 0.93rem;
      font-weight: 600;
      color: #334155;
      cursor: pointer;
      user-select: none;
      transition: all 0.15s;
    }}

    .check-item-btn.checked {{
      border-color: var(--primary);
      background: var(--primary-soft);
      color: var(--primary-dark);
      font-weight: 700;
    }}

    .check-box-icon {{
      width: 22px;
      height: 22px;
      border-radius: 6px;
      border: 2px solid #94a3b8;
      background: #fff;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      font-size: 0.8rem;
      color: transparent;
    }}

    .check-item-btn.checked .check-box-icon {{
      background: var(--primary);
      border-color: var(--primary);
      color: #fff;
    }}

    /* 하단 제출 버튼 바 */
    .submit-bar {{
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      background: rgba(255, 255, 255, 0.95);
      backdrop-filter: blur(8px);
      border-top: 1px solid var(--border);
      padding: 12px 16px;
      z-index: 100;
    }}

    .submit-bar-inner {{
      max-width: 640px;
      margin: 0 auto;
      display: flex;
      gap: 10px;
    }}

    .submit-btn {{
      width: 100%;
      min-height: 56px;
      border: none;
      border-radius: 14px;
      background: linear-gradient(135deg, #0f766e 0%, #0d9488 100%);
      color: #fff;
      font-size: 1.1rem;
      font-weight: 800;
      cursor: pointer;
      box-shadow: 0 4px 14px rgba(15, 118, 110, 0.3);
      transition: opacity 0.2s, transform 0.15s;
    }}

    .submit-btn:active {{
      transform: scale(0.99);
    }}

    .submit-btn:disabled {{
      opacity: 0.6;
      cursor: not-allowed;
    }}

    /* 완료 화면 */
    .complete-screen {{
      display: none;
      text-align: center;
      padding: 40px 20px;
      background: #fff;
      border-radius: 20px;
      border: 1px solid var(--border);
      margin-top: 24px;
      box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
    }}

    .complete-icon {{
      width: 72px;
      height: 72px;
      border-radius: 50%;
      background: #dcfce7;
      color: #15803d;
      font-size: 2.2rem;
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0 auto 18px;
    }}

    .toast {{
      position: fixed;
      bottom: 84px;
      left: 50%;
      transform: translateX(-50%);
      background: rgba(15, 23, 42, 0.92);
      color: #fff;
      padding: 10px 18px;
      border-radius: 999px;
      font-size: 0.88rem;
      font-weight: 600;
      z-index: 200;
      display: none;
      box-shadow: 0 4px 12px rgba(0,0,0,0.2);
      white-space: nowrap;
    }}
  </style>
</head>
<body>

  <!-- 상단 고정 헤더 -->
  <header class="sticky-header">
    <div class="header-inner">
      <div class="brand-title">
        <span>🌿</span>
        <span>해아림한의원 자가보고 설문</span>
      </div>
      <div class="chart-badge" id="headerChartBadge">차트번호 미입력</div>
    </div>
    <div class="progress-wrap">
      <div class="progress-meta">
        <span id="progressLabel">설문 진행률</span>
        <span id="progressCount">0 / 0 문항</span>
      </div>
      <div class="progress-bar-bg">
        <div class="progress-bar-fill" id="progressBarFill"></div>
      </div>
    </div>
  </header>

  <main class="container">
    <!-- 메인 작성 영역 -->
    <div id="surveyFormContainer">
      <section class="info-card">
        <div class="privacy-notice">
          <span>🔒</span>
          <div>
            <strong>개인식별정보 미수집 안내</strong><br/>
            본 설문은 개인정보 보호를 위해 <u>이름, 연락처, 생년월일 등 개인정보를 입력받지 않으며</u>, 오직 원내 차트번호로만 안전하게 접수됩니다.
          </div>
        </div>

        <div class="field-group">
          <label class="field-label" for="chartIdInput">환자 차트번호 (안내받은 번호 확인 또는 입력)</label>
          <input
            type="text"
            id="chartIdInput"
            class="chart-input"
            placeholder="예: 10293 (차트번호를 입력해주세요)"
            autocomplete="off"
          />
        </div>

        <div class="field-group" id="surveySelectorWrap" style="margin-top: 14px;">
          <label class="field-label">작성할 설문 종류 <span style="font-weight:500; font-size:0.82rem; color:#64748b;">(터치하여 선택/해제 가능)</span></label>
          <div class="survey-selector" id="surveyChipsContainer"></div>
        </div>
      </section>

      <!-- 동적 설문 문항 렌더링 영역 -->
      <div id="questionsRoot"></div>
    </div>

    <!-- 제출 완료 화면 -->
    <div id="completeScreen" class="complete-screen">
      <div class="complete-icon">✓</div>
      <h2 style="margin: 0 0 10px; font-size: 1.45rem; color: #0f172a;">설문 제출이 완료되었습니다</h2>
      <p style="color: #475569; font-size: 0.98rem; margin: 0 0 20px;">
        작성하신 설문 결과가 진료실로 안전하게 전달되었습니다.<br/>
        창을 닫으시고 대기해 주시면 됩니다. 감사합니다.
      </p>
      <div id="submittedSummaryBox" style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; padding:14px; text-align:left; font-size:0.9rem; color:#334155; margin-bottom:18px;"></div>
      <button type="button" onclick="window.location.reload()" style="padding:12px 24px; border-radius:10px; border:1px solid #cbd5e1; background:#fff; font-weight:700; cursor:pointer;">
        다른 설문 추가로 작성하기
      </button>
    </div>
  </main>

  <!-- 하단 고정 제출 버튼 -->
  <div class="submit-bar" id="submitBar">
    <div class="submit-bar-inner">
      <button type="button" class="submit-btn" id="submitBtn" onclick="handleSubmitSurvey()">
        설문 작성 완료 및 제출하기
      </button>
    </div>
  </div>

  <div class="toast" id="toastMsg"></div>

  <script>
    // =========================================================================
    // 1. Supabase 연동 설정 (환경변수 주입 또는 URL 쿼리 파라미터 지원)
    // =========================================================================
    const DEFAULT_SUPABASE_CONFIG = {{
      url: "{supabase_url}",
      anonKey: "{supabase_anon_key}"
    }};

    // 설문 카탈로그 데이터
    const SURVEY_CATALOG = {catalog_json};
    const SURVEY_PRESETS = {presets_json};

    // 상태 관리
    let activeSurveyCodes = [];
    let responses = {{}};      // {{ surveyCode: [val0, val1, ...] or {{ sec_id: [...] }} }}
    let metaResponses = {{}};  // {{ surveyCode: {{ key: val }} }}

    function showToast(msg, duration = 2400) {{
      const el = document.getElementById("toastMsg");
      el.textContent = msg;
      el.style.display = "block";
      clearTimeout(window.__toastTimer);
      window.__toastTimer = setTimeout(() => {{
        el.style.display = "none";
      }}, duration);
    }}

    // URL 쿼리 파라미터 파싱 (?id=차트번호&type=설문종류)
    function parseUrlParams() {{
      const params = new URLSearchParams(window.location.search);
      const chartId = (params.get("id") || params.get("chart_id") || "").trim();
      const typeParam = (params.get("type") || params.get("survey") || "").trim();
      const sbUrl = (params.get("sb_url") || "").trim();
      const sbKey = (params.get("sb_key") || "").trim();

      if (sbUrl) DEFAULT_SUPABASE_CONFIG.url = sbUrl;
      if (sbKey) DEFAULT_SUPABASE_CONFIG.anonKey = sbKey;

      const chartInput = document.getElementById("chartIdInput");
      if (chartId) {{
        chartInput.value = chartId;
        updateHeaderBadge(chartId);
      }}

      chartInput.addEventListener("input", (e) => {{
        updateHeaderBadge(e.target.value.trim());
      }});

      // type 파라미터 분석 (예: ?type=PHQ9 또는 ?type=BAI,PHQ9,ISI)
      if (typeParam) {{
        const codes = typeParam.split(",").map(s => s.trim().toUpperCase()).filter(Boolean);
        // 별칭 매핑 (예: INSOMNIA -> ISI, TIC -> TIC_INIT, PHQ-9 -> PHQ9, GAD-7 -> GAD7)
        const aliasMap = {{
          "PHQ-9": "PHQ9",
          "GAD-7": "GAD7",
          "INSOMNIA": "ISI",
          "TIC": "TIC_INIT",
          "TIC_INIT": "TIC_INIT",
          "한방문진": "HANBANG",
          "ALL_PSYCH": "BAI,PHQ9,PDI,ISI"
        }};
        let resolved = [];
        codes.forEach(c => {{
          const mapped = aliasMap[c] || c;
          mapped.split(",").forEach(m => {{
            if (SURVEY_CATALOG[m] && !resolved.includes(m)) {{
              resolved.push(m);
            }}
          }});
        }});
        if (resolved.length > 0) {{
          activeSurveyCodes = resolved;
          // URL로 설문종류가 명확히 지정된 경우 설문 변경 칩은 접어두어 환자 혼선 방지
          document.getElementById("surveySelectorWrap").style.display = "none";
        }}
      }}

      if (activeSurveyCodes.length === 0) {{
        // 기본값: PHQ9, BAI, ISI
        activeSurveyCodes = ["BAI", "PHQ9", "ISI"];
      }}

      renderSurveyChips();
      initSurveyState();
      renderAllQuestions();
      updateProgress();
    }}

    function updateHeaderBadge(val) {{
      const badge = document.getElementById("headerChartBadge");
      if (val) {{
        badge.textContent = `차트번호: ${{val}}`;
        badge.style.background = "#ccfbf1";
      }} else {{
        badge.textContent = "차트번호 미입력";
        badge.style.background = "#fef2f2";
      }}
    }}

    function renderSurveyChips() {{
      const container = document.getElementById("surveyChipsContainer");
      container.innerHTML = "";
      Object.keys(SURVEY_CATALOG).forEach(code => {{
        const spec = SURVEY_CATALOG[code];
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "survey-chip" + (activeSurveyCodes.includes(code) ? " active" : "");
        chip.textContent = spec.short_title || spec.title;
        chip.onclick = () => {{
          if (activeSurveyCodes.includes(code)) {{
            if (activeSurveyCodes.length === 1) {{
              showToast("최소 1개 이상의 설문을 선택해야 합니다.");
              return;
            }}
            activeSurveyCodes = activeSurveyCodes.filter(c => c !== code);
          }} else {{
            activeSurveyCodes.push(code);
          }}
          renderSurveyChips();
          initSurveyState();
          renderAllQuestions();
          updateProgress();
        }};
        container.appendChild(chip);
      }});
    }}

    function initSurveyState() {{
      activeSurveyCodes.forEach(code => {{
        const spec = SURVEY_CATALOG[code];
        if (!spec) return;
        if (spec.is_checklist) {{
          if (!responses[code]) {{
            responses[code] = {{}};
            (spec.sections || []).forEach(sec => {{
              responses[code][sec.id] = [];
              responses[code][sec.id + "_other"] = "";
            }});
          }}
          if (!metaResponses[code]) metaResponses[code] = {{}};
        }} else {{
          if (!responses[code] || !Array.isArray(responses[code])) {{
            responses[code] = new Array(spec.questions.length).fill(null);
          }}
        }}
      }});
    }}

    function renderAllQuestions() {{
      const root = document.getElementById("questionsRoot");
      root.innerHTML = "";

      activeSurveyCodes.forEach((code) => {{
        const spec = SURVEY_CATALOG[code];
        if (!spec) return;

        // 설문 섹션 배너
        const secHeader = document.createElement("div");
        secHeader.className = "survey-section-header";
        secHeader.innerHTML = `
          <h2 class="survey-section-title">${{spec.title}}</h2>
          <p class="survey-section-desc">${{spec.description || ""}}</p>
        `;
        root.appendChild(secHeader);

        if (spec.is_checklist) {{
          renderChecklistSurvey(root, code, spec);
        }} else {{
          renderLikertSurvey(root, code, spec);
        }}
      }});
    }}

    function renderLikertSurvey(root, code, spec) {{
      spec.questions.forEach((qText, qIdx) => {{
        const card = document.createElement("div");
        const currentVal = responses[code][qIdx];
        card.className = "question-card" + (currentVal !== null ? " answered" : "");
        card.id = `qcard_${{code}}_${{qIdx}}`;
        card.dataset.surveyCode = code;
        card.dataset.qIdx = qIdx;

        const opts = (spec.custom_options_by_index && spec.custom_options_by_index[qIdx])
          ? spec.custom_options_by_index[qIdx]
          : spec.options;

        let optionsHtml = "";
        opts.forEach((opt) => {{
          const isSelected = currentVal === opt.value;
          optionsHtml += `
            <button
              type="button"
              class="option-btn ${{isSelected ? "selected" : ""}}"
              onclick="selectLikertOption('${{code}}', ${{qIdx}}, ${{opt.value}})"
            >
              <span class="option-radio-circle">
                <span class="option-radio-inner"></span>
              </span>
              <span style="flex:1;">${{opt.label}}</span>
              <span class="option-score-badge">${{opt.value}}점</span>
            </button>
          `;
        }});

        card.innerHTML = `
          <div class="question-header">
            <div class="question-text">${{qText}}</div>
            <div class="status-dot" id="dot_${{code}}_${{qIdx}}">${{currentVal !== null ? "✓" : (qIdx + 1)}}</div>
          </div>
          <div class="options-list" id="opts_${{code}}_${{qIdx}}">
            ${{optionsHtml}}
          </div>
        `;
        root.appendChild(card);
      }});
    }}

    function selectLikertOption(code, qIdx, value) {{
      responses[code][qIdx] = value;

      // UI 즉시 업데이트
      const card = document.getElementById(`qcard_${{code}}_${{qIdx}}`);
      if (card) {{
        card.classList.remove("unanswered-error");
        card.classList.add("answered");
      }}
      const dot = document.getElementById(`dot_${{code}}_${{qIdx}}`);
      if (dot) dot.textContent = "✓";

      const optsContainer = document.getElementById(`opts_${{code}}_${{qIdx}}`);
      if (optsContainer) {{
        const spec = SURVEY_CATALOG[code];
        const opts = (spec.custom_options_by_index && spec.custom_options_by_index[qIdx])
          ? spec.custom_options_by_index[qIdx]
          : spec.options;
        const buttons = optsContainer.querySelectorAll(".option-btn");
        buttons.forEach((btn, idx) => {{
          if (opts[idx] && opts[idx].value === value) {{
            btn.classList.add("selected");
          }} else {{
            btn.classList.remove("selected");
          }}
        }});
      }}

      updateProgress();

      // 다음 문항으로 부드럽게 자동 스크롤 이동
      setTimeout(() => {{
        scrollToNextQuestion(code, qIdx);
      }}, 210);
    }}

    function scrollToNextQuestion(currentCode, currentQIdx) {{
      const spec = SURVEY_CATALOG[currentCode];
      // 1) 현재 설문의 다음 문항 확인
      if (spec && !spec.is_checklist && currentQIdx + 1 < spec.questions.length) {{
        const nextCard = document.getElementById(`qcard_${{currentCode}}_${{currentQIdx + 1}}`);
        if (nextCard) {{
          nextCard.scrollIntoView({{ behavior: "smooth", block: "center" }});
          return;
        }}
      }}
      // 2) 다음 설문의 첫 문항 확인
      const codeIdx = activeSurveyCodes.indexOf(currentCode);
      if (codeIdx >= 0 && codeIdx + 1 < activeSurveyCodes.length) {{
        const nextCode = activeSurveyCodes[codeIdx + 1];
        const nextFirst = document.getElementById(`qcard_${{nextCode}}_0`) || document.getElementById(`chksec_${{nextCode}}_0`);
        if (nextFirst) {{
          nextFirst.scrollIntoView({{ behavior: "smooth", block: "center" }});
        }}
      }}
    }}

    function renderChecklistSurvey(root, code, spec) {{
      // 메타 문항 (학력, 발병시기 등 비식별 임상문항)
      if (spec.meta_fields && spec.meta_fields.length > 0) {{
        const metaCard = document.createElement("div");
        metaCard.className = "question-card answered";
        let metaHtml = `<div class="question-text" style="margin-bottom:12px;">기본 임상 문진 (개인식별정보 제외)</div>`;
        spec.meta_fields.forEach(mf => {{
          const val = (metaResponses[code] && metaResponses[code][mf.key]) || "";
          if (mf.type === "select") {{
            const optsHtml = mf.options.map(o => `<option value="${{o}}" ${{val === o ? "selected" : ""}}>${{o}}</option>`).join("");
            metaHtml += `
              <div class="field-group">
                <label class="field-label">${{mf.label}}</label>
                <select class="chart-input" style="font-size:0.95rem; padding:10px;" onchange="updateMetaField('${{code}}', '${{mf.key}}', this.value)">
                  <option value="">선택해주세요</option>
                  ${{optsHtml}}
                </select>
              </div>
            `;
          }} else {{
            metaHtml += `
              <div class="field-group">
                <label class="field-label">${{mf.label}}</label>
                <input type="text" class="chart-input" style="font-size:0.95rem; padding:10px;"
                  placeholder="${{mf.placeholder || ''}}"
                  value="${{val}}"
                   oninput="updateMetaField('${{code}}', '${{mf.key}}', this.value)" />
              </div>
            `;
          }}
        }});
        metaCard.innerHTML = metaHtml;
        root.appendChild(metaCard);
      }}

      // 섹션별 체크리스트 렌더링
      (spec.sections || []).forEach((sec, sIdx) => {{
        const card = document.createElement("div");
        card.className = "question-card answered";
        card.id = `chksec_${{code}}_${{sIdx}}`;

        const selectedArr = (responses[code] && responses[code][sec.id]) || [];
        let itemsHtml = "";
        sec.items.forEach((itemText, iIdx) => {{
          const isChecked = selectedArr.includes(itemText);
          itemsHtml += `
            <button
              type="button"
              class="check-item-btn ${{isChecked ? "checked" : ""}}"
              id="chkbtn_${{code}}_${{sec.id}}_${{iIdx}}"
              onclick="toggleChecklistItem('${{code}}', '${{sec.id}}', ${{iIdx}}, ${{sIdx}})"
            >
              <span class="check-box-icon">✓</span>
              <span style="text-align:left;">${{itemText}}</span>
            </button>
          `;
        }});

        let otherHtml = "";
        if (sec.has_other) {{
          const otherVal = (responses[code] && responses[code][sec.id + "_other"]) || "";
          otherHtml = `
            <div style="margin-top:10px;">
              <input type="text" class="chart-input" style="font-size:0.92rem; padding:10px;"
                placeholder="기타 증상이 있다면 직접 입력해주세요"
                value="${{otherVal}}"
                oninput="responses['${{code}}']['${{sec.id}}_other'] = this.value" />
            </div>
          `;
        }}

        card.innerHTML = `
          <div class="question-header">
            <div class="question-text">${{sec.title}}</div>
            <div class="status-dot" style="width:auto; padding:0 10px; border-radius:99px;" id="chkcount_${{code}}_${{sec.id}}">
              ${{selectedArr.length}}개 선택
            </div>
          </div>
          <div class="checklist-grid two-col">
            ${{itemsHtml}}
          </div>
          ${{otherHtml}}
        `;
        root.appendChild(card);
      }});
    }}

    function updateMetaField(code, key, val) {{
      if (!metaResponses[code]) metaResponses[code] = {{}};
      metaResponses[code][key] = val;
    }}

    function toggleChecklistItem(code, secId, itemIdx, secIdx) {{
      const spec = SURVEY_CATALOG[code];
      const sec = spec.sections[secIdx];
      const itemText = sec.items[itemIdx];
      const arr = responses[code][secId] || [];
      const pos = arr.indexOf(itemText);
      const btn = document.getElementById(`chkbtn_${{code}}_${{secId}}_${{itemIdx}}`);

      if (pos >= 0) {{
        arr.splice(pos, 1);
        if (btn) btn.classList.remove("checked");
      }} else {{
        arr.push(itemText);
        if (btn) btn.classList.add("checked");
      }}
      responses[code][secId] = arr;

      const badge = document.getElementById(`chkcount_${{code}}_${{secId}}`);
      if (badge) badge.textContent = `${{arr.length}}개 선택`;
      updateProgress();
    }}

    function updateProgress() {{
      let totalLikert = 0;
      let answeredLikert = 0;

      activeSurveyCodes.forEach(code => {{
        const spec = SURVEY_CATALOG[code];
        if (!spec) return;
        if (!spec.is_checklist) {{
          const arr = responses[code] || [];
          totalLikert += spec.questions.length;
          answeredLikert += arr.filter(v => v !== null && v !== undefined).length;
        }}
      }});

      const countEl = document.getElementById("progressCount");
      const fillEl = document.getElementById("progressBarFill");

      if (totalLikert === 0) {{
        countEl.textContent = "자유 체크형 설문";
        fillEl.style.width = "100%";
      }} else {{
        const pct = Math.round((answeredLikert / totalLikert) * 100);
        countEl.textContent = `${{answeredLikert}} / ${{totalLikert}} 문항 (${{pct}}%)`;
        fillEl.style.width = `${{pct}}%`;
      }}
    }}

    // =========================================================================
    // 2. 클라이언트 채점 및 JSON 패키징 로직
    // =========================================================================
    function evaluateSurveyClient(code) {{
      const spec = SURVEY_CATALOG[code];
      if (spec.is_checklist) {{
        const secMap = responses[code] || {{}};
        let totalChecked = 0;
        let sectionDetails = [];
        let alerts = [];

        (spec.sections || []).forEach(sec => {{
          const checked = secMap[sec.id] || [];
          const other = (secMap[sec.id + "_other"] || "").trim();
          const cnt = checked.length + (other ? 1 : 0);
          totalChecked += cnt;
          if (cnt > 0) {{
            sectionDetails.push({{
              section_id: sec.id,
              section_title: sec.title,
              count: cnt,
              checked_items: checked,
              other_text: other
            }});
          }}
        }});

        let severity = "정상";
        let color = "#10b981";
        (spec.cutoffs || []).forEach(c => {{
          if (totalChecked >= c.min && totalChecked <= c.max) {{
            severity = c.level;
            color = c.color;
          }}
        }});

        return {{
          survey_code: code,
          title: spec.title,
          short_title: spec.short_title,
          is_checklist: true,
          total_score: totalChecked,
          max_score: spec.max_score,
          severity: `${{severity}} (체크 ${{totalChecked}}개)`,
          color: color,
          meta_answers: metaResponses[code] || {{}},
          answers: secMap,
          section_summaries: sectionDetails,
          alerts: alerts
        }};
      }}

      // 리커트 척도형
      const ansArr = (responses[code] || []).map(v => (v === null || v === undefined) ? 0 : Number(v));
      let totalScore = 0;
      let subscales = {{}};

      if (spec.is_ygtss) {{
        const motor = ansArr.slice(0, 5).reduce((a, b) => a + b, 0);
        const vocal = ansArr.slice(5, 10).reduce((a, b) => a + b, 0);
        const impair = ansArr[10] || 0;
        const globalImp = ansArr[11] || 0;
        totalScore = motor + vocal + impair;
        subscales = {{
          "운동틱 점수": `${{motor}}/25점`,
          "음성틱 점수": `${{vocal}}/25점`,
          "총 틱증상 점수(운동+음성)": `${{motor + vocal}}/50점`,
          "틱장애척도(괴로움)": `${{impair}}/50점`,
          "전반적인 인상": `${{globalImp}}/6점`
        }};
      }} else {{
        totalScore = ansArr.reduce((a, b) => a + b, 0);
        if (spec.subscales) {{
          Object.values(spec.subscales).forEach(sub => {{
            const sSum = sub.indices.reduce((acc, idx) => acc + (ansArr[idx] || 0), 0);
            subscales[sub.name] = `${{sSum}}/${{sub.max}}점`;
          }});
        }}
      }}

      let severity = "정상";
      let color = "#10b981";
      (spec.cutoffs || []).forEach(c => {{
        if (totalScore >= c.min && totalScore <= c.max) {{
          severity = c.level;
          color = c.color;
        }}
      }});

      const threshold = spec.alert_threshold || 2;
      const criticalSet = new Set(spec.critical_items || []);
      let alerts = [];
      let itemizedDetails = [];

      ansArr.forEach((score, idx) => {{
        const itemNo = idx + 1;
        const qText = spec.questions[idx] || `문항 ${{itemNo}}`;
        const opts = (spec.custom_options_by_index && spec.custom_options_by_index[idx])
          ? spec.custom_options_by_index[idx]
          : spec.options;
        const matchedOpt = (opts || []).find(o => o.value === score);
        const optLabel = matchedOpt ? matchedOpt.label : `${{score}}점`;

        itemizedDetails.push({{
          item_no: itemNo,
          question: qText,
          score: score,
          label: optLabel
        }});

        if (code === "PHQ9" && itemNo === 9 && score >= 1) {{
          alerts.push({{
            item_no: itemNo,
            question: qText,
            score: score,
            label: optLabel,
            is_critical: true,
            alert_note: "🚨 자살/자해 사고 위험 문항 양성 (즉시 임상 면담 필요)"
          }});
        }} else if (score >= threshold || (criticalSet.has(itemNo) && score >= 2)) {{
          alerts.push({{
            item_no: itemNo,
            question: qText,
            score: score,
            label: optLabel,
            is_critical: criticalSet.has(itemNo),
            alert_note: criticalSet.has(itemNo) ? "핵심 주의 증상" : `${{threshold}}점 이상 체크`
          }});
        }}
      }});

      return {{
        survey_code: code,
        title: spec.title,
        short_title: spec.short_title,
        is_checklist: false,
        total_score: totalScore,
        max_score: spec.max_score,
        severity: severity,
        color: color,
        subscales: subscales,
        alerts: alerts,
        answers: ansArr,
        itemized_details: itemizedDetails
      }};
    }}

    // =========================================================================
    // 3. 설문 제출 핸들러 (미응답 검증 -> JSON 패키징 -> Supabase REST API POST)
    // =========================================================================
    async function handleSubmitSurvey() {{
      const chartIdInput = document.getElementById("chartIdInput");
      const chartId = chartIdInput.value.trim();

      if (!chartId) {{
        showToast("상단에 차트번호를 입력해주세요!");
        chartIdInput.focus();
        chartIdInput.scrollIntoView({{ behavior: "smooth", block: "center" }});
        return;
      }}

      // 리커트 설문 미응답 문항 검증
      for (const code of activeSurveyCodes) {{
        const spec = SURVEY_CATALOG[code];
        if (!spec || spec.is_checklist) continue;
        const arr = responses[code] || [];
        for (let i = 0; i < spec.questions.length; i++) {{
          if (arr[i] === null || arr[i] === undefined) {{
            const card = document.getElementById(`qcard_${{code}}_${{i}}`);
            if (card) {{
              card.classList.add("unanswered-error");
              card.scrollIntoView({{ behavior: "smooth", block: "center" }});
            }}
            showToast(`[${{spec.short_title}}] ${{i + 1}}번 문항을 선택해주세요.`);
            return;
          }}
        }}
      }}

      const submitBtn = document.getElementById("submitBtn");
      submitBtn.disabled = true;
      submitBtn.textContent = "진료실로 안전하게 전송 중...";

      // 전체 설문 결과 패키징 (survey_responses 테이블 컬럼 구조: chart_id, survey_type, scores, raw_answers)
      const submittedAt = new Date().toISOString();
      const surveyResults = activeSurveyCodes.map(code => evaluateSurveyClient(code));
      const summaryParts = surveyResults.map(r => `${{r.short_title}}: ${{r.total_score}}/${{r.max_score}}점(${{r.severity}})` );
      const scoreSummaryText = summaryParts.join(" | ");

      // scores (jsonb): 설문별 총점, 중증도 등급, 소척도, 주의문항 요약
      const scoresJson = {{
        submitted_at: submittedAt,
        summary_text: scoreSummaryText,
        surveys: surveyResults.map(r => ({{
          survey_code: r.survey_code,
          title: r.title,
          short_title: r.short_title,
          is_checklist: r.is_checklist,
          total_score: r.total_score,
          max_score: r.max_score,
          severity: r.severity,
          color: r.color,
          subscales: r.subscales || {{}},
          alerts: r.alerts || [],
          section_summaries: r.section_summaries || []
        }}))
      }};

      // raw_answers (jsonb): 문항별 원본 응답 배열 (단일 설문이면 배열도 함께 제공, 다중 설문이면 설문코드별 매핑)
      const answersByCode = {{}};
      surveyResults.forEach(r => {{
        answersByCode[r.survey_code] = {{
          answers: r.answers,
          meta_answers: r.meta_answers || {{}},
          itemized_details: r.itemized_details || []
        }};
      }});
      const rawAnswersJson = activeSurveyCodes.length === 1
        ? {{
            survey_code: activeSurveyCodes[0],
            answers: surveyResults[0].answers,
            meta_answers: surveyResults[0].meta_answers || {{}},
            by_survey: answersByCode
          }}
        : {{
            by_survey: answersByCode
          }};

      const relayRow = {{
        chart_id: chartId,
        survey_type: activeSurveyCodes.join(","),
        scores: scoresJson,
        raw_answers: rawAnswersJson
      }};

      try {{
        if (!DEFAULT_SUPABASE_CONFIG.url || !DEFAULT_SUPABASE_CONFIG.anonKey || DEFAULT_SUPABASE_CONFIG.url.includes("your-project-id")) {{
          throw new Error("SUPABASE_NOT_CONFIGURED");
        }}

        const endpoint = `${{DEFAULT_SUPABASE_CONFIG.url.replace(/\\/$/, "")}}/rest/v1/survey_responses`;
        const apiKey = DEFAULT_SUPABASE_CONFIG.anonKey.trim();
        const reqHeaders = {{
          "Content-Type": "application/json",
          "apikey": apiKey,
          "Prefer": "return=minimal"
        }};
        // 기존 JWT(eyJ...) 형식일 때만 Authorization 헤더 추가, 신규 sb_publishable_... 키는 apikey 헤더만 전송
        if (apiKey.startsWith("eyJ")) {{
          reqHeaders["Authorization"] = `Bearer ${{apiKey}}`;
        }}

        const res = await fetch(endpoint, {{
          method: "POST",
          headers: reqHeaders,
          body: JSON.stringify(relayRow)
        }});

        if (!res.ok) {{
          const errText = await res.text();
          throw new Error(`HTTP ${{res.status}}: ${{errText}}`);
        }}

        showCompletionScreen(chartId, surveyResults, true);
      }} catch (err) {{
        console.error("전송 오류:", err);
        // 데모/오프라인 상태이거나 Supabase 미설정 시에도 로컬 백업 JSON 다운로드 안내 제공
        showCompletionScreen(chartId, surveyResults, false, relayRow, err.message);
      }} finally {{
        submitBtn.disabled = false;
        submitBtn.textContent = "설문 작성 완료 및 제출하기";
      }}
    }}

    function showCompletionScreen(chartId, surveyResults, isCloudSuccess, fallbackPayload = null, errMsg = "") {{
      document.getElementById("surveyFormContainer").style.display = "none";
      document.getElementById("submitBar").style.display = "none";
      const screen = document.getElementById("completeScreen");
      screen.style.display = "block";

      const box = document.getElementById("submittedSummaryBox");
      let html = `<div style="font-weight:800; margin-bottom:8px; color:#0f766e;">접수 차트번호: ${{chartId}}</div>`;
      surveyResults.forEach(r => {{
        html += `<div style="margin-bottom:4px;">• <strong>${{r.title}}</strong>: 완료</div>`;
      }});

      if (!isCloudSuccess && fallbackPayload) {{
        const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(fallbackPayload, null, 2));
        html += `
          <div style="margin-top:12px; padding:10px; background:#fffbeb; border:1px solid #fde68a; border-radius:8px; color:#92400e; font-size:0.84rem;">
            ⚠️ 클라우드 중계소 연결 설정 전이거나 일시적 네트워크 오류입니다 (${{errMsg}}).<br/>
            아래 버튼을 눌러 결과 파일을 저장하거나 데스크에 화면을 보여주세요.<br/>
            <a href="${{dataStr}}" download="survey_${{chartId}}.json"
               style="display:inline-block; margin-top:8px; padding:8px 14px; background:#d97706; color:#fff; border-radius:8px; text-decoration:none; font-weight:700;">
               📥 응답 데이터(JSON) 파일 다운로드
            </a>
          </div>
        `;
      }}

      box.innerHTML = html;
      window.scrollTo({{ top: 0, behavior: "smooth" }});
    }}

    window.addEventListener("DOMContentLoaded", parseUrlParams);
  </script>
</body>
</html>
"""
    return html_template


def build_and_save_frontend():
    load_dotenv(override=True)
    sb_url = os.getenv("SUPABASE_URL", "").strip()
    sb_key = os.getenv("SUPABASE_ANON_KEY", "").strip()
    out_dir = Path(__file__).parent / "frontend"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "index.html"
    html_content = generate_frontend_html(sb_url, sb_key)
    out_file.write_text(html_content, encoding="utf-8")
    return out_file


if __name__ == "__main__":
    saved_path = build_and_save_frontend()
    print(f"Frontend generated at: {saved_path}")

