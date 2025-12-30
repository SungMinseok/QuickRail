from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user
from app import db
from app.models import User

bp = Blueprint('auth', __name__, url_prefix='/auth')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    """로그인 페이지"""
    if current_user.is_authenticated:
        return redirect(url_for('main.projects'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = request.form.get('remember', False)
        
        user = User.query.filter_by(email=email).first()
        
        if user:
            # 계정 활성화 체크
            if not user.is_active:
                flash('비활성화된 계정입니다. 관리자에게 문의하세요.', 'error')
                return render_template('auth/login.html')
            
            if user.check_password(password):
                login_user(user, remember=remember)
                next_page = request.args.get('next')
                return redirect(next_page or url_for('main.projects'))
        
        flash('이메일 또는 비밀번호가 올바르지 않습니다.', 'error')
    
    return render_template('auth/login.html')


@bp.route('/logout')
def logout():
    """로그아웃"""
    logout_user()
    flash('로그아웃되었습니다.', 'success')
    return redirect(url_for('auth.login'))


@bp.route('/register', methods=['GET', 'POST'])
def register():
    """사용자 등록"""
    if request.method == 'POST':
        email = request.form.get('email')
        name = request.form.get('name')
        password = request.form.get('password')
        
        # 이메일 중복 체크
        if User.query.filter_by(email=email).first():
            flash('이미 등록된 이메일입니다.', 'error')
            return redirect(url_for('auth.register'))
        
        # 비밀번호 길이 체크
        if len(password) < 6:
            flash('비밀번호는 최소 6자 이상이어야 합니다.', 'error')
            return redirect(url_for('auth.register'))
        
        # 새 사용자 생성 (기본 role=runner, admin@pubg.com은 자동으로 admin)
        role = 'admin' if email == 'admin@pubg.com' else 'runner'
        user = User(email=email, name=name, role=role, is_active=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('회원가입이 완료되었습니다. 로그인해주세요.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/register.html')


