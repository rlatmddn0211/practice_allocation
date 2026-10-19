# F05 기술 검사 실패와 수정 이력

실패한 실행은 모두 보존했다. 모델·실험 결과를 성공으로 바꾸거나 덮어쓰지 않았다.

| 시도 | 결과 | 환경 step | wall 초 | CPU 초 |
| --- | --- | ---: | ---: | ---: |
| [A 최초](results/20261015T032130Z_verify_implementation_A_8c9cdf55/summary.json) | return 합산의 완전 일치 검사 실패 | 7,103 | 20.531 | 7.328 |
| [B 최초](results/20261015T032430Z_verify_implementation_B_75b43298/summary.json) | 같은 검사 실패 | 7,517 | 18.971 | 8.078 |
| [A 새 검사](results/20261015T032518Z_verify_implementation_A_a936dc86/summary.json) | 117개 통과 | 7,103 | 16.769 | 8.172 |
| [B 새 검사](results/20261015T032848Z_verify_implementation_B_d2b90b92/summary.json) | 117개 통과 | 7,517 | 19.772 | 8.063 |
| [C 검사](results/20261015T033342Z_verify_implementation_C_5bb14fb1/summary.json) | 117개 통과 | 7,537 | 20.374 | 12.063 |

기존 early-stop 평가의 순차 float 합과 새 trace의 NumPy 합은 합산 순서가 달랐다. 새 A/B/C 검사에서 같은 성공 전 구간 return의 최대 절대 차이는 각각 2.27×10⁻¹³, 9.09×10⁻¹³, 4.55×10⁻¹³이었다. 성공 여부와 첫 성공 step은 동일했다.

측정 코드는 바꾸지 않고 return 합 비교에 절대 허용 오차 10⁻¹⁰을 적용했다. 첫 성공 step의 일치 검사를 추가했고, 전체 학습 상태와 RNG의 완전 일치 기준은 유지했다. Monte Carlo soft return은 독립 역방향 재귀식으로 검산했다. 각 시도의 실행 당시 소스·설정·의존성·비용이 해당 결과 폴더에 있다.

이 다섯 시도의 총 환경 비용은 36,777 step, 지속 학습 update는 0이다. 자동 실행기의 추가 기술 검사와 본 측정·실패 비용은 [v33 실행 기록](../33_remaining_factor_queue_v1/README.md)에서 별도로 합산한다.
