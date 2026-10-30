// 신용평가 프로젝트 요약 3장 덱 (pptxgenjs)
const pptxgen = require("pptxgenjs");
const { applyTheme } = require("/root/.claude/skills/synced/9c0687c6-062d-46a6-9d48-5a42e34a50b6_c78fdb90-5c9a-491e-9c01-033150b6f9ed/pptx/scripts/apply_theme.js");

const FONT = "Malgun Gothic";
const THEME = {
  name: "Credit Ink",
  headFontFace: FONT, bodyFontFace: FONT,
  colors: {
    dk1: "15202B", lt1: "FFFFFF", dk2: "0E3B43", lt2: "EEF4F3",
    accent1: "1F7A73", accent2: "E4572E", accent3: "8FB8B2", accent4: "F2C14E",
    accent5: "5B6B7A", accent6: "2E4057", hlink: "1F7A73", folHlink: "5B6B7A",
  },
};
const HEX = THEME.colors;

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625
pres.theme = { headFontFace: FONT, bodyFontFace: FONT };
pres.title = "신용평가 스코어카드 프로젝트 요약";
const C = pres.SchemeColor;

pres.defineSlideMaster({
  title: "DARK",
  background: { color: HEX.dk2 },
  objects: [{ placeholder: { options: { name: "title", type: "title", x: 0.5, y: 0.45, w: 9, h: 1.0,
    fontSize: 28, bold: true, color: C.background1, valign: "top", margin: 0 }, text: "" } }],
});
pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: HEX.lt1 },
  objects: [{ placeholder: { options: { name: "title", type: "title", x: 0.5, y: 0.3, w: 9, h: 0.6,
    fontSize: 24, bold: true, color: C.text2, valign: "middle", margin: 0 }, text: "" } }],
  slideNumber: { x: 9.2, y: 5.25, w: 0.4, h: 0.25, fontSize: 9, color: C.accent5, fontFace: FONT },
});

const txt = (slide, text, o) => slide.addText(text, { isTextBox: true, fontFace: FONT, margin: 0, ...o });
const card = (slide, o) => slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { rectRadius: 0.08, line: { type: "none" }, ...o });

// ───────────────────────── 1. 표지 + 핵심 결과
pres.addSection({ title: "요약" });
{
  const s = pres.addSlide({ masterName: "DARK", sectionTitle: "요약" });
  s.addText("AUC보다 중요한 건\n‘몇 점부터 승인할까’였다", { placeholder: "title" });
  txt(s, "15만 명 대출 데이터로 신용평가 스코어카드를 만들고, 승인 기준점의 손익을 분석해 웹 서비스로 배포", {
    x: 0.5, y: 1.55, w: 9, h: 0.4, fontSize: 13, color: C.accent3, objectName: "subtitle" });

  const stats = [
    ["0.858", "스코어카드 AUC", "LightGBM 0.869와 근접"],
    ["2.4%", "승인자 부도율", "승인율 80% 시 (원래 6.7%)"],
    ["71%", "사전 차단한 부도자", "558점 이상만 승인할 때"],
    ["+29%", "1인당 손익 개선", "손익 최대 기준점 539점"],
  ];
  stats.forEach(([big, label, sub], i) => {
    const x = 0.5 + i * 2.3;
    card(s, { x, y: 2.2, w: 2.1, h: 1.6, fill: { color: "174A52" }, objectName: `stat${i}` });
    txt(s, big, { x: x + 0.2, y: 2.32, w: 1.8, h: 0.7, fontSize: 32, bold: true,
      color: i === 3 ? C.accent4 : C.background1 });
    txt(s, label, { x: x + 0.2, y: 3.02, w: 1.8, h: 0.3, fontSize: 13, bold: true, color: C.background1 });
    txt(s, sub, { x: x + 0.2, y: 3.34, w: 1.8, h: 0.3, fontSize: 10, color: C.accent3 });
  });

  const steps = ["구간화", "WoE", "로지스틱", "점수표", "기준점 손익", "웹 앱", "로그·A/B"];
  const w = 1.16, gap = 0.15;
  steps.forEach((t, i) => {
    const x = 0.5 + i * (w + gap);
    card(s, { x, y: 4.15, w, h: 0.5, fill: { color: i === 3 ? HEX.accent4 : "2A5C63" }, objectName: `step${i}` });
    txt(s, `${i + 1}  ${t}`, { x, y: 4.15, w, h: 0.5, fontSize: 11, bold: true, align: "center", valign: "middle",
      color: i === 3 ? C.text1 : C.background1 });
  });
  txt(s, "데이터: Kaggle “Give Me Some Credit” (2011, 미국 대출자 150,000명) · 방법론: Siddiqi, Intelligent Credit Scoring (2017)", {
    x: 0.5, y: 5.0, w: 9, h: 0.3, fontSize: 9, color: C.accent3, objectName: "source" });
  s.addNotes("핵심: 성능 지표보다 '몇 점부터 승인할지'라는 의사결정에 집중했다. 4개 수치가 결론이고, 아래 7단계가 진행 흐름이다. 4번 점수표가 분석과 서비스를 연결한다.");
}

