import React, { useState } from "react";
import { DataComponent, DataTable, EvidenceChart, ReportSection, RichNarrative, useDataApp } from "../../data-app-public.jsx";

const candidates = ["U", "F_DO", "F_DC", "F_WO", "F_WC"];
const average = (rows, field) => rows.reduce((sum, row) => sum + row[field], 0) / rows.length;
const numberColumn = (field, label, signed = false) => ({ field, label, deltaTone: "neutral",
  renderCell: value => `${signed && value > 0 ? "+" : ""}${Number(value).toFixed(2)}` });
const allocationColumn = { field: "allocation", label: "배분" };
const seedColumn = { field: "seed", label: "후속 seed", renderCell: value => String(value) };
function Narrative({ id, queryId, rows, text }) {
  return <ReportSection id={id} title="분석" queryId={queryId} sourceRows={rows} showHeading={false}>
    <RichNarrative id={`${id}:body`} value={text} label="분석 문장 편집" />
  </ReportSection>;
}
function EvidenceTable({ id, title, queryId, sourceRows, rows, columns, controls }) {
  return <DataComponent id={id} title={title} queryId={queryId} kind="table" sourceRows={sourceRows} displayRows={rows}>
    <DataTable rows={rows} columns={columns} searchable={false} compactNumbers={false} caption={title} toolbarControls={controls} />
  </DataComponent>;
}
export function ReportContent() {
  const { reviewedRows, appTitle, canEdit, mode, setAppTitle, visible } = useDataApp();
  const [seed, setSeed] = useState("all");
  const all = reviewedRows("branches");
  const cohorts = reviewedRows("cohorts");
  const secondary = reviewedRows("secondary");
  const contributions = reviewedRows("contributions").filter(r => r.cohort === "replication");
  const budgets = reviewedRows("budgets").filter(r => r.cohort === "replication");
  const primary = all.filter(r => r.cohort === "replication" && r.horizon === 40000);
  const confirmation = cohorts.filter(r => r.cohort === "replication");
  const table = candidates.map(candidate => {
    const group = primary.filter(r => r.candidate === candidate);
    return { allocation: group[0].allocation, s1903: group.find(r => r.seed === 1903).macro_pct,
      s1904: group.find(r => r.seed === 1904).macro_pct, s1905: group.find(r => r.seed === 1905).macro_pct,
      mean: average(group, "macro_pct"), delta: average(group, "delta_pp"), wins: candidate === "U" ? "기준" : `${group.filter(r => r.delta_pp > 0).length}/3` };
  });
  const effectRows = primary.filter(r => r.candidate !== "U").map(r => ({ ...r, repeat: String(r.seed), "집중 과제": r.allocation.replace(" 집중", ""), "균등 대비 차이 (%p)": r.delta_pp }));
  const selected = primary.filter(r => seed === "all" || String(r.seed) === seed);
  const taskTable = candidates.map(candidate => {
    const group = selected.filter(r => r.candidate === candidate);
    return { allocation: group[0].allocation, ...Object.fromEntries(["DO", "DC", "WO", "WC", "macro_pct"].map(t => [t, average(group, t)])) };
  });
  const history = candidates.map(candidate => {
    const lookup = cohort => cohorts.find(r => r.cohort === cohort && r.candidate === candidate);
    return { allocation: lookup("replication").allocation, discovery: lookup("discovery").macro_pct,
      replication: lookup("replication").macro_pct, combined: lookup("combined_descriptive").macro_pct,
      delta: lookup("combined_descriptive").delta_pp, wins: candidate === "U" ? "기준" : `${lookup("combined_descriptive").wins}/5` };
  });
  const budgetTable = candidates.map(candidate => {
    const early = budgets.find(r => r.candidate === candidate && r.horizon === 20000);
    const late = budgets.find(r => r.candidate === candidate && r.horizon === 40000);
    return { allocation: early.allocation, at20: early.macro_pct, at40: late.macro_pct, delta20: early.delta_pp, delta40: late.delta_pp };
  });
  const contrast = secondary.map(r => ({ ...r, cohortLabel: r.cohort === "replication" ? "새 반복" : "기존 발견" }));
  const wc = contrast.filter(r => r.cohort === "replication").map(r => ({ ...r, result: r.WC_dip_recovery ? "하락 후 회복" : "재현 안 됨" }));
  const contributionTable = candidates.filter(c => c !== "U").map(candidate => {
    const group = contributions.filter(r => r.candidate === candidate);
    return { allocation: group[0].allocation, ...Object.fromEntries(group.map(r => [r.task, r.macro_contribution_pp])),
      total: group.reduce((s, r) => s + r.macro_contribution_pp, 0) };
  });
  return <article className="report-content replication-report" aria-label="연습 배분 재현성 실험 분석">
    <header className="report-hero">
      <h1 data-data-app-title contentEditable={canEdit && mode === "edit"} suppressContentEditableWarning
        onBlur={canEdit && mode === "edit" ? e => setAppTitle(e.currentTarget.textContent.trim() || appTitle) : undefined}>{appTitle}</h1>
    </header>
    {visible("replication-summary") && <Narrative id="replication-summary" queryId="cohorts" rows={confirmation}
      text={`**새 후속 seed 1903·1904·1905의 확인 결과입니다.**

- 추가 40k에서 서랍닫기 집중은 균등 대비 **+6.00%p**, 창문열기 집중은 **+6.33%p**였습니다. 두 배분 모두 새 3개 seed에서 균등을 앞섰습니다.
- 실패율 기준으로 사전에 선택한 서랍열기 집중은 **+0.33%p**, 1승·2패였습니다. 최근 진행량 기준 창문닫기 집중은 +5.17%p, 2승·1패였습니다.
- 이 결과는 이 200k 출발점에서 실패율만으로 좋은 배분을 보장하기 어렵다는 근거입니다. 적응형 선택기나 추가 상태 정보의 효과는 아직 검증하지 않았습니다.`} />}
    {visible("primary-results") && <EvidenceTable id="primary-results" title="새 3개 seed의 40k 평균 성공률 (%)" queryId="branches" sourceRows={primary} rows={table}
      columns={[allocationColumn, numberColumn("s1903", "1903"), numberColumn("s1904", "1904"), numberColumn("s1905", "1905"),
        numberColumn("mean", "평균"), numberColumn("delta", "균등 대비 %p", true), { field: "wins", label: "균등보다 높음" }]} />}
    <Narrative id="baseline-context" queryId="branches" rows={primary}
      text={`공통 출발점의 평균 성공률은 48.5%였습니다(서랍열기 6%, 서랍닫기 100%, 창문열기 4%, 창문닫기 84%). 서랍닫기 집중의 시작점 대비 평균 개선은 +6.50%p, 창문열기 집중은 +6.83%p입니다. 두 배분은 각 seed에서도 모두 출발점보다 높았습니다.

실패율 규칙은 결과 평가와 다른 **공개 진단 20사례**에서 서랍열기를 골랐습니다. 결과 평가 50사례의 최하위 과제를 보고 선택을 바꾸지 않았습니다.`} />
    {visible("replication-effect") && <EvidenceChart id="replication-effect" queryId="branches" title="집중 배분의 균등 대비 차이 (%p): 후속 seed별 비교"
      rows={effectRows} sourceRows={primary.filter(r => r.candidate !== "U")}
      spec={{ type: "bar", x: "집중 과제", y: "균등 대비 차이 (%p)", series: "repeat", stackable: false,
        colors: { "1903": "#285f94", "1904": "#b26b22", "1905": "#67753b" }, valueDecimals: 2 }} height={360} />}
    <Narrative id="outlier-context" queryId="branches" rows={primary}
      text={`seed 1904의 균등 배분은 **42.0%로 시작점보다 6.5%p 하락**했습니다. 따라서 그 seed에서의 큰 상대 이득에는 균등 배분의 성능 하락을 피한 효과도 포함됩니다.

탐색적 민감도 확인으로 seed 1904를 계산에서 잠시 제외해도, 나머지 두 seed의 균등 대비 평균 차이는 서랍닫기 집중 **+5.0%p**, 창문열기 집중 **+2.0%p**입니다. 본 결과에서는 어떤 seed도 제외하지 않았습니다. 새 seed 평균 1위는 창문열기 집중이지만 서랍닫기 집중과 차이는 **0.33%p**이며, 확정적인 우열을 주장하지 않습니다.`} />
    <Narrative id="drawer-finding" queryId="secondary" rows={secondary}
      text={`**가장 분명하게 반복된 보조 관찰은 서랍열기의 반응 차이입니다.** 서랍닫기 집중 배분에서 서랍열기 성공률이 서랍열기 자체를 집중한 배분보다 새 3개 seed 모두 높았습니다. 기존 발견용 두 seed를 포함하면 관측 방향은 5/5에서 같았습니다.

서랍닫기는 출발점의 평가에서 이미 100%였습니다. 그래도 그 과제에 더 배분한 조건이 다른 과제의 성능에 유리할 수 있다는 관찰입니다. 새 경험의 구성과 다른 과제의 연습량이 함께 바뀌므로, 이를 서랍닫기에서 서랍열기로의 직접적인 전이로 확정할 수는 없습니다.`} />
    {visible("drawer-contrast") && <EvidenceTable id="drawer-contrast" title="40k 서랍열기 성공률: 사전에 고정한 보조 비교" queryId="secondary" sourceRows={secondary} rows={contrast}
      columns={[{ field: "cohortLabel", label: "구분" }, seedColumn, numberColumn("DO_F_DO", "서랍열기 집중 (%)"),
        numberColumn("DO_F_DC", "서랍닫기 집중 (%)"), numberColumn("DO_difference_pp", "차이 (%p)", true)]} />}
    <Narrative id="recovery-finding" queryId="secondary" rows={secondary.filter(r => r.cohort === "replication")}
      text={`**창문닫기가 중간에 하락했다가 회복한다는 패턴은 보편적으로 재현되지 않았습니다.** 서랍열기 집중 배분에서 기존 두 seed는 84%→0%→100%였지만, 새 seed에서는 1/3만 이 방향을 반복했습니다.

seed 1905는 오히려 84%→94%→52%로 늦게 하락했습니다. “20k에서 낮아도 40k에서 회복한다”는 운영 규칙을 두기에는 근거가 부족합니다. 40k 이후 회복 여부도 이번 실험으로는 알 수 없습니다.`} />
    {visible("window-recovery") && <EvidenceTable id="window-recovery" title="서랍열기 집중 조건의 창문닫기 성공률 (%)" queryId="secondary" sourceRows={secondary.filter(r => r.cohort === "replication")}
      rows={wc} columns={[seedColumn, numberColumn("WC_baseline", "출발점"), numberColumn("WC_20k", "+20k"),
        numberColumn("WC_40k", "+40k"), { field: "result", label: "사전 정의 패턴" }]} />}
    <Narrative id="task-finding" queryId="contributions" rows={contributions}
      text={`**평균 성공률의 이득에는 취약 과제 개선과 기존 과제 성능 유지가 함께 들어 있습니다.** 서랍닫기 집중의 +6.00%p는 서랍열기 기여 +2.33%p, 창문열기 +1.33%p, 창문닫기 +2.33%p로 분해됩니다. 반면 창문닫기 집중의 +5.17%p 중 +4.50%p는 창문닫기 성능 유지·개선에서 나왔습니다.

서랍닫기 성공률은 관측한 평가 사례에서 계속 100%였고, 창문열기는 여러 조건에서 여전히 낮았습니다. 평균만으로 네 과제가 모두 잘 학습됐다고 판단할 수 없습니다.`} />
    {visible("task-contributions") && <EvidenceTable id="task-contributions" title="균등 대비 평균 차이의 과제별 기여 (%p, 탐색적 산술 분해)" queryId="contributions" sourceRows={contributions}
      rows={contributionTable} columns={[allocationColumn, numberColumn("DO", "서랍열기", true), numberColumn("DC", "서랍닫기", true),
        numberColumn("WO", "창문열기", true), numberColumn("WC", "창문닫기", true), numberColumn("total", "합계", true)]} />}
    {visible("task-detail") && <EvidenceTable id="task-detail" title="40k 과제별 성공률 상세 (%)" queryId="branches" sourceRows={selected} rows={taskTable}
      controls={<label className="seed-control">후속 seed <select aria-label="과제별 결과의 후속 seed" value={seed} onChange={e => setSeed(e.target.value)}>
        <option value="all">새 3개 평균</option><option value="1903">1903</option><option value="1904">1904</option><option value="1905">1905</option>
      </select><button type="button" onClick={() => setSeed("all")}>평균으로 초기화</button></label>}
      columns={[allocationColumn, numberColumn("DO", "서랍열기"), numberColumn("DC", "서랍닫기"), numberColumn("WO", "창문열기"),
        numberColumn("WC", "창문닫기"), numberColumn("macro_pct", "평균")]} />}
    <Narrative id="budget-finding" queryId="budgets" rows={budgets}
      text={`**20k와 40k에서의 판단도 달랐습니다.** 새 seed 평균에서 서랍닫기 집중은 20k에 균등보다 −1.00%p였지만 40k에는 +6.00%p였습니다. 창문열기 집중은 −6.33%p에서 +6.33%p로 바뀌었습니다.

20k는 보조 시점이고 **주평가는 사전에 정한 40k**입니다. 이 두 시점만으로 전체 학습 곡선이나 최적 중단 시점을 추정하지 않습니다.`} />
    {visible("budget-table") && <EvidenceTable id="budget-table" title="새 3개 seed 평균: 추가 연습 예산에 따른 변화" queryId="budgets" sourceRows={budgets} rows={budgetTable}
      columns={[allocationColumn, numberColumn("at20", "20k 성공률 (%)"), numberColumn("at40", "40k 성공률 (%)"),
        numberColumn("delta20", "20k 균등 대비 %p", true), numberColumn("delta40", "40k 균등 대비 %p", true)]} />}
    <Narrative id="combined-context" queryId="cohorts" rows={cohorts}
      text={`**기존 발견용 두 반복과 합친 값은 기술적 요약으로 제시합니다.** 전체 다섯 후속 seed에서는 서랍닫기 집중의 평균이 55.6%, 균등 대비 +4.6%p로 가장 높았습니다. 다만 모든 seed에서 1위였던 배분은 없었습니다. 기존 seed에서 후보를 탐색한 사실을 유지하며 새 세 반복의 결과를 우선 해석합니다.`} />
    {visible("cohort-comparison") && <EvidenceTable id="cohort-comparison" title="발견·재현성 확인·전체 요약을 분리한 40k 성공률" queryId="cohorts" sourceRows={cohorts} rows={history}
      columns={[allocationColumn, numberColumn("discovery", "기존 2개 (%)"), numberColumn("replication", "새 3개 (%)"), numberColumn("combined", "전체 5개 (%)"),
        numberColumn("delta", "전체 균등 대비 %p", true), { field: "wins", label: "전체 균등보다 높음" }]} />}
    <Narrative id="scope-next" queryId="cohorts" rows={cohorts}
      text={`**연구 판단:** 이 출발점에서는 실패율 규칙의 이득이 작고 불안정한 반면, 일부 다른 배분의 이득은 반복됐습니다. 따라서 추가 연습의 효과를 직접 측정할 가치는 확인됐습니다. 그러나 고정된 서랍닫기 집중 배분으로 충분할 가능성도 남아 있습니다. 실패율 외의 정보를 쓰는 선택기가 필요하거나 유리하다는 결론은 아직 이릅니다.

다음 판단에는 **다른 원래 사전학습 seed와 다른 체크포인트**에서 같은 비교가 필요합니다. 그때 서랍닫기 집중 같은 고정 배분을 강한 기준선으로 두고, 실패율·최근 진행량·학습 시점이 더 좋은 선택을 예측하는지 확인하는 것이 합리적입니다. 이번 분석에서 추가 학습은 실행하지 않았습니다.

범위는 원래 seed 901의 200k 정책 하나입니다. 평가 초기 상태는 과제당 50개, 총 200개이며 모든 배분·시점·후속 seed에서 재사용했습니다. 관측 범위와 반복 방향은 신뢰구간이나 통계적 유의성 판정이 아닙니다.`} />
    <Narrative id="execution-methods" queryId="branches" rows={all}
      text={`실행은 2026-10-08 **12:05:54–14:14:14 KST**, 학습 실행기 기준 약 **2시간 8분 18초**에 완료됐습니다. 15분기, 추가 학습 600k, 평가 6.2k episodes를 수행했습니다. 실제 평가 환경 step은 1,730,026, 학습 포함 총 2,330,026입니다.

episode별 성공률과 집계, 배분 quota, 비용 장부, 원래 체크포인트, 실행 소스, 새 전체 상태 checkpoint 31개의 hash와 저장된 복원 검사를 독립 대조해 **1,127/1,127 검사**를 통과했습니다. 분석 과정의 추가 학습·정책 평가 비용은 0입니다. 체크포인트를 새로 실행해 재평가한 검사는 아닙니다.`} />
  </article>;
}
