#!/usr/bin/env python
"""
QuickRail - Flask 애플리케이션 실행 스크립트
"""
import os
from app import create_app, db
from app.models import User, Project

# 환경 설정
config_name = os.environ.get('FLASK_ENV', 'development')
app = create_app(config_name)


@app.shell_context_processor
def make_shell_context():
    """Flask shell에서 사용할 컨텍스트"""
    return {
        'db': db,
        'User': User,
        'Project': Project
    }


@app.cli.command()
def init_db():
    """데이터베이스 초기화 및 샘플 데이터 생성"""
    print('데이터베이스 초기화 중...')
    db.create_all()
    
    # 샘플 사용자 생성
    if not User.query.filter_by(email='admin@quickrail.com').first():
        admin = User(
            email='admin@quickrail.com',
            name='Admin User',
            role='admin'
        )
        admin.set_password('admin123')
        db.session.add(admin)
        
        author = User(
            email='author@quickrail.com',
            name='Test Author',
            role='author'
        )
        author.set_password('author123')
        db.session.add(author)
        
        runner = User(
            email='runner@quickrail.com',
            name='Test Runner',
            role='runner'
        )
        runner.set_password('runner123')
        db.session.add(runner)
        
        db.session.commit()
        print('✓ 샘플 사용자 생성 완료')
        print('  - admin@quickrail.com / admin123')
        print('  - author@quickrail.com / author123')
        print('  - runner@quickrail.com / runner123')
    else:
        print('✓ 사용자가 이미 존재합니다')
    
    # 샘플 프로젝트 생성
    if not Project.query.filter_by(name='Sample Project').first():
        project = Project(
            name='Sample Project',
            description='QuickRail 데모 프로젝트'
        )
        db.session.add(project)
        db.session.commit()
        print('✓ 샘플 프로젝트 생성 완료')
    else:
        print('✓ 프로젝트가 이미 존재합니다')
    
    print('데이터베이스 초기화 완료!')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

