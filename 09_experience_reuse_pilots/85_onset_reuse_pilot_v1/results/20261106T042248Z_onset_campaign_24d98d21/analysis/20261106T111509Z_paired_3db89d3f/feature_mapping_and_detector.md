# 물리 입력과 선택 규칙

- 원 환경 drawer-open-v3, reward v2. 공식 물체 기준점은 drawer_link world xpos+[0,-0.16,0] m.
- goal_slidey는 +world-Y slide joint, qpos/qvel 주소9. 개방 방향 s_goal=-1.
- reset 물리 h0는 goal+[0,0.19+q0,0]. q0는 저장 reset Y와 고정 XML에서 산술 복원하며 x1을 사용하지 않는다. raw reset X는 이전 forward 좌표로 남아 구분한다.
- t=1..L은 실제 action과 반환값. d_t=norm(h_t-goal), q_t는 같은 제어 endpoint의 저장 joint. 원 index와 원 정밀도를 유지한다.
- control_dt=.0125s=frame_skip5×physics_dt.0025s. W32=.4s, 전후16전이 각각.2s. 접촉은 endpoint 표본이고 필수 선택 조건이 아니다.
- 3점 중심 median은 offline detector에만 쓴다. 첫 tau 후보의 직전5점 joint 범위<=1mm, 첫 감소>=.1mm,8-action 진행>=5mm, 다음3점 각각>=2.5mm 유지, joint 방향 일치를 검사한다.
- 최초 후보가 부적격이면 다음 사건을 고르지 않는다. tau>=17, tau+15<sigma. 첫16 action의 실제 d0 대비5mm 진행은 제외한다. 32개 원 전이를 padding/연결/복제하지 않는다.
- U의 창 시작점은1..sigma-32 균일 정수, seed41031의 안정 SHA256/PCG64 파생. 공통 episode는 모든 receiver/future에서 같은 U 창을 사용한다. 중복을 허용한다.
- 원 obs43D와 task/goal, 실제 action, reward, next_obs와 timeout 처리 그대로다. 차원/구간을 위한 새 policy 입력이나 BC 손실은 없다.
- actual native/archive 사용량은 최종 batch 기준이며 원 native draw를 별도 기록한다. 최초 표집 후 교체된 native 전이는 실제 사용으로 세지 않는다.

전체 수치·예외 우선순위·seed·source hash는 protocol_resolved.json 및 preparation의 입력 영수증을 따른다. 평활과 이후 유지 확인은 온라인 관측 가능한 선택 신호가 아니다.
