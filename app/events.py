"""이벤트 로깅.

- 로컬: SQLite (logs/events.db)
- 배포: Streamlit Cloud는 디스크가 재시작 때 초기화되므로, secrets의 DATABASE_URL에
  무료 Postgres(Supabase / Neon 등) 주소를 넣으면 그쪽에 저장한다.

개인정보 보호를 위해 입력값 원본은 저장하지 않고, 점수·등급·구간만 남긴다.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id    VARCHAR(36) PRIMARY KEY,
    ts          TIMESTAMP   NOT NULL,     -- UTC
    user_id     VARCHAR(36) NOT NULL,     -- 브라우저(URL)별 익명 ID
    session_id  VARCHAR(36) NOT NULL,     -- 접속 1회
    variant     VARCHAR(8)  NOT NULL,     -- A/B 실험군
    event       VARCHAR(32) NOT NULL,     -- page_view, calc_submit, result_view, tip_open, feedback, share_click
    props       TEXT                      -- JSON (score, grade, helpful 등)
)
"""


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        try:
            import streamlit as st
            url = st.secrets.get("DATABASE_URL")
        except Exception:
            url = None
    if url:
        # SQLAlchemy 2.1부터 'postgresql://'의 기본 드라이버가 psycopg(v3)로 바뀌었다.
        # requirements.txt의 psycopg2-binary를 쓰도록 드라이버를 명시한다.
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg2://" + url[len(prefix):]
        return url
    (ROOT / "logs").mkdir(exist_ok=True)
    return f"sqlite:///{ROOT / 'logs' / 'events.db'}"


_engine = None


def engine():
    global _engine
    if _engine is None:
        _engine = create_engine(_database_url(), pool_pre_ping=True)
        with _engine.begin() as c:
            c.execute(text(SCHEMA))
    return _engine


def log(event: str, *, user_id: str, session_id: str, variant: str,
        props: dict | None = None, ts: datetime | None = None) -> None:
    """로깅 실패가 서비스 장애로 이어지지 않도록 예외는 삼킨다."""
    try:
        with engine().begin() as c:
            c.execute(text("INSERT INTO events VALUES (:id, :ts, :u, :s, :v, :e, :p)"), {
                "id": str(uuid.uuid4()), "ts": (ts or datetime.now(timezone.utc)).replace(tzinfo=None),
                "u": user_id, "s": session_id, "v": variant, "e": event,
                "p": json.dumps(props or {}, ensure_ascii=False),
            })
    except Exception as e:  # pragma: no cover
        print("[events] log failed:", e)