// ───────────────────────── 2. 모델 원리
pres.addSection({ title: "모델" });
{
  const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "모델" });
  s.addText("점수표 하나로 ‘왜 이 점수인지’ 설명할 수 있다", { placeholder: "title" });

  // 왼쪽: 구간별 부도율 차트
  card(s, { x: 0.5, y: 1.05, w: 4.3, h: 3.2, fill: { color: HEX.lt2 }, objectName: "chartBg" });
  s.addChart(pres.charts.BAR, [{ name: "부도율",
    labels: ["0~19%", "19~40%", "40~67%", "67~87%", "87~100%", "100%+"],
    values: [2.0, 4.2, 8.7, 13.7, 19.1, 38.1] }], {
    x: 0.6, y: 1.1, w: 4.1, h: 3.1, barDir: "col", objectName: "badRateChart",
    showTitle: true, title: "리볼빙 사용률 구간별 부도율 (%)", titleFontSize: 12, titleColor: HEX.dk2, titleFontFace: "+mn-lt",
    chartColors: [HEX.accent1, HEX.accent1, HEX.accent1, HEX.accent1, HEX.accent2, HEX.accent2],
    showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 10, dataLabelColor: HEX.dk1, dataLabelFontFace: "+mn-lt",
    catAxisLabelFontSize: 10, catAxisLabelColor: HEX.accent5, catAxisLabelFontFace: "+mn-lt",
    valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" }, showLegend: false,
    barGapWidthPct: 60,
  });

  // 오른쪽: 3단계 설명
  const items = [
    ["1", "구간화", "의사결정나무가 부도율이 갈리는 지점을 찾아 구간을 나눈다. 이상치·결측·특수코드가 자연스럽게 처리된다."],
    ["2", "WoE + 로지스틱", "구간을 위험도 값(WoE)으로 바꿔 학습한다. 계수 부호가 거꾸로 나온 변수 1개는 제거했다."],
    ["3", "점수 스케일링", "600점 = 정상:부도 50:1, 20점마다 odds 2배. 총점은 구간 점수의 합이다."],
  ];
  items.forEach(([n, head, body], i) => {
    const y = 1.05 + i * 0.95;
    s.addShape(pres.shapes.OVAL, { x: 5.1, y: y + 0.05, w: 0.42, h: 0.42, fill: { color: HEX.accent1 }, line: { type: "none" }, objectName: `num${n}` });
    txt(s, n, { x: 5.1, y: y + 0.05, w: 0.42, h: 0.42, fontSize: 14, bold: true, color: C.background1, align: "center", valign: "middle" });
    txt(s, head, { x: 5.7, y, w: 3.8, h: 0.3, fontSize: 14, bold: true, color: C.text2 });
    txt(s, body, { x: 5.7, y: y + 0.3, w: 3.8, h: 0.6, fontSize: 11, color: C.text1, valign: "top" });
  });
  card(s, { x: 5.1, y: 3.9, w: 4.4, h: 0.35, fill: { color: "FDEDE8" }, objectName: "example" });
  txt(s, [{ text: "예) ", options: { bold: true, color: C.accent2 } },
           { text: "사용률 95%→19%로 낮추면 41점→85점, ", options: {} },
           { text: "+44점", options: { bold: true, color: C.accent2 } }],
      { x: 5.25, y: 3.9, w: 4.2, h: 0.35, fontSize: 11, color: C.text1, valign: "middle" });

  // 하단: 모델 비교
  const rows = [
    [{ text: "", options: {} }, "AUC", "KS", "승인율 80% 시 승인된 부도자", "1인당 손익", "설명 가능성"],
    ["스코어카드 (운영)", "0.858", "0.560", "577명", "0.670", "구간별 점수표"],
    ["LightGBM (챌린저)", "0.869", "0.583", "537명 (−40)", "0.675 (+0.8%)", "별도 해석 도구 필요"],
  ];
  s.addTable(rows.map((r, ri) => r.map((c, ci) => (typeof c === "string" ? { text: c, options: {
    bold: ri === 0 || ci === 0, color: ri === 0 ? HEX.lt1 : HEX.dk1,
    fill: { color: ri === 0 ? HEX.dk2 : ri === 1 ? HEX.lt2 : HEX.lt1 } } } : c))),
    { x: 0.5, y: 4.4, w: 9, colW: [1.7, 0.8, 0.8, 2.2, 1.6, 1.9], rowH: 0.24, fontSize: 10, fontFace: FONT,
      border: { type: "solid", pt: 0.5, color: "D5DEDD" }, valign: "middle", margin: [0.02, 0.08, 0.02, 0.08], objectName: "compare" });
  s.addNotes("스코어카드는 점수가 구간 점수의 합이라 '왜 이 점수인지'를 바로 설명할 수 있다. LightGBM은 AUC가 0.011 높지만 같은 승인율에서 부도자를 3만 명당 40명 더 막는 정도(손익 +0.8%)라, 설명 가능한 스코어카드를 운영 모델로 권고했다.");
}

