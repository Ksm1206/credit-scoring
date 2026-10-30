# 데이터 출처 및 수집 기록

이 문서는 프로젝트에 쓴 데이터가 **어디서 왔고, 어떻게 받았고, 원본과 같은지 어떻게 확인했는지**를 남긴 기록입니다.

- 수집일: 2026-10-30 (KST)
- 재현 스크립트: `scripts/collect_data.sh` → `scripts/prepare_data.py`

---

## 1. Give Me Some Credit: 메인 데이터 (모델 학습에 사용)

| 항목 | 내용 |
|---|---|
| **원 출처** | Kaggle 대회 "Give Me Some Credit" (2011) |
| **원본 URL** | https://www.kaggle.com/c/GiveMeSomeCredit |
| 내용 | 미국 개인 대출자 150,000명, 2년 내 90일 이상 연체 여부(`SeriousDlqin2yrs`) + 10개 변수 |
| 사용 파일 | `cs-training.csv` (학습·평가에 사용), `cs-test.csv` (정답 없음, 미사용) |
| 이용 조건 | Kaggle 대회 규정을 따름. **원본 재배포 금지**가 원칙이라 저장소에는 데이터를 올리지 않고(`.gitignore`) 수집 스크립트만 공개 |

**실제로 받은 경로.** Kaggle 다운로드는 로그인과 대회 약관 동의가 필요하다. 그래서 같은 파일을 올려둔 공개 GitHub 저장소 2곳에서 받고, 두 파일의 SHA-256이 같은지 확인했다.

| 미러 | 커밋 | 파일 |
|---|---|---|
| https://github.com/jwu424/GiveMeSomeCredit | `ff876b6` | cs-training.csv, cs-test.csv |
| https://github.com/wang-weishuai/GiveMeSomeCredit | `f27853c` | cs-training.csv (대조용) |

```
cs-training.csv  SHA-256 1bd46da486a5708c58c7b01a034fae2a13b327f6f7b62ea7ba4fe3b5824b24ac  (7,564,965 bytes, 150,000행)
cs-test.csv      SHA-256 bab363a2a807218d32a51f5fc9668b8be7977795065edd386abc8546abaa5b78
```

**원본과 같은지 확인한 방법.**
1. 서로 다른 두 미러의 해시가 일치했다.
2. 행 수 150,000, 부도율 6.684%, 컬럼 구성이 Kaggle 데이터 설명과 일치했다.

> 📌 직접 Kaggle에서 받아 `data/raw/gmsc/`에 넣은 뒤 `sha256sum cs-training.csv`가 위 값과 같은지 확인하면, 포트폴리오에 "Kaggle 원본 사용"이라고 자신 있게 쓸 수 있다.

---

## 2. Lending Club 2007–2011: 보조 데이터 (수집만 완료, 후속 분석용)

| 항목 | 내용 |
|---|---|
| **원 출처** | LendingClub (미국 P2P 대출 플랫폼)이 공개한 대출 실적 데이터 `LoanStats3a` |
| 원본 URL | 과거 LendingClub 웹사이트의 통계 페이지에서 배포했다. 현재는 공식 사이트에서 내려간 것으로 알려져 있어, Kaggle 등 2차 배포본을 주로 쓴다 |
| 내용 | 2007-06 ~ 2011-12에 실행된 대출 42,535건. 대출금액·금리·등급·상환 결과 포함 |
| 정리 후 | 상환 결과가 확정된 40,347건 (Fully Paid / Charged Off) |

| 미러 | 커밋 | 파일 |
|---|---|---|
| https://github.com/jsabrams/default_risk_prediction | `f73b176` | LoanStats3a.csv.zip |
| https://github.com/jatinit056/banking-loan-analytics | `0470e2f` | data/raw/LoanStats3a.csv.zip (대조용) |

```
LoanStats3a.csv.zip  SHA-256 6e53451aca45fdc3265d01ea99e1543e3730c80a53b68cf098ef3db06ee3bc32  (9,571,527 bytes)
```

---

## 3. German Credit: 보조 데이터 (연습용 샌드박스)

| 항목 | 내용 |
|---|---|
| **원 출처** | UCI Machine Learning Repository, "Statlog (German Credit Data)", Prof. Hans Hofmann (1994) 기증 |
| **원본 URL** | https://archive.ics.uci.edu/dataset/144/statlog+german+credit+data |
| 내용 | 독일 은행 대출 신청자 1,000명, 20개 변수, 정상(700)/불량(300) |
| 이용 조건 | CC BY 4.0 (UCI 저장소 표기 기준). 사용 시 출처 표기 |

| 미러 | 커밋 | 파일 |
|---|---|---|
| https://github.com/rajarshighoshal/german-credit-data | `7b3ec22` | german.data |

```
german.data  SHA-256 b21f3d81db8071257d5ff1deaeba1fd4303b62712e6fcc9715c7a86202cb5871  (1,000행)
```

변수 코드(A11, A12 …)의 한글·영문 의미는 UCI 데이터 설명서(german.doc)를 따라 `prepare_data.py`에서 변환했다.

---

## 4. 왜 웹사이트에서 직접 수집(크롤링)하지 않았나

개인의 소득·연체 이력 같은 신용정보는 「신용정보의 이용 및 보호에 관한 법률」의 보호 대상이다. 웹에서 수집할 수 있는 형태로 공개되지도 않는다. 그래서 신용평가 모델 연습과 연구에는 **기관이 익명화해 공개한 데이터셋**을 쓰는 것이 일반적이다.

국내 데이터가 필요하면 한국신용정보원이 연구 목적의 신용정보 표본 DB(CreDB)를 신청·심사를 거쳐 제공해 왔다. 이용 조건은 기관 안내를 직접 확인해야 한다.
- 참고: [CreDB 기업신용표본DB의 이해와 활용 (이슈리포트 2019-4호)](https://www.smallake.kr/wp-content/uploads/2020/08/이슈리포트2019-4호CreDB기업신용표본DB의이해와활용.pdf)

---

## 5. 방법론 · 도구 참고문헌

**방법론**
- Siddiqi, N. *Intelligent Credit Scoring: Building and Implementing Better Credit Risk Scorecards* (2nd ed.), Wiley, 2017. WoE·IV, 구간화, PDO 점수 스케일링, cut-off 설정의 표준 교재
- Ke, G. et al. "LightGBM: A Highly Efficient Gradient Boosting Decision Tree." *NeurIPS*, 2017.

**IV 해석 기준** (0.02 미만 무의미 / 0.1~0.3 중간 / 0.3 이상 강함): 스코어카드 실무에서 널리 쓰는 경험 기준이다. 위 Siddiqi 교재에서도 다룬다.

**손익 가정** (정상 +1, 부도 −6): 프로젝트에서 세운 단순화 가정이다. 외부 출처가 아니며, 민감도 분석(3~15배)으로 보완했다.

**소프트웨어** (분석 시점 버전): Python 3.13, pandas 3.0.5, scikit-learn 1.9.1, LightGBM 4.7.0, Streamlit 1.66.1, SQLAlchemy 2.1.6, SciPy 1.18.1

---

## 포트폴리오·블로그용 출처 표기 예시

> 데이터: Kaggle, "Give Me Some Credit" (2011), https://www.kaggle.com/c/GiveMeSomeCredit
> 방법론: Siddiqi, N. (2017). *Intelligent Credit Scoring* (2nd ed.). Wiley.
