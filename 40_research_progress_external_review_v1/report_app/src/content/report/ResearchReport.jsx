import React from "react";
import { DataTable, ReportSection, RichNarrative, useDataApp } from "../../data-app-public.jsx";

const base = "https://github.com/rlatmddn0211/practice_allocation/";
const previews = Object.fromEntries([
  ["tree/main/03_p0_pretraining_analysis_v1", "P0 사전학습 분석", "400k 공개 진단과 200k 분기점 선택, 평가 사례 수와 학습 비용을 설명한다."],
  ["tree/main/07_p0_replication_analysis_v1", "같은 부모에서의 후속 반복", "새 후속 seed 세 개와 발견 두 개를 구분한다. 새 원래 seed의 재현이 아니다."],
  ["tree/main/17_e0_e2_detailed_research_report_v1", "E0~E2 상세 보고서", "새 평가 사례·독립 부모·목표 수집량 고정 대조를 구분하고 원래 seed별 차이를 보고한다."],
  ["blob/main/21_e3_completed_results_analysis_v1/report_ko.md", "E3 완료 분석", "B의 고정 ButtonPress 집중 우위와 C의 부모 대비 능력 손실, 구성별 선택 규칙을 분석한다."],
  ["blob/main/19_budgeted_practice_research_feasibility_v1/research_plan_ko.md", "유한 예산 예측 연구의 가능성", "E1의 20k→40k 순위 반전과 단순 보정의 실패, 큰 진단 비용을 기록한다. 후속 제안은 별도다."],
  ["blob/main/36_all_candidate_evidence_review_v1/report_ko.md", "후보 ①~⑦ 통합 검토", "후보별 기준·선택 변화·불리한 결과를 구분한 개발 자료의 재검토다."],
  ["blob/main/37_f08_integrated_candidate_review_v1/report_ko.md", "⑧ 포함 후보 통합 해석", "72분기 강도·순서 개입을 재계산했다. B 교대−혼합 차이는 원래 seed 하나의 개발 근거다."],
  ["tree/main/38_candidate_factor_publication_v1", "후보별 증거 공개 안내", "각 후보의 역할, 실제 측정, 결과, 한계와 이후 채택 조건을 연결한다."],
  ["tree/main/18_practice_allocation_literature_review_v1", "문헌 비교 기록", "초기 핵심·인접 문헌 비교와 차별화의 한계를 기록한 10월 13일 검토다."],
  ["tree/main/22_candidate_factor_grounding_v1", "후보 요인의 근거", "연구 질문의 변화와 기본 세 요인, 추가 후보의 검증 필요성을 기록한다."]
].map(([url,title,summary]) => [base+url,{title,summary,source:"연구 저장소",approvedForReport:true}]));

previews["https://chatgpt.com/share/6ad594f9-38dc-83ee-ac43-7022fcf2dde3"] = {
  title:"사용자 제공 Deep Research 평가", source:"공유된 외부 방법론 검토",
  summary:"평균 경로 효과와 상태별 선택 가치의 분리, 측정 오차 결합, 교대 위상, 진단 비용을 지적한다. 원시 실험의 독립 재현은 아니다.", approvedForReport:true
};
previews["https://proceedings.mlr.press/v235/cho24d.html"] = {
  title:"Hard Tasks First", source:"PMLR · ICML 2024",
  summary:"공식 초록은 난이도에 따른 task 우선순위와 reset을 포함한 다중 과제 RL 방법을 설명한다. 본 연구에서 방법을 재현하지 않았다.",approvedForReport:true
};
previews["https://arxiv.org/abs/2503.01941"] = {
  title:"Task Scheduling & Forgetting in Multi-Task Reinforcement Learning",source:"arXiv · 2025",
  summary:"공식 초록은 task별 비대칭 학습·유지 패턴과 기존 유지·성능 기반 scheduling의 한계를 보고한다.",approvedForReport:true
};
previews["https://arxiv.org/abs/2608.13415"] = {
  title:"Deliberate Practice: Learning Robot Skills under a Budget",source:"arXiv · 2026",
  summary:"공식 초록은 제한된 연습 예산으로 유용한 robot skill을 배우기 위한 배분·계획을 다룬다. 초록 수준의 관련성 확인이다.",approvedForReport:true
};

