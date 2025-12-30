from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from app import db
from app.models import Project, Section, Case, Run, Tag, User

bp = Blueprint('main', __name__)


@bp.route('/')
def index():
    """메인 페이지"""
    if current_user.is_authenticated:
        return redirect(url_for('main.projects'))
    return redirect(url_for('auth.login'))


@bp.route('/projects')
@login_required
def projects():
    """프로젝트 목록"""
    projects = Project.query.order_by(Project.updated_at.desc()).all()
    return render_template('main/projects.html', projects=projects)


@bp.route('/p/<int:project_id>/cases')
@login_required
def cases(project_id):
    """케이스 관리 화면 (2-pane: Section 트리 + Case 리스트)"""
    project = Project.query.get_or_404(project_id)
    
    # 쿼리 파라미터로 필터링
    section_id = request.args.get('section_id', type=int)
    search = request.args.get('q', '').strip()
    priority = request.args.get('priority')
    tag_name = request.args.get('tag')
    
    # Section 트리 (루트 섹션들만) - 재귀적으로 자식 로드
    def load_section_tree(parent_id=None, depth=0):
        """섹션 트리를 재귀적으로 로드 (최대 4단계)"""
        if depth >= 4:
            return []
        
        sections = Section.query.filter_by(
            project_id=project_id,
            parent_id=parent_id
        ).order_by(Section.order_index).all()
        
        for section in sections:
            section.children = load_section_tree(section.id, depth + 1)
        
        return sections
    
    sections = load_section_tree()
    
    # Case 쿼리 빌드
    query = Case.query.filter_by(project_id=project_id, status='active')
    
    if section_id:
        query = query.filter_by(section_id=section_id)
    
    if search:
        search_pattern = f'%{search}%'
        query = query.filter(
            db.or_(
                Case.title.ilike(search_pattern),
                Case.steps.ilike(search_pattern),
                Case.expected_result.ilike(search_pattern)
            )
        )
    
    if priority:
        query = query.filter_by(priority=priority)
    
    if tag_name:
        query = query.join(Case.tags).filter(Tag.name == tag_name)
    
    # 정렬
    sort = request.args.get('sort', 'default')
    if sort == 'oldest':
        query = query.order_by(Case.updated_at.asc())
    elif sort == 'title':
        query = query.order_by(Case.title.asc())
    elif sort == 'priority':
        # Critical > High > Medium > Low
        priority_order = db.case(
            (Case.priority == 'Critical', 0),
            (Case.priority == 'High', 1),
            (Case.priority == 'Medium', 2),
            (Case.priority == 'Low', 3),
            else_=4
        )
        query = query.order_by(priority_order)
    elif sort == 'recent':
        query = query.order_by(Case.updated_at.desc())
    else:  # default - 섹션 내 순서
        query = query.order_by(Case.order_index.asc(), Case.created_at.asc())
    
    cases = query.all()
    
    # 프로젝트의 모든 태그
    tags = Tag.query.filter_by(project_id=project_id).order_by(Tag.name).all()
    
    return render_template('main/cases.html',
                         project=project,
                         sections=sections,
                         cases=cases,
                         tags=tags,
                         current_section_id=section_id,
                         search=search,
                         priority=priority,
                         selected_tag=tag_name,
                         current_sort=request.args.get('sort', 'recent'))


@bp.route('/p/<int:project_id>/runs')
@login_required
def runs(project_id):
    """런 목록"""
    project = Project.query.get_or_404(project_id)
    
    # Open runs와 closed runs 분리
    open_runs = Run.query.filter_by(
        project_id=project_id,
        is_closed=False
    ).order_by(Run.created_at.desc()).all()
    
    closed_runs = Run.query.filter_by(
        project_id=project_id,
        is_closed=True
    ).order_by(Run.created_at.desc()).limit(20).all()
    
    return render_template('main/runs.html',
                         project=project,
                         open_runs=open_runs,
                         closed_runs=closed_runs)


@bp.route('/runs/<int:run_id>')
@login_required
def run_execute(run_id):
    """런 실행 화면 (핫키 지원)"""
    run = Run.query.get_or_404(run_id)
    
    # RunCase 목록
    run_cases = run.run_cases.order_by('order_index').all()
    
    # 각 RunCase의 최신 결과 가져오기 (JSON 직렬화 가능하도록 딕셔너리로 변환)
    run_cases_with_results = []
    for rc in run_cases:
        result = rc.get_latest_result()
        run_cases_with_results.append({
            'run_case': {
                'id': rc.id,
                'run_id': rc.run_id,
                'case_id': rc.case_id,
                'order_index': rc.order_index
            },
            'case': {
                'id': rc.case.id,
                'title': rc.case.title,
                'steps': rc.case.steps or '',
                'expected': rc.case.expected_result or '',
                'priority': rc.case.priority
            },
            'result': {
                'id': result.id,
                'status': result.status,
                'comment': result.comment or '',
                'executor': result.executor.name,
                'created_at': result.created_at.isoformat()
            } if result else None
        })
    
    # 통계
    stats = run.get_stats()
    
    return render_template('main/run_execute.html',
                         run=run,
                         run_cases=run_cases_with_results,
                         stats=stats)


@bp.route('/p/<int:project_id>/dashboard')
@login_required
def dashboard(project_id):
    """프로젝트 대시보드 (리포트)"""
    project = Project.query.get_or_404(project_id)
    
    # 최근 런들
    recent_runs = Run.query.filter_by(
        project_id=project_id
    ).order_by(Run.created_at.desc()).limit(10).all()
    
    # 각 런의 통계
    runs_with_stats = []
    for run in recent_runs:
        runs_with_stats.append({
            'run': run,
            'stats': run.get_stats()
        })
    
    return render_template('main/dashboard.html',
                         project=project,
                         runs_with_stats=runs_with_stats)


@bp.route('/users/manage')
@login_required
def manage_users():
    """회원 관리 (관리자 전용)"""
    if not current_user.is_admin():
        flash('관리자만 접근할 수 있습니다.', 'error')
        return redirect(url_for('main.projects'))
    
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('main/manage_users.html', users=users)


@bp.route('/profile')
@login_required
def profile():
    """계정 정보"""
    return render_template('main/profile.html')


