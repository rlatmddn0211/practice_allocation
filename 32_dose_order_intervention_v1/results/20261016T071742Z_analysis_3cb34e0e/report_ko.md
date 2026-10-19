# F08 강도와 순서 대조 결과

사전에 고정한 72분기를 모두 완료했다. A/B/C 각각 원래 seed 12 한 개의 개발 검증이며, 아래 구간은 고정된 정책의 평가 사례만 재표집했다. 원래 seed 일반화나 비용 포함 적응형 배분의 성공을 뜻하지 않는다.

| 구성 | 사전 대조 | 차이 %p | 사례 조건부 95% 구간 | 같은 방향 반복 |
| --- | --- | ---: | --- | ---: |
| A | dose81_minus25 | -7.917 | [-9.833, -6.000] | 2/3 |
| A | dose4375_nonlinearity | +2.972 | [+1.444, +4.500] | 2/3 |
| A | dose625_nonlinearity | +0.528 | [-1.528, +2.528] | 1/3 |
| A | forward_minus_reverse | +1.583 | [-0.333, +3.500] | 2/3 |
| A | forward_minus_mixture | -1.417 | [-3.417, +0.583] | 2/3 |
| A | reverse_minus_mixture | -3.000 | [-5.250, -0.750] | 2/3 |
| A | alternate_minus_mixture | -2.500 | [-4.083, -0.833] | 2/3 |
| B | dose81_minus25 | +12.250 | [+10.417, +14.167] | 2/3 |
| B | dose4375_nonlinearity | +4.833 | [+2.750, +6.861] | 3/3 |
| B | dose625_nonlinearity | +6.083 | [+4.750, +7.361] | 3/3 |
| B | forward_minus_reverse | +6.500 | [+4.000, +9.083] | 2/3 |
| B | forward_minus_mixture | +3.333 | [+1.667, +5.000] | 2/3 |
| B | reverse_minus_mixture | -3.167 | [-5.417, -1.000] | 1/3 |
| B | alternate_minus_mixture | +5.833 | [+4.583, +7.000] | 3/3 |
| C | dose81_minus25 | +0.333 | [-0.500, +1.167] | 2/3 |
| C | dose4375_nonlinearity | +0.639 | [-0.167, +1.444] | 2/3 |
| C | dose625_nonlinearity | -4.639 | [-5.694, -3.639] | 2/3 |
| C | forward_minus_reverse | +1.167 | [+0.167, +2.167] | 3/3 |
| C | forward_minus_mixture | +0.000 | [-0.917, +0.917] | 1/3 |
| C | reverse_minus_mixture | -1.167 | [-2.250, -0.083] | 2/3 |
| C | alternate_minus_mixture | -0.083 | [-0.917, +0.750] | 1/3 |

dose4375/625_nonlinearity는 양 끝 비중의 선형 보간과 실제 중간 비중의 차이다. 순서 대조는 총 수집량을 맞춘 실제 연속 학습이다. 학습 중 optimizer·replay·RNG를 전환 시점에 초기화하지 않았다.

완료 분기 학습은 2,880,000 step, 이 단계의 초기·최종 평가 환경 실행은 9,495,447 step이었다. 실패·기술 검사 비용은 campaign 실행 비용표에 별도로 포함한다.

[전체 분기 점수](branch_scores.csv) · [대조별 반복](contrasts_by_repeat.csv) · [출처](outcome_provenance.csv)

평균 절대 차이 1%p와 3반복 중 2반복 같은 방향은 후속 연구를 위한 기술적 표시다. 통계적 유의성이나 일반 효과 채택 기준으로 바꾸지 않는다.
