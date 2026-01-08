import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def _default_sqlite_db_url() -> str:
    # 표준 DB 위치: <project_root>/instance/quickrail.db (절대경로로 고정: CWD 영향 제거)
    root = Path(__file__).resolve().parent
    db_path = (root / "instance" / "quickrail.db").resolve()
    # Windows에서도 동작하는 형태: sqlite:///C:/.../instance/quickrail.db
    return f"sqlite:///{db_path.as_posix()}"


def _normalize_db_url(db_url: str | None) -> str:
    """DB URL 정규화.

    - 기본은 instance/quickrail.db로 통일
    - 과거/개발 중 생성된 per-user DB(예: instance/quickrail-*.db)로 인해 DB가 여러 개 생기는 문제를 방지
    - 예외적으로 다른 DB를 쓰고 싶으면 QUICKRAIL_ALLOW_CUSTOM_DB=1 설정
    """
    allow_custom = os.environ.get("QUICKRAIL_ALLOW_CUSTOM_DB") in ("1", "true", "True", "YES", "yes")
    if not db_url:
        return _default_sqlite_db_url()

    if allow_custom:
        return db_url

    # sqlite 상대 경로/레거시 경로 케이스들 정리
    if db_url.startswith("sqlite:///"):
        rel = db_url[len("sqlite:///") :]
        rel_norm = rel.replace("\\", "/")
        # root quickrail.db 또는 instance 내 변형 DB들을 모두 instance/quickrail.db로 통일
        if rel_norm == "quickrail.db":
            return _default_sqlite_db_url()
        if rel_norm.startswith("instance/quickrail-") and rel_norm.endswith(".db"):
            return _default_sqlite_db_url()
        if rel_norm == "instance/quickrail.db":
            return _default_sqlite_db_url()

    return db_url


class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = _normalize_db_url(os.environ.get('DATABASE_URL'))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # File upload settings
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    # 업로드 전체 요청 최대 크기(기본 64MB). 필요 시 환경변수로 조정 가능.
    # - QUICKRAIL_MAX_UPLOAD_MB=64  (정수)
    _max_upload_mb = int(os.environ.get('QUICKRAIL_MAX_UPLOAD_MB', '64') or '64')
    MAX_CONTENT_LENGTH = max(1, _max_upload_mb) * 1024 * 1024
    # 첨부파일 업로드 허용 확장자
    # - 이미지/동영상은 run_execute에서 사용
    ALLOWED_EXTENSIONS = {
        'png', 'jpg', 'jpeg', 'gif', 'webp',
        'mp4', 'mov', 'webm', 'avi', 'mkv',
        'zip', 'log', 'txt'
    }

    # 피드백 첨부(이미지/영상) 1개당 최대 크기 (기본 25MB)
    # - QUICKRAIL_FEEDBACK_ATTACHMENT_MAX_MB=25  (정수)
    FEEDBACK_ATTACHMENT_MAX_MB = int(os.environ.get('QUICKRAIL_FEEDBACK_ATTACHMENT_MAX_MB', '25') or '25')
    
    # Session settings
    SESSION_COOKIE_SECURE = False  # Set True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 86400  # 24 hours


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    SQLALCHEMY_ECHO = True


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    SESSION_COOKIE_SECURE = True


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}