// ───────────────────────── 3. 비즈니스 + 서비스
pres.addSection({ title: "의사결정과 서비스" });
{
  const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "의사결정과 서비스" });
  s.addText("승인율 목표는 감이 아니라 손실 구조에서 정한다", { placeholder: "title" });

  const cut = [440,445,450,455,460,465,470,475,480,485,490,495,500,505,510,515,520,525,530,535,540,545,550,555,560,565,570,575,580,585,590,595,600,605,610,615,620];
  const prof = [0.5434,0.5452,0.5473,0.5511,0.5559,0.5604,0.5672,0.5735,0.5818,0.5866,0.5973,0.6094,0.6178,0.6266,0.637,0.6469,0.6586,0.6692,0.6753,0.6822,0.6859,0.6869,0.6785,0.671,0.6639,0.6446,0.6211,0.5943,0.5639,0.5268,0.4881,0.4311,0.3681,0.2999,0.2018,0.1157,0.0487];
  card(s, { x: 0.5, y: 1.05, w: 4.6, h: 2.75, fill: { color: HEX.lt2 }, objectName: "lineBg" });
  s.addChart(pres.charts.LINE, [{ name: "1인당 손익", labels: cut.map(String), values: prof }], {
    x: 0.6, y: 1.1, w: 4.4, h: 2.65, objectName: "profitChart",
    showTitle: true, title: "기준점별 1인당 손익 (정상 +1, 부도 −6 가정)", titleFontSize: 11, titleColor: HEX.dk2, titleFontFace: "+mn-lt",
    chartColors: [HEX.accent1], lineSize: 2.5, lineDataSymbol: "none", showLegend: false,
    catAxisLabelFontSize: 9, catAxisLabelColor: HEX.accent5, catAxisLabelFontFace: "+mn-lt", catAxisLabelFrequency: 4,
    valAxisLabelFontSize: 9, valAxisLabelColor: HEX.accent5, valAxisLabelFontFace: "+mn-lt", valAxisLabelFormatCode: "0.0",
    valAxisMinVal: 0, valAxisMaxVal: 0.8, valGridLine: { color: "D5DEDD", size: 0.5 }, catGridLine: { style: "none" },
  });

  // 오른쪽: 정책 비교
  const pol = [
    ["전원 승인", "100%", "6.7%", "0.532", HEX.lt1, HEX.dk1],
    ["80% 정책 (558점↑)", "80%", "2.4%", "0.670 (+26%)", HEX.lt2, HEX.dk1],
    ["손익 최대 (539점↑)", "90%", "3.4%", "0.686 (+29%)", HEX.accent1, HEX.lt1],
  ];
  s.addTable([
    ["정책", "승인율", "부도율", "1인당 손익"].map(t => ({ text: t, options: { bold: true, color: HEX.lt1, fill: { color: HEX.dk2 } } })),
    ...pol.map(([a, b, c, d, bg, fg]) => [a, b, c, d].map((t, i) => ({ text: t, options: {
      bold: i === 0 || bg === HEX.accent1, color: fg, fill: { color: bg } } }))),
  ], { x: 5.4, y: 1.05, w: 4.1, colW: [1.75, 0.6, 0.6, 1.15], rowH: 0.34, fontSize: 10, fontFace: FONT,
       border: { type: "solid", pt: 0.5, color: "D5DEDD" }, valign: "middle", margin: [0.03, 0.08, 0.03, 0.08], objectName: "policy" });
  txt(s, [
    { text: "80%가 최적이려면 부도 손실이 이익의 약 10배여야 한다.", options: { bold: true, color: C.accent2, breakLine: true } },
    { text: "기준점은 검증셋에서 고르고 테스트셋에서 측정했으며, 손실 비율 3~15배 민감도 분석으로 가정을 보완했다.", options: {} },
  ], { x: 5.4, y: 2.75, w: 4.1, h: 1.05, fontSize: 11, color: C.text1, valign: "top", paraSpaceAfter: 4 });

  // 하단: 서비스 파이프라인
  txt(s, "서비스로 확장: 실사용자 데이터 기반 개선", { x: 0.5, y: 3.98, w: 9, h: 0.3, fontSize: 13, bold: true, color: C.text2 });
  const flow = [
    ["웹 시뮬레이터", "점수·등급·점수 올리는 법"],
    ["이벤트 로그", "방문·계산·피드백 (익명)"],
    ["A/B 테스트", "점수 중심 vs 개선 팁 먼저"],
    ["SQL 분석", "퍼널·리텐션·z-검정"],
  ];
  flow.forEach(([h, b], i) => {
    const x = 0.5 + i * 2.3;
    card(s, { x, y: 4.35, w: 2.05, h: 0.75, fill: { color: i === 2 ? "FDEDE8" : HEX.lt2 }, objectName: `flow${i}` });
    txt(s, h, { x: x + 0.15, y: 4.42, w: 1.8, h: 0.28, fontSize: 12, bold: true, color: i === 2 ? C.accent2 : C.text2 });
    txt(s, b, { x: x + 0.15, y: 4.7, w: 1.8, h: 0.3, fontSize: 9.5, color: C.text1 });
    if (i < 3) txt(s, "›", { x: x + 2.05, y: 4.35, w: 0.25, h: 0.75, fontSize: 18, color: C.accent5, align: "center", valign: "middle" });
  });
  txt(s, "+5%p 차이 검출에는 군당 약 1,400명이 필요하다. 표본이 부족하면 판정을 미루고 기간을 늘린다.", {
    x: 0.5, y: 5.18, w: 8.5, h: 0.25, fontSize: 9.5, color: C.accent5, italic: true });
  s.addNotes("가정(정상 +1, 부도 −6)에서 손익 최대점은 539점, 승인율 약 90%다. 흔히 쓰는 80% 목표는 손실이 이익의 10배 정도일 때만 최적이다. 이 점수표를 웹 앱으로 배포해 이벤트 로그를 쌓고, A/B 테스트로 개선 효과를 검증한다.");
}

(async () => {
  const out = "/home/claude/credit-scoring/docs/신용평가_프로젝트_요약.pptx";
  await pres.writeFile({ fileName: out });
  await applyTheme(out, THEME);
  console.log("written", out);
})();
