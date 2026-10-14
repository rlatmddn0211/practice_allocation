import React, { useState } from "react";
import { DataComponent, DataTable, EvidenceChart, ReportSection, RichNarrative,
  SegmentedControl, useDataApp } from "../../data-app-public.jsx";
import { prose } from "./prose.js";

const ORDER = ["U", "F_DO", "F_DC", "F_WO", "F_WC"];
const LABEL = { U: "Uniform", F_DO: "DO 집중", F_DC: "DC 집중", F_WO: "WO 집중", F_WC: "WC 집중",
  DC_plus_WO_minus: "DC+ / WO−", DC_minus_WO_plus: "DC− / WO+" };
const RULE = { Uniform: "Uniform", Failure: "실패율 기준", Progress: "최근 진전 기준", Fixed_DC: "DC 고정",
  LOSO_global_fixed: "다른 seed로 고른 고정 배분", LOSO_time_fixed: "다른 seed로 고른 시점별 배분",
  cross_repeat_diagnostic: "다른 반복으로 고른 배분*" };
const signed = n => `${n > 0 ? "+" : ""}${n.toFixed(2)}`;
const num = (field, label, sign = false) => ({field, label, deltaTone: "neutral",
  renderCell: v => typeof v === "number" ? (sign ? signed(v) : v.toFixed(2)) : v});
const txt = (field, label) => ({field, label});
const allocColumn = {field: "allocation", label: "배분", renderCell: v => LABEL[v] || v};
const taskColumns = ["DO", "DC", "WO", "WC"].map(t => num(`${t}_pct`, `${t} (%)`));
const orderRows = rows => [...rows].sort((a,b) => ORDER.indexOf(a.allocation)-ORDER.indexOf(b.allocation));

