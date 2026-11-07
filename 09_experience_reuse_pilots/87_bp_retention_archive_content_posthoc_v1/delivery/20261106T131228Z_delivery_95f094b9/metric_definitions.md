# 87번 지표·시점·분모 규약

이 분석은85번의 같은 기록을 다시 계산한 사후 탐색이다. P=ONSET,U=RANDOM_PRE,B=BASE. BC 손실이 아니라SAC 최종배치의DO slot을archive로대체한처치다.

- BP history의z0,z16,z32,z64는+0,+16k,+32k,+64k에서500action동안한번이라도관측된공식success의OR다.원시success는현재상태flag다.
- 160=5부모×2미래×16사례,독립부모5,고유물리사례16,초기평가는80부모×사례관측을두미래/세arm이공유한다. 초기성공74/80,초기실패6/80이반복표에서148/12가된다.
- AUC=[.125,.25,.375,.25]·J. 부모안두미래평균뒤부모동일비중. pp는0..1차이×100.1111은네관측시점성공이며그사이의유지를증명하지않는다.
- gain/loss는인접원평가점0→1/1→0사건.이전성공후실패블록이끝나는0→1만recovery.사건수와그사건을겪은이력수는별개다.
- 초기성공의최종유지=모든네관측성공+관측상실후최종성공.두집단의합차이를보존구성으로분해하며개별사례의인과적상실예방으로부르지않는다.
- 처음획득16/32/64k의남은평가기회는2/1/0.마지막획득은이후유지미측정이다.
- BP공식목표오차=abs(버튼Y-goalY),≤.02m. qnegative가누름방향,물체세계+Y. DOqnegative가개방방향,세계-Y.같은joint부호가같은행동기능을뜻하지않는다.
- T_t의action은obs_(t-1)에서생성,저장physics는action후x_t.제어t1..500,control_dt=.0125s. BP TCP이동총량은실제저장post1→post500의499links만계산한다.초기TCP를raw관측으로추정하지않는다.
- DO물리초기q0=raw_reset_handleY-goalY-.19,h0=goal+[0,.19+q0,0].85정정mapping그대로이며원reset관측·실제h0·x1별도저장,원SAC입력수정없음.
- DO개방량p=-q(m).창[a,e]순개방=p_e-p_(a-1),개방path=sum(max(Δp,0)),닫힘path=sum(max(-Δp,0)).순개방=개방path-닫힘path.
- 창이후맥락은e+1..sigma첫성공.끝기준되돌림=max(0,p_e-min(p_post));추가진행=max(p_post)-p_e.전체순개방되돌림은창net>1e-8m이며이후p<=p_(a-1)+1e-8m인경우.1e-8은수치0허용오차이며좋은행동의성능문턱이아니다.
- 실제사용n_j=C_j(end)-C_j(start).P/U원episode+offset별n_j동일검증.노출평균=sum(n_j*feature_j)/sum(n_j).해당시점이후사용량을앞시점결과에붙이지않는다. actor/critic실제사용count를각각보고하며critic2개때문에2배로세지않는다.
- 반복draw비율=1-고유전이수/총사용수.입력의경험수가증가했다는뜻이아니다.사용량가중변위는원자료변위의재표집평균으로새로실행한물체이동량이아니다.
- actionXYZ명령,gripper명령,실제TCP/물체변위는별도다.접촉은body/geom식별된제어endpoint표본이며내부substep접촉부재를뜻하지않는다.
- 원85의부모bootstrap분위범위만복사한다.이번새bootstrap/pvalue/선택모델/threshold탐색없음.중첩LOO와기존16개개발사례에조건화한탐색이다.
