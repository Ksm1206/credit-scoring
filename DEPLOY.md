# 배포 & 사용자 모으기 체크리스트

## 0. 배포 전 점검 (2분)
```bash
pip install -r requirements.txt
python tests/smoke_test.py                                  # 로컬 SQLite로 점검
DATABASE_URL="Supabase 주소" python tests/smoke_test.py     # 2단계 후, 실제 DB로 한 번 더
```
마지막 줄에 `ALL PASSED`가 나오면 앱·점수·로깅이 모두 정상이다. 실제 DB로 돌리면 `demoa0`, `demob2` 테스트 행이 남는다. 실험 시작 전에 Supabase SQL Editor에서 `DELETE FROM events WHERE user_id IN ('demoa0','demob2');`로 지운다.

## 1. GitHub에 올리기 (10분)
✅ 완료: https://github.com/Ksm1206/credit-scoring

- **웹으로 올릴 때**: 저장소 → Add file → Upload files. 압축을 푼 폴더 **안의 내용물**을 끌어다 놓는다. 수정된 파일만 다시 올려도 된다(같은 이름이면 덮어씀).
- **Git으로 올릴 때**:
  ```bash
  git remote add origin https://github.com/Ksm1206/credit-scoring.git
  git pull origin main --allow-unrelated-histories   # 웹 업로드로 생긴 커밋과 합치기
  git push -u origin main
  ```
- `data/`, `logs/`는 올리지 않는다. Kaggle 데이터는 재배포하지 않고 `scripts/collect_data.sh`로 받게 한다.

## 2. 로그 저장소 만들기 (10분), 꼭 배포 전에
✅ 완료 (Supabase, West EU 리전, Data API 끔, 자동 RLS 켬)

Streamlit Cloud는 재시작하면 디스크가 초기화된다. 그래서 SQLite 로그는 사라진다.
1. [supabase.com](https://supabase.com)에서 무료 프로젝트를 만든다. 비밀번호는 영문·숫자로만 길게 정하고 따로 적어둔다.
2. Security: **Enable Data API 끔**(앱은 DB에 직접 접속하므로 불필요), **Enable automatic RLS 켬**.
3. 상단 **Connect** → **Direct** 탭 → Type: URI, Method: **Session pooler** 주소를 복사하고 `[YOUR-PASSWORD]`를 비밀번호로 바꾼다.
4. 테이블은 앱이 처음 실행될 때 자동으로 생성된다.

## 3. Streamlit Community Cloud 배포 (10분)
✅ 완료

1. [share.streamlit.io](https://share.streamlit.io) → GitHub로 로그인 → **Create app**
2. Repository: `credit-scoring`, Branch: `main`, Main file: `app/app.py`
3. Advanced settings → **Secrets**에 아래를 붙여넣는다:
   ```toml
   DATABASE_URL = "postgresql://postgres.<프로젝트ID>:비밀번호@aws-0-eu-west-1.pooler.supabase.com:5432/postgres"
   ```
   - Secrets 칸의 회색 예시 글씨는 안내문이다. 지우지 않고 바로 입력하면 된다.
   - **Python version은 3.13**을 고른다(기본값 3.14는 일부 패키지 설치가 실패할 수 있음, 테스트는 3.13에서 함).
4. Deploy → 발급된 주소를 README 상단 `<배포주소>`에 반영한다. 앱의 공유 링크는 배포 주소를 자동으로 읽는다.
5. **확인 (필수)**: 앱에서 점수를 한 번 계산한 뒤, Supabase Table Editor에서 `events` 테이블에 행이 생겼는지 본다.
   - 화면이 정상이어도 로그는 실패할 수 있다. 로깅 오류는 서비스를 멈추지 않도록 숨겨져 있기 때문이다.
   - 행이 없으면 Streamlit Cloud → Manage app → **Logs**에서 `[events] log failed` 줄을 찾아 메시지를 확인한다.
   - 자주 나오는 원인
     | 메시지 | 조치 |
     |---|---|
     | `No module named 'psycopg'` | 이 저장소 최신 버전(드라이버 명시 수정 포함)인지 확인한다 |
     | `password authentication failed` | Secrets의 비밀번호를 확인한다. 특수문자는 URL 인코딩(`@`→`%40`)해야 한다 |
     | `could not translate host name` / 연결 시간 초과 | Supabase의 **Session pooler** 주소를 썼는지 확인한다(Direct 주소는 IPv6 전용일 수 있음) |

## 홍보 전 체크리스트
- [ ] 앱에서 점수 계산 → Supabase Table Editor의 `events`에 행이 생기는지 확인
- [ ] README 상단 `<배포주소>`를 실제 주소로 교체 (GitHub에서 README.md 연필 아이콘으로 바로 수정 가능)
- [ ] 테스트 기록 삭제: Supabase SQL Editor에서 `DELETE FROM events;` 실행
- [ ] 이 시점의 날짜를 실험 시작일로 기록 (`docs/changelog.md`)

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
