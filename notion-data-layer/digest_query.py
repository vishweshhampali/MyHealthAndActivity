PROJECT = "vishactivitytracker"
DATASET = "dbt_vish"

# landing_date is injected as a query parameter (see sync.py) — defaults to "yesterday"
DIGEST_SQL = f"""
WITH base AS (
  SELECT
    activity_date,
    COALESCE(running_minutes, 0) AS running_minutes,
    COALESCE(walking_minutes, 0) AS walking_minutes,
    COALESCE(gym_minutes, 0) AS gym_minutes,
    COALESCE(sports_minutes, 0) AS sports_minutes,
    COALESCE(total_active_minutes, 0) AS total_active_minutes,
    COALESCE(distance_millimeters, 0) / 1000000.0 AS distance_km,
    COALESCE(exercise_session_count, 0) AS exercise_session_count,
    (COALESCE(running_minutes, 0) > 0
      OR COALESCE(gym_minutes, 0) > 0
      OR COALESCE(sports_minutes, 0) > 0) AS trained
  FROM `{PROJECT}.{DATASET}.fct_activity_daily`
  WHERE activity_date <= @landing_date
),
-- fill any gap days as untrained so streaks/rolling windows aren't fooled by
-- days genuinely absent from the source table
spine AS (
  SELECT day AS activity_date
  FROM UNNEST(GENERATE_DATE_ARRAY((SELECT MIN(activity_date) FROM base), @landing_date)) AS day
),
filled AS (
  SELECT
    s.activity_date,
    COALESCE(b.trained, FALSE) AS trained,
    COALESCE(b.total_active_minutes, 0) AS total_active_minutes,
    COALESCE(b.running_minutes, 0) AS running_minutes,
    COALESCE(b.walking_minutes, 0) AS walking_minutes,
    COALESCE(b.gym_minutes, 0) AS gym_minutes,
    COALESCE(b.sports_minutes, 0) AS sports_minutes,
    COALESCE(b.distance_km, 0) AS distance_km,
    COALESCE(b.exercise_session_count, 0) AS exercise_session_count
  FROM spine s
  LEFT JOIN base b USING (activity_date)
),
streak_calc AS (
  SELECT *,
    SUM(CASE WHEN trained THEN 0 ELSE 1 END) OVER (ORDER BY activity_date) AS break_group
  FROM filled
),
target_break_group AS (
  SELECT break_group FROM streak_calc WHERE activity_date = @landing_date
),
current_streak AS (
  SELECT COUNT(*) AS streak_len
  FROM streak_calc, target_break_group
  WHERE streak_calc.trained AND streak_calc.break_group = target_break_group.break_group
),
last_trained AS (
  SELECT MAX(activity_date) AS last_trained_date
  FROM filled
  WHERE trained AND activity_date < @landing_date
),
week_bounds AS (
  SELECT DATE_TRUNC(@landing_date, WEEK(MONDAY)) AS week_start
),
weekly AS (
  SELECT COUNTIF(trained) AS deliberate_days_this_week
  FROM filled, week_bounds
  WHERE activity_date BETWEEN week_bounds.week_start AND @landing_date
),
rolling AS (
  SELECT
    SUM(CASE WHEN activity_date > DATE_SUB(@landing_date, INTERVAL 7 DAY) THEN total_active_minutes ELSE 0 END) AS minutes_7d,
    SUM(CASE WHEN activity_date > DATE_SUB(@landing_date, INTERVAL 28 DAY) THEN total_active_minutes ELSE 0 END) AS minutes_28d
  FROM filled
  WHERE activity_date <= @landing_date
)
SELECT
  f.activity_date,
  f.trained AS trained_today,
  f.running_minutes, f.walking_minutes, f.gym_minutes, f.sports_minutes,
  f.total_active_minutes,
  ROUND(f.distance_km, 2) AS distance_km,
  f.exercise_session_count,
  cs.streak_len AS current_streak_days,
  DATE_DIFF(@landing_date, lt.last_trained_date, DAY) AS days_since_last_session,
  w.deliberate_days_this_week,
  r.minutes_7d AS minutes_last_7d,
  r.minutes_28d AS minutes_last_28d,
  SAFE_DIVIDE(r.minutes_7d / 7, r.minutes_28d / 28) AS acwr_ratio
FROM filled f
CROSS JOIN current_streak cs
CROSS JOIN last_trained lt
CROSS JOIN weekly w
CROSS JOIN rolling r
WHERE f.activity_date = @landing_date
"""
