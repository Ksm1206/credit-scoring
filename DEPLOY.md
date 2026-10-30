# 배포 & 사용자 모으기 체크리스트

## 0. 배포 전 점검 (2분)
```bash
pip install -r requirements.txt
python tests/smoke_test.py                                  # 로컬 SQLite로 점검
DATABASE_URL="Supabase 주소" python tests/smoke_test.py     # 2단계 후, 실제 DB로 한 번 더
```
마지막 줄에 `ALL PASSED`가 나오면 앱·점수·로깅이 모두 정상이다. 실제 DB로 돌리면 `demoa0`, `demob2` 테스트 행이 남는다. 실험 시작 전에 Supabase SQL Editor에서 `DELETE FROM events WHERE user_id IN ('demoa0','demob2');`로 지운다.

## 1. GitHub에 올리기 (10분)
1. github.com에서 새 저장소 `credit-scoring`을 만든다 (Public).
2. 압축을 푼 폴더에서 아래를 실행한다:
   ```bash
   git remote add origin https://github.com/<아이디>/credit-scoring.git
   git push -u origin main
   ```
   커밋은 이미 만들어져 있다. `data/`, `logs/`는 `.gitignore`로 제외된다. Kaggle 데이터는 재배포하지 않고 `scripts/collect_data.sh`로 받게 한다.

## 2. 로그 저장소 만들기 (10분), 꼭 배포 전에
Streamlit Cloud는 재시작하면 디스크가 초기화된다. 그래서 SQLite 로그는 사라진다.
1. [supabase.com](https://supabase.com)에서 무료 프로젝트를 만든다 (리전: Seoul).
2. Project Settings → Database → Connection string(URI, **Session pooler**)을 복사한다.
3. 테이블은 앱이 처음 실행될 때 자동으로 생성된다.

## 3. Streamlit Community Cloud 배포 (10분)
1. [share.streamlit.io](https://share.streamlit.io) → GitHub로 로그인 → **Create app**
2. Repository: `credit-scoring`, Branch: `main`, Main file: `app/app.py`
3. Advanced settings → **Secrets**에 아래를 붙여넣는다:
   ```toml
   DATABASE_URL = "postgresql://postgres.xxxx:비밀번호@aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres"
   ```
4. Deploy → 발급된 주소를 `app/app.py`의 공유 링크(`<배포주소>`)와 README에 반영한다.
5. **확인 (필수)**: 앱에서 점수를 한 번 계산한 뒤, Supabase Table Editor에서 `events` 테이블에 행이 생겼는지 본다.
   - 화면이 정상이어도 로그는 실패할 수 있다. 로깅 오류는 서비스를 멈추지 않도록 숨겨져 있기 때문이다.
   - 행이 없으면 Streamlit Cloud → Manage app → **Logs**에서 `[events] log failed` 줄을 찾아 메시지를 확인한다.
   - 자주 나오는 원인
     | 메시지 | 조치 |
     |---|---|
     | `No module named 'psycopg'` | 이 저장소 최신 버전(드라이버 명시 수정 포함)인지 확인한다 |
     | `password authentication failed` | Secrets의 비밀번호를 확인한다. 특수문자는 URL 인코딩(`@`→`%40`)해야 한다 |
     | `could not translate host name` / 연결 시간 초과 | Supabase의 **Session pooler** 주소를 썼는지 확인한다(Direct 주소는 IPv6 전용일 수 있음) |

## 4. 사용자 모으기
채널별로 **`?ref=` 링크를 다르게** 뿌려야 유입 경로 분석(`acquisition` 쿼리)이 된다.

| 채널 | 링크 예시 | 홍보 포인트 |
|---|---|---|
| 에브리타임 (졸업생은 모교 게시판) | `…streamlit.app/?ref=everytime` | "대출 15만 건 데이터로 만든 신용점수 계산기, 점수 올리는 법까지" |
| 오픈카톡 (재테크·사회초년생·데이터분석 방) | `?ref=openchat` | 1분 테스트, 개인정보 저장 안 함 |
| 링크드인 / 블로그 | `?ref=linkedin` / `?ref=blog` | 만든 과정 + 분석 결과 글과 함께 |
| 커뮤니티 (디스콰이엇, 데이터 분석 카페 등) | `?ref=community` | 피드백 요청 형식이 반응이 좋음 |

목표: **2주 안에 300명**. 그 후 매주 `python analytics/analyze.py`로 지표를 기록한다.

## 5. 운영 루틴 (주 1회, 30분)
1. Supabase 연결 문자열을 환경변수에 넣고 실행한다: `DATABASE_URL=... python analytics/analyze.py`
2. 퍼널에서 가장 많이 빠지는 단계를 찾는다 → 가설 1개 → 개선 1개 배포
3. 개선 전·후 지표를 `docs/changelog.md`에 기록한다. 이게 면접에서 말할 "데이터 기반 개선" 사례가 된다.

> ⚠️ `logs/events_synthetic.db`(가상 로그)의 수치는 쿼리 검증용이다. 이력서·블로그에는 실제 로그 수치만 쓴다.
