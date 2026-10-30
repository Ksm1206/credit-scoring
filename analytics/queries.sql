-- 신용점수 시뮬레이터 이벤트 분석 쿼리 (SQLite 문법)
-- analyze.py가 운영 DB(Postgres 등)를 로컬 SQLite 스냅샷으로 복사한 뒤 실행한다.
-- 각 쿼리는 "-- name: <이름>" 주석으로 구분한다.

-- name: daily_active
-- 일별 방문자(DAU)와 계산 수행자
SELECT DATE(ts)                                                    AS day,
       COUNT(DISTINCT user_id)                                     AS dau,
       COUNT(DISTINCT CASE WHEN event = 'calc_submit' THEN user_id END) AS calc_users,
       SUM(event = 'calc_submit')                                  AS calcs
FROM events
GROUP BY 1
ORDER BY 1;

-- name: funnel
-- 방문 → 계산 → 결과 확인 → 피드백 → 공유 (사용자 기준, 실험군별)
WITH u AS (
    SELECT user_id, variant,
           MAX(event = 'page_view')   AS visited,
           MAX(event = 'calc_submit') AS calculated,
           MAX(event = 'result_view') AS viewed,
           MAX(event = 'feedback')    AS gave_feedback,
           MAX(event = 'share_click') AS shared
    FROM events
    GROUP BY user_id, variant
)
SELECT variant,
       SUM(visited)       AS step1_visit,
       SUM(calculated)    AS step2_calc,
       SUM(viewed)        AS step3_result,
       SUM(gave_feedback) AS step4_feedback,
       SUM(shared)        AS step5_share,
       ROUND(1.0 * SUM(calculated) / SUM(visited), 4) AS visit_to_calc
FROM u
GROUP BY variant;

-- name: ab_helpful
-- 1차 지표: 결과를 본 사용자 중 '도움됐어요'를 누른 비율 (사용자당 첫 피드백 기준)
WITH viewers AS (
    SELECT DISTINCT user_id, variant FROM events WHERE event = 'result_view'
),
first_fb AS (
    SELECT user_id, json_extract(props, '$.helpful') AS helpful,
           ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY ts) AS rn
    FROM events WHERE event = 'feedback'
)
SELECT v.variant,
       COUNT(*)                                   AS viewers,
       SUM(COALESCE(f.helpful, 0))                AS helpful_users,
       ROUND(1.0 * SUM(COALESCE(f.helpful, 0)) / COUNT(*), 4) AS helpful_rate
FROM viewers v
LEFT JOIN first_fb f ON f.user_id = v.user_id AND f.rn = 1
GROUP BY v.variant;

-- name: ab_secondary
-- 2차 지표: 재계산률(조건을 바꿔 다시 계산한 사용자 비율), 공유율
WITH u AS (
    SELECT user_id, variant,
           SUM(event = 'calc_submit') AS calcs,
           MAX(event = 'share_click') AS shared
    FROM events GROUP BY user_id, variant
)
SELECT variant,
       COUNT(*)                                       AS users,
       ROUND(AVG(calcs >= 2), 4)                      AS recalc_rate,
       ROUND(AVG(shared), 4)                          AS share_rate,
       ROUND(AVG(calcs), 3)                           AS avg_calcs
FROM u WHERE calcs >= 1
GROUP BY variant;

-- name: retention
-- 첫 방문일 기준 코호트별 D1 / D7 재방문율
WITH first_day AS (
    SELECT user_id, MIN(DATE(ts)) AS d0 FROM events GROUP BY user_id
),
activity AS (
    SELECT DISTINCT e.user_id, f.d0,
           CAST(julianday(DATE(e.ts)) - julianday(f.d0) AS INTEGER) AS dn
    FROM events e JOIN first_day f USING (user_id)
)
SELECT d0                                          AS cohort,
       COUNT(DISTINCT user_id)                     AS users,
       ROUND(1.0 * COUNT(DISTINCT CASE WHEN dn = 1 THEN user_id END) / COUNT(DISTINCT user_id), 4) AS d1,
       ROUND(1.0 * COUNT(DISTINCT CASE WHEN dn BETWEEN 1 AND 7 THEN user_id END) / COUNT(DISTINCT user_id), 4) AS d1_7
FROM activity
GROUP BY d0
ORDER BY d0;

-- name: acquisition
-- 유입 경로별 방문자와 계산 전환율 (?ref=everytime 같은 링크로 구분)
WITH first_visit AS (
    SELECT user_id, json_extract(props, '$.ref') AS ref,
           ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY ts) AS rn
    FROM events WHERE event = 'page_view'
),
calc AS (SELECT DISTINCT user_id FROM events WHERE event = 'calc_submit')
SELECT f.ref,
       COUNT(*)                                        AS users,
       ROUND(1.0 * COUNT(c.user_id) / COUNT(*), 4)     AS calc_rate
FROM first_visit f LEFT JOIN calc c USING (user_id)
WHERE f.rn = 1
GROUP BY f.ref
ORDER BY users DESC;

-- name: grade_mix
-- 사용자 점수 등급 분포 (첫 계산 기준) — 어떤 사용자층이 들어오는지
WITH first_calc AS (
    SELECT user_id, json_extract(props, '$.grade') AS grade,
           ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY ts) AS rn
    FROM events WHERE event = 'calc_submit'
)
SELECT grade, COUNT(*) AS users,
       ROUND(1.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 4) AS share
FROM first_calc WHERE rn = 1
GROUP BY grade ORDER BY grade;
