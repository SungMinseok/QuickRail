"""데이터베이스 초기화 스크립트"""
from app import create_app, db
from app.models import User, Project

app = create_app()

with app.app_context():
    print('Initializing database...')
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
        print('[OK] Sample users created')
        print('  - admin@quickrail.com / admin123')
        print('  - author@quickrail.com / author123')
        print('  - runner@quickrail.com / runner123')
    else:
        print('[OK] Users already exist')
    
    # 샘플 프로젝트 생성
    if not Project.query.filter_by(name='Sample Project').first():
        project = Project(
            name='Sample Project',
            description='QuickRail Demo Project'
        )
        db.session.add(project)
        db.session.commit()
        print('[OK] Sample project created')
    else:
        print('[OK] Project already exists')
    
    print('\n=== Database initialized! ===')
    print('Run: python run.py')
    print('URL: http://localhost:5000')