function Narrative({id, title, sources, value}) {
  const {visible} = useDataApp();
  const ids = Object.keys(sources);
  if (!visible(id)) return null;
  return <ReportSection id={id} title={title} queryId={ids[0]} queryIds={ids}
    sourceRowsByQuery={sources} showHeading={false}>
    <RichNarrative id={`${id}:body`} className="report-analysis" value={value} />
  </ReportSection>;
}
function Table({id, title, query, rows, sourceRows = rows, columns, description, controls}) {
  const {visible} = useDataApp();
  if (!visible(id)) return null;
  return <DataComponent id={id} title={title} kind="table" queryId={query} displayRows={rows}
    sourceRows={sourceRows} description={description} headerControls={controls}>
    <DataTable rows={rows} columns={columns} label={title} searchable={false} compactNumbers={false} />
  </DataComponent>;
}
export function ReportContent() {
  const {snapshot, appTitle, setAppTitle, canEdit, mode} = useDataApp();
  const q = id => snapshot.queries[id].rows;
  const [checkpoint, setCheckpoint] = useState("all");
  const e0 = orderRows(q("e0").filter(r => r.cohort === "replication_1903_1905"));
  const e1 = orderRows(q("e1").filter(r => r.horizon === 40000));
  const bases = q("baselines").filter(r => r.stage === "E1");
  const seeds = q("seed_effects").filter(r => r.stage === "E1" && r.horizon === 40000);
  const e1Display = e1.map(r => ({...r, seed11: seeds.find(s => s.allocation === r.allocation && s.original_seed === 11).macro_vs_U_pp,
    seed12: seeds.find(s => s.allocation === r.allocation && s.original_seed === 12).macro_vs_U_pp,
    seed13: seeds.find(s => s.allocation === r.allocation && s.original_seed === 13).macro_vs_U_pp}));
  const allContexts = q("context").filter(r => r.stage === "E1" && r.horizon === 40000);
  const contexts = allContexts.filter(r => checkpoint === "all" || r.checkpoint_step === checkpoint);
  const contextDisplay = contexts.filter(r => r.allocation === "U").map(r => {
    const matches = contexts.filter(s => s.original_seed === r.original_seed && s.checkpoint_step === r.checkpoint_step);
    return {context: `${r.original_seed} · ${r.checkpoint_step / 1000}k`, Uniform: r.macro_pct,
      ...Object.fromEntries(ORDER.slice(1).map(a => [a, matches.find(s => s.allocation === a).macro_vs_U_pp]))};
  });
  const tradeoffs = orderRows(q("task_tradeoffs"));
  const tradeoffPlot = tradeoffs.filter(r => r.allocation !== "U").flatMap(r => ["DO", "DC", "WO", "WC"].map(t => ({allocation: LABEL[r.allocation], task: t, "차이 (%p)": r[`${t}_vs_U_pp`]})));
  const temporal = orderRows(q("temporal"));
  const temporalPlot = temporal.filter(r => r.allocation !== "U").flatMap(r => [
    {allocation: LABEL[r.allocation], budget: "+20k", "차이 (%p)": r.gain20_vs_U},
    {allocation: LABEL[r.allocation], budget: "+40k", "차이 (%p)": r.gain40_vs_U}]);
  const rules = q("rules").filter(r => r.horizon === 40000).map(r => ({...r,
    gain20: q("rules").find(s => s.rule === r.rule && s.horizon === 20000).gain_vs_U_pp}));
  const e2 = q("e2").filter(r => r.horizon === 40000).sort((a,b) => ["U", "DC_plus_WO_minus", "DC_minus_WO_plus"].indexOf(a.allocation)-["U", "DC_plus_WO_minus", "DC_minus_WO_plus"].indexOf(b.allocation));
  const e2Plot = q("e2_contrast").map(r => ({seed: `seed ${r.seed}`, budget: `+${r.horizon/1000}k`, "DO 차이 (%p)": r.DO_DCplus_minus_WOplus_pp}));
  const donorSources = {e2,e2_contrast:q("e2_contrast"),baselines:q("baselines").filter(r=>r.stage==="E2")};
  return <article className="report-content research-report" aria-label="E0 E1 E2 연구 결과 상세 보고서">
    <header className="report-hero">
      <h1 data-data-app-title contentEditable={canEdit && mode === "edit"} suppressContentEditableWarning
        onBlur={canEdit && mode === "edit" ? e => setAppTitle(e.currentTarget.textContent.trim() || appTitle) : undefined}>{appTitle}</h1>
      <RichNarrative id="report:deck" className="report-deck" value="공유 SAC · 4개 과제 · 완료된 E0–E2 전체 결과\n\n독립 사전학습 seed, 출발 checkpoint, 추가 연습량, 과제별 손익을 분리한 분석입니다. 모든 수치는 성공률 또는 성공률 차이이며 보상 합계와 구분합니다." />
    </header>
    <Narrative id="main-finding" title="현재 지지되는 결론" sources={{primary:q("primary"),rules:q("rules")}} value={prose.summary} />
    <Table id="primary-table" title="사전에 정한 주 비교 · 추가 연습 40k" query="primary" rows={q("primary")} columns={[
      txt("stage","실험"),{field:"contrast",label:"비교 / 측정 과제",renderCell:(v,r)=>r.stage==="E2"?"DC+ − WO+ / DO":"DC 집중 − U / macro"},num("mean_pp","평균 차이 (%p)",true),
      {field:"n_original",label:"사전학습 seed 수"},{field:"seed_values_pp",label:"seed별 차이 (%p)",renderCell:v=>v.map(signed).join(" / ")}
    ]} description="E0: 확인용 continuation 1903–1905, 부모 seed 901 하나. E1/E2: 원래 seed 11/12/13에 동일 가중." />
    <Narrative id="design" title="무엇을 비교했는가" sources={{costs:q("costs"),baselines:q("baselines")}} value={prose.design} />
    <Narrative id="e0-finding" title="E0: 새 평가에서도 남은 효과와 측정 민감도" sources={{e0:q("e0"),diagnostics:q("diagnostics").filter(r=>r.stage==="E0"),e0_failure:q("e0_failure")}} value={prose.e0} />
    <Table id="e0-results" title="E0 확인용 반복 3개 · 최종 성공률과 U 대비 차이" query="e0" rows={e0}
      columns={[allocColumn,num("macro_pct","Macro (%)"),num("macro_vs_U_pp","U 대비 (%p)",true),...taskColumns]}
      description="동일 P0 seed 901, 200k 출발, +40k 끝점. 발견용 1901/1902는 제외." />
    <Narrative id="baseline-finding" title="E1: 출발 정책의 이질성" sources={{baselines:bases}} value={prose.baseline} />
    <Table id="baseline-table" title="E1 부모 정책 · 분기 시작 전 outcome 성공률 (%)" query="baselines" rows={bases}
      columns={[{field:"seed",label:"원래 seed"},{field:"checkpoint",label:"출발 step",renderCell:v=>`${v/1000}k`},num("macro_pct","Macro"),...taskColumns]} />
    <Narrative id="e1-primary-finding" title="E1: DC 일반 우위는 재현되지 않았다" sources={{e1,seed_effects:seeds}} value={prose.e1} />
    <Table id="e1-mean-seeds" title="E1 +40k · 평균과 원래 seed별 U 대비 차이" query="seed_effects" rows={e1Display} sourceRows={seeds}
      columns={[allocColumn,num("macro_pct","Macro (%)"),num("macro_vs_U_pp","평균 (%p)",true),num("seed11","seed 11",true),num("seed12","seed 12",true),num("seed13","seed 13",true)]} />
    <Narrative id="context-finding" title="출발 checkpoint별로 배분 순위가 바뀐다" sources={{context:allContexts,checkpoint_interaction:q("checkpoint_interaction")}} value={prose.context} />
    <Table id="context-table" title="E1 출발점별 +40k · U는 성공률 %, 나머지는 U 대비 %p" query="context" rows={contextDisplay} sourceRows={contexts}
      controls={<SegmentedControl ariaLabel="출발 checkpoint 선택" value={checkpoint} onChange={setCheckpoint}
        options={[{value:"all",label:"전체"},{value:200000,label:"200k"},{value:400000,label:"400k"}]} />}
      columns={[txt("context","seed · 출발점"),num("Uniform","U (%)"),...ORDER.slice(1).map(a=>num(a,LABEL[a],true))]} />
    <Narrative id="task-finding" title="평균 안의 과제별 이득과 손실" sources={{task_tradeoffs:tradeoffs,risk:q("risk"),seed_effects:seeds,baselines:bases}} value={prose.tasks} />
    <EvidenceChart id="task-tradeoffs" queryId="task_tradeoffs" title="E1 +40k · 과제별 U 대비 성공률 차이 (%p)"
      rows={tradeoffPlot} sourceRows={tradeoffs.filter(r=>r.allocation!=="U")} height={350}
      spec={{type:"bar",x:"allocation",y:"차이 (%p)",series:"task",stackable:false,startAtZero:true,valueDecimals:2}}
      description="원래 seed 3개, 출발 checkpoint 2개, continuation 3개. 네 과제 막대의 평균이 macro 차이." />
    <Table id="task-absolute-table" title="E1 +40k · 과제별 최종 성공률 (%)" query="task_tradeoffs" rows={tradeoffs}
      columns={[allocColumn,...taskColumns,num("macro_pct","Macro (%)")]} />
    <Narrative id="budget-finding" title="20k와 40k의 결론은 다르다" sources={{temporal}} value={prose.budget} />
    <EvidenceChart id="budget-chart" queryId="temporal" title="E1 · 추가 20k와 40k에서의 U 대비 차이 (%p)"
      rows={temporalPlot} sourceRows={temporal.filter(r=>r.allocation!=="U")} height={330}
      spec={{type:"bar",x:"allocation",y:"차이 (%p)",series:"budget",stackable:false,startAtZero:true,valueDecimals:2}} />
    <Narrative id="selector-finding" title="실패율, 진전, 고정 규칙과 반복 간 선택" sources={{rules:q("rules"),diagnostics:q("diagnostics").filter(r=>r.stage==="E1"),rule_choices:q("rule_choices")}} value={prose.rules} />
    <Table id="rules-table" title="E1 선택 규칙 · Uniform 대비 macro 차이 (%p)" query="rules" rows={rules} sourceRows={q("rules")}
      columns={[{field:"rule",label:"규칙",renderCell:v=>RULE[v]},num("gain20","+20k",true),num("gain_vs_U_pp","+40k",true),num("seed_11_pp","40k seed 11",true),num("seed_12_pp","40k seed 12",true),num("seed_13_pp","40k seed 13",true)]}
      description="*다른 반복으로 고른 배분은 사후 진단. 실제 사전 선택기나 oracle 상한이 아님." />
    <Narrative id="e2-finding" title="E2: DO 예산을 고정한 donor 교환" sources={donorSources} value={prose.e2} />
    <Table id="e2-absolute-table" title="E2 +40k · 최종 성공률과 U 대비 차이" query="e2" rows={e2}
      columns={[allocColumn,num("macro_pct","Macro (%)"),num("macro_vs_U_pp","U 대비 (%p)",true),...taskColumns]} />
    <EvidenceChart id="e2-seed-chart" queryId="e2_contrast" title="E2 주 비교 · DO 성공률 DC+ − WO+ (%p)"
      rows={e2Plot} sourceRows={q("e2_contrast")} height={330}
      spec={{type:"bar",x:"seed",y:"DO 차이 (%p)",series:"budget",stackable:false,startAtZero:true,valueDecimals:2}}
      description="양수: DC를 더 연습한 쪽이 유리. 음수: WO를 더 연습한 쪽이 유리. 독립 원래 seed 3개, 각 continuation 3개 평균." />
    <Narrative id="research-judgment" title="연구적으로 남는 것과 남지 않는 것" sources={{primary:q("primary"),e1,e2,rules:q("rules"),task_tradeoffs:tradeoffs}} value={prose.judgment} />
    <Narrative id="uncertainty" title="추론 범위와 검증" sources={{primary:q("primary"),costs:q("costs")}} value={prose.uncertainty} />
    <Table id="cost-table" title="완료 범위와 실제 기록 비용" query="costs" rows={q("costs")} columns={[
      txt("stage","실험"),{field:"completed_jobs",label:"완료 작업"},{field:"training_steps",label:"학습 step"},
      {field:"evaluation_episodes",label:"평가 에피소드"},num("sum_job_wall_hours","작업 시간 합 (h)")
    ]} description="E0–E2: 학습 5.88M step, 평가 112,800회. 시간은 완료 작업 내부 합이며 queue 대기·구현 검증·실패 시도 제외. 금전 비용 미계측." />
  </article>;
}
