# F04 기술적 실패와 정정 기록

본 측정과 주 분석의 과학적 수치는 아래 정정으로 바뀌지 않았다. 이전 출력 폴더를 덮어쓰거나 실패를 삭제하지 않았다.

1. `20261014T071541Z_verify_measurements_7677460c`: 전체 수치 검산 중 raw alignment가 거의 0인 값에서 1.2980732391754124e-9의 차이를 상대 오차 기준으로 거절했다. production은 task 가중치를 float32로 바꾸고 gradient 네 개를 float32로 합하지만, 검산은 float64 가중치와 Gram 행렬의 정확한 합을 사용했다. 검산을 실제 float32 가중치와 저장된 혼합 gradient norm으로 계산하게 고쳤다. 그 norm은 별도로 float64 Gram으로 재계산한 값과 비교하고 `8*epsilon_float32*sum(abs(w)*task_norm)+1e-12`의 네 항 합산 반올림 경계 안인지 검사한다. 과학적 수치나 채택 기준을 완화한 수정이 아니다.

2. `20261014T071639Z_verify_measurements_1ff20d0b`: 수치 검산과 대표 checkpoint의 finite difference를 마친 뒤, 검사 상세의 NumPy float32 경계값을 JSON으로 저장하는 과정에서 `TypeError: Object of type float32 is not JSON serializable`이 발생했다. 뒤이어 실패 요약을 쓰려는 재호출은 이미 생성된 `input_hashes.json`의 독점 생성 규칙에 막혀 `FileExistsError`가 났다. 입력 hash, 소스 사본, finite difference 결과, 부분 작성된 `checks.json`을 그대로 보존했다. 완료된 검증 실행으로 세지 않는다. 경계값을 Python float로 변환하고 새 폴더에서 전체 검산을 다시 실행한다. 이 시도는 최종 wall/CPU 요약이 기록되지 않았으므로 전체 정확한 비용 합계에 포함했다고 주장하지 않는다. 파일 시각 기반 경과시간 추정은 별도로 표시할 수 있다.

3. `20261014T072613Z_delivery_80e7e3f7`: 문서·소스 보관 검사에서 `sys.path.insert`의 단순 문자열 검사가 검사 코드 자신의 금지 문자열까지 잡았다. AST의 실제 호출 노드만 검사하도록 수정했다. 문서·산출물 확인 단계의 오류로 분석 수치에는 영향이 없다. 실패 출력도 보존했다.

4. `20261014T072648Z_delivery_3130b95d`: 재사용한 v26 수치 표의 기존 hash 기록은 상대 경로를 키로 저장했지만 새 보관 검사는 절대 경로로 조회해 `KeyError`가 났다. 두 경로를 resolve하여 비교하도록 고쳤다. 데이터 hash 불일치가 아니라 키 형식 문제였고 원본 파일을 수정하지 않았다.

첫 smoke와 smoke 검산은 통과했다. 첫 두 실패는 측정된 gradient·선택 결과의 scientific effect에 관한 실패가 아니라 검산 구현·저장에 관한 실패이고, 뒤의 두 번은 산출물 정리 검사 실패다. 최종 측정 검산 `20261014T071809Z_verify_measurements_9b3c92e4`는 87,608개 검사와 대표 checkpoint 8개·finite difference 16건을 통과했다. 마지막 문서 검사는 별도 성공한 `delivery` 실행으로 확인한다.