export function ReportContent() {
  const {snapshot, visible, appTitle, setAppTitle, canEdit, mode} = useDataApp();
  const sections = snapshot.report.sections;
  const contents = sections.slice(1).map(s => `- [${s.title}](#read-${s.id})`).join("\n");
  return <article className="report-content research-progress" aria-label="추가 연습 배분 연구 외부 평가 보고서">
    <header className="report-hero">
      <h1 data-data-app-title contentEditable={canEdit && mode === "edit"} suppressContentEditableWarning
        onBlur={canEdit && mode === "edit" ? e => setAppTitle(e.currentTarget.textContent.trim() || appTitle) : undefined}
        onKeyDown={canEdit && mode === "edit" ? e => {if(e.key === "Enter"){e.preventDefault();e.currentTarget.blur();}} : undefined}>{appTitle}</h1>
      <RichNarrative id="report-introduction" value={snapshot.report.introduction} label="보고서 소개 편집"/>
    </header>
    {sections.map((s,index) => {
      const sourceRowsByQuery = Object.fromEntries(s.queryIds.map(q => [q,snapshot.queries[q].rows]));
      return <React.Fragment key={s.id}>
        {visible(s.id) && <div id={`read-${s.id}`} className="research-section-anchor">
          {s.queryIds.length ? <ReportSection id={s.id} title={s.title} showHeading={false}
            queryId={s.queryIds[0]} queryIds={s.queryIds} sourceRowsByQuery={sourceRowsByQuery}>
            <EvidenceNarrative section={s}/>
          </ReportSection> : <section data-review-section={s.id}>
            <EvidenceNarrative section={s}/>
          </section>}
        </div>}
        {index === 0 && <nav className="research-contents" aria-label="보고서 목차">
          <details><summary>전체 목차 · 17개 절</summary>
            <RichNarrative id="report-contents" value={contents} label="목차 편집"/>
          </details>
        </nav>}
      </React.Fragment>;
    })}
  </article>;
}

// The shared narrative renderer intentionally does not render GFM tables.
// Keep prose editable and reviewed tables on the shared read-only table path.
function EvidenceNarrative({section}) {
  const pieces=section.markdown.split(/(^\|.*\n\|[-:| ]+\|\n(?:\|.*(?:\n|$))+)/gm).filter(Boolean);
  return <div className="research-section-body">{pieces.map((piece,index)=>{
    if(!piece.startsWith('|'))return <RichNarrative key={index} id={`${section.id}:prose-${index}`} value={piece} sourcePreviews={previews} label="보고서 본문 편집"/>;
    const lines=piece.trim().split('\n');
    const cells=line=>line.trim().slice(1,-1).split('|').map(v=>v.trim().replace(/\*\*|`/g,''));
    const headings=cells(lines[0]);
    const columns=headings.map((label,i)=>({field:`c${i}`,label}));
    const rows=lines.slice(2).map(line=>Object.fromEntries(cells(line).map((v,i)=>[`c${i}`,v])));
    // Keep every row visible. Shared DataTable uses eight-row pagination;
    // long archival tables are presented as consecutive eight-row blocks.
    const chunks=Array.from({length:Math.ceil(rows.length/8)},(_,i)=>rows.slice(i*8,i*8+8));
    return <div key={index} className="research-evidence-table" data-reviewed-rows data-logical-table={`${section.id}-${index}`}>
      {chunks.map((chunk,i)=><DataTable key={i} rows={chunk} columns={columns} searchable={false} compactNumbers={false}
        label={`${section.title} 표 ${index} ${i+1}/${chunks.length}`}/>)}
    </div>;
  })}</div>;
}
