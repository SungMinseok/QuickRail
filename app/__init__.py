import os
import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from datetime import datetime
from flask import Flask, request
from werkzeug.exceptions import HTTPException
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from config import config

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()


def setup_logging(app):
    """로깅 설정"""
    # logs 폴더 생성
    logs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    
    # 로그 포맷 설정 (날짜와 시간 포함)
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 날짜별 로그 파일 핸들러 (매일 자정에 새 파일 생성)
    file_handler = TimedRotatingFileHandler(
        os.path.join(logs_dir, 'quickrail.log'),
        when='midnight',
        interval=1,
        backupCount=30,  # 30일치 로그 보관
        encoding='utf-8'
    )
    file_handler.suffix = '%Y-%m-%d.log'
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    
    # 에러 로그 파일 핸들러 (에러만 별도 저장)
    error_file_handler = TimedRotatingFileHandler(
        os.path.join(logs_dir, 'quickrail-error.log'),
        when='midnight',
        interval=1,
        backupCount=90,  # 90일치 에러 로그 보관
        encoding='utf-8'
    )
    error_file_handler.suffix = '%Y-%m-%d.log'
    error_file_handler.setFormatter(formatter)
    error_file_handler.setLevel(logging.ERROR)
    
    # 콘솔 핸들러 (개발 시 편의를 위해)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    
    # Flask 앱 로거 설정
    app.logger.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.addHandler(error_file_handler)
    app.logger.addHandler(console_handler)
    
    # Werkzeug 로거 설정 (Flask 내장 서버 로그)
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.setLevel(logging.INFO)
    werkzeug_logger.addHandler(file_handler)
    werkzeug_logger.addHandler(console_handler)
    
    # SQLAlchemy 로거 설정 (쿼리 로그는 DEBUG 레벨에서만)
    if app.debug:
        sqlalchemy_logger = logging.getLogger('sqlalchemy.engine')
        sqlalchemy_logger.setLevel(logging.WARNING)
        sqlalchemy_logger.addHandler(file_handler)
    
    app.logger.info('=' * 80)
    app.logger.info('QuickRail 애플리케이션 시작')
    app.logger.info(f'환경: {app.config.get("ENV", "production")}')
    app.logger.info(f'디버그 모드: {app.debug}')
    app.logger.info('=' * 80)


def create_app(config_name='default'):
    """Application factory pattern"""
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    try:
        app.logger.info(f'DB URI: {app.config.get("SQLALCHEMY_DATABASE_URI")}')
    except Exception:
        pass
    
    # 로깅 설정
    setup_logging(app)
    
    # Ensure instance folder exists (DB path uses instance/quickrail.db)
    try:
        instance_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance')
        os.makedirs(instance_dir, exist_ok=True)
    except Exception:
        pass

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    
    # Login manager settings
    login_manager.login_view = 'auth.login'
    login_manager.login_message = '로그인이 필요합니다.'
    
    # Create upload folder if it doesn't exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.logger.info(f'업로드 폴더 생성: {app.config["UPLOAD_FOLDER"]}')
    
    # 요청/응답 로깅
    @app.before_request
    def log_request():
        app.logger.info(f'{request.method} {request.path} - {request.remote_addr}')
    
    @app.after_request
    def log_response(response):
        app.logger.info(f'{request.method} {request.path} - {response.status_code}')
        return response
    
    # 브라우저가 자동으로 요청하는 favicon (없어도 되지만 404 노이즈 감소)
    @app.route('/favicon.ico')
    def favicon():
        return ('', 204)

    # 에러 핸들러
    @app.errorhandler(Exception)
    def handle_exception(e):
        # 404/403 등 HTTP 예외는 그대로 반환(현재는 Exception 핸들러가 전부 500으로 바꿔버리는 문제 방지)
        if isinstance(e, HTTPException):
            return e
        app.logger.error(f'처리되지 않은 예외 발생: {str(e)}', exc_info=True)
        return {'error': '서버 오류가 발생했습니다.'}, 500
    
    # Register blueprints
    from app.routes import auth, main, api
    app.register_blueprint(auth.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(api.bp)
    app.logger.info('블루프린트 등록 완료')
    
    # User loader
    from app.models import User
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    return app


