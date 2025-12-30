from flask import Blueprint, request, jsonify, current_app, send_file
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime
import os
from app import db
from app.models import Project, Section, Case, Tag, CaseTag, Run, RunCase, Result, Attachment, RunTemplate, User
from sqlalchemy import func

bp = Blueprint('api', __name__, url_prefix='/api')


def allowed_file(filename):
    """허용된 파일 확장자인지 확인"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


# ============ Auth API ============

@bp.route('/me', methods=['GET'])
@login_required
def get_me():
    """현재 사용자 정보"""
    return jsonify({
        'id': current_user.id,
        'email': current_user.email,
        'name': current_user.name,
        'role': current_user.role,
        'is_admin': current_user.is_admin()
    })


# ============ User Management API (Admin) ============

@bp.route('/users', methods=['GET'])
@login_required
def get_users():
    """모든 사용자 목록 (관리자 전용)"""
    if not current_user.is_admin():
        return jsonify({'error': '권한이 없습니다'}), 403
    
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify([{
        'id': u.id,
        'email': u.email,
        'name': u.name,
        'role': u.role,
        'is_active': u.is_active,
        'created_at': u.created_at.isoformat()
    } for u in users])


@bp.route('/users/<int:user_id>', methods=['PATCH', 'DELETE'])
@login_required
def manage_user(user_id):
    """사용자 수정/삭제 (관리자 전용)"""
    if not current_user.is_admin():
        return jsonify({'error': '권한이 없습니다'}), 403
    
    user = User.query.get_or_404(user_id)
    
    # admin@pubg.com은 수정/삭제 불가
    if user.email == 'admin@pubg.com':
        return jsonify({'error': 'Super Admin 계정은 수정/삭제할 수 없습니다'}), 403
    
    if request.method == 'PATCH':
        data = request.get_json()
        
        if 'role' in data:
            user.role = data['role']
        if 'is_active' in data:
            user.is_active = data['is_active']
        
        db.session.commit()
        return jsonify({'message': '사용자 정보가 업데이트되었습니다'})
    
    # DELETE
    # 자기 자신은 삭제 불가
    if user.id == current_user.id:
        return jsonify({'error': '자기 자신은 삭제할 수 없습니다'}), 403
    
    db.session.delete(user)
    db.session.commit()
    return '', 204


# ============ Profile API ============

@bp.route('/profile/name', methods=['PATCH'])
@login_required
def update_profile_name():
    """이름 변경"""
    data = request.get_json()
    name = data.get('name', '').strip()
    
    if not name:
        return jsonify({'error': '이름을 입력해주세요'}), 400
    
    current_user.name = name
    db.session.commit()
    
    return jsonify({'message': '이름이 변경되었습니다'})


@bp.route('/profile/password', methods=['PATCH'])
@login_required
def update_profile_password():
    """비밀번호 변경"""
    data = request.get_json()
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    
    if not current_password or not new_password:
        return jsonify({'error': '현재 비밀번호와 새 비밀번호를 입력해주세요'}), 400
    
    if not current_user.check_password(current_password):
        return jsonify({'error': '현재 비밀번호가 올바르지 않습니다'}), 400
    
    if len(new_password) < 6:
        return jsonify({'error': '비밀번호는 최소 6자 이상이어야 합니다'}), 400
    
    current_user.set_password(new_password)
    db.session.commit()
    
    return jsonify({'message': '비밀번호가 변경되었습니다'})


@bp.route('/profile', methods=['DELETE'])
@login_required
def delete_profile():
    """회원 탈퇴"""
    # admin@pubg.com은 탈퇴 불가
    if current_user.email == 'admin@pubg.com':
        return jsonify({'error': 'Super Admin 계정은 탈퇴할 수 없습니다'}), 403
    
    from flask_login import logout_user
    
    user_id = current_user.id
    logout_user()
    
    user = User.query.get(user_id)
    db.session.delete(user)
    db.session.commit()
    
    return jsonify({'message': '회원 탈퇴가 완료되었습니다'})


# ============ Project API ============

@bp.route('/projects', methods=['GET', 'POST'])
@login_required
def projects():
    """프로젝트 목록 조회 / 생성"""
    if request.method == 'GET':
        projects = Project.query.order_by(Project.updated_at.desc()).all()
        return jsonify([{
            'id': p.id,
            'name': p.name,
            'description': p.description,
            'created_at': p.created_at.isoformat(),
            'updated_at': p.updated_at.isoformat()
        } for p in projects])
    
    # POST: 프로젝트 생성 (admin, author만)
    if current_user.role not in ['admin', 'author']:
        return jsonify({'error': '권한이 없습니다'}), 403
    
    data = request.get_json()
    project = Project(
        name=data['name'],
        description=data.get('description', '')
    )
    db.session.add(project)
    db.session.commit()
    
    return jsonify({
        'id': project.id,
        'name': project.name,
        'description': project.description
    }), 201


@bp.route('/projects/<int:project_id>', methods=['GET'])
@login_required
def get_project(project_id):
    """프로젝트 상세"""
    project = Project.query.get_or_404(project_id)
    return jsonify({
        'id': project.id,
        'name': project.name,
        'description': project.description,
        'created_at': project.created_at.isoformat(),
        'updated_at': project.updated_at.isoformat()
    })


# ============ Section API ============

@bp.route('/projects/<int:project_id>/sections', methods=['GET', 'POST'])
@login_required
def sections(project_id):
    """섹션 목록 조회 / 생성"""
    project = Project.query.get_or_404(project_id)
    
    if request.method == 'GET':
        sections = Section.query.filter_by(project_id=project_id).order_by(Section.order_index).all()
        return jsonify([{
            'id': s.id,
            'name': s.name,
            'parent_id': s.parent_id,
            'order_index': s.order_index,
            'full_path': s.get_full_path()
        } for s in sections])
    
    # POST: 섹션 생성
    if current_user.role not in ['admin', 'author']:
        return jsonify({'error': '권한이 없습니다'}), 403
    
    data = request.get_json()
    
    # order_index 자동 계산
    max_order = db.session.query(func.max(Section.order_index)).filter_by(
        project_id=project_id,
        parent_id=data.get('parent_id')
    ).scalar() or 0
    
    section = Section(
        project_id=project_id,
        name=data['name'],
        parent_id=data.get('parent_id'),
        order_index=max_order + 1
    )
    db.session.add(section)
    db.session.commit()
    
    return jsonify({
        'id': section.id,
        'name': section.name,
        'parent_id': section.parent_id,
        'order_index': section.order_index
    }), 201


@bp.route('/sections/<int:section_id>', methods=['PATCH', 'DELETE'])
@login_required
def section(section_id):
    """섹션 수정 / 삭제"""
    if current_user.role not in ['admin', 'author']:
        return jsonify({'error': '권한이 없습니다'}), 403
    
    section = Section.query.get_or_404(section_id)
    
    if request.method == 'PATCH':
        data = request.get_json()
        
        if 'name' in data:
            section.name = data['name']
        if 'parent_id' in data:
            section.parent_id = data['parent_id']
        if 'order_index' in data:
            section.order_index = data['order_index']
        
        db.session.commit()
        
        return jsonify({
            'id': section.id,
            'name': section.name,
            'parent_id': section.parent_id,
            'order_index': section.order_index
        })
    
    # DELETE
    db.session.delete(section)
    db.session.commit()
    return '', 204


# ============ Case API ============

@bp.route('/projects/<int:project_id>/cases', methods=['GET', 'POST'])
@login_required
def cases(project_id):
    """케이스 목록 조회 / 생성"""
    project = Project.query.get_or_404(project_id)
    
    if request.method == 'GET':
        query = Case.query.filter_by(project_id=project_id)
        
        # 필터링
        section_id = request.args.get('section_id', type=int)
        search = request.args.get('q', '').strip()
        priority = request.args.get('priority')
        tag_name = request.args.get('tag')
        status = request.args.get('status', 'active')
        
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
        
        if status:
            query = query.filter_by(status=status)
        
        cases = query.order_by(Case.updated_at.desc()).all()
        
        return jsonify([{
            'id': c.id,
            'title': c.title,
            'section_id': c.section_id,
            'section_name': c.section.name,
            'priority': c.priority,
            'owner_id': c.owner_id,
            'owner_name': c.owner.name if c.owner else None,
            'status': c.status,
            'tags': [t.name for t in c.tags],
            'updated_at': c.updated_at.isoformat()
        } for c in cases])
    
    # POST: Quick Add 케이스 생성
    if current_user.role not in ['admin', 'author']:
        return jsonify({'error': '권한이 없습니다'}), 403
    
    data = request.get_json()
    
    case = Case(
        project_id=project_id,
        section_id=data['section_id'],
        title=data['title'],
        steps=data.get('steps', ''),
        expected_result=data.get('expected_result', ''),
        priority=data.get('priority', 'P2'),
        owner_id=data.get('owner_id')
    )
    db.session.add(case)
    db.session.flush()  # case.id 필요
    
    # 태그 처리
    if 'tags' in data:
        for tag_name in data['tags']:
            tag = Tag.query.filter_by(
                project_id=project_id,
                name=tag_name.lower()
            ).first()
            
            if not tag:
                tag = Tag(project_id=project_id, name=tag_name.lower())
                db.session.add(tag)
                db.session.flush()
            
            case_tag = CaseTag(case_id=case.id, tag_id=tag.id)
            db.session.add(case_tag)
    
    db.session.commit()
    
    return jsonify({
        'id': case.id,
        'title': case.title,
        'section_id': case.section_id,
        'priority': case.priority
    }), 201


@bp.route('/cases/<int:case_id>', methods=['GET', 'PATCH'])
@login_required
def case(case_id):
    """케이스 상세 조회 / 수정 (인라인 편집)"""
    case = Case.query.get_or_404(case_id)
    
    if request.method == 'GET':
        return jsonify({
            'id': case.id,
            'title': case.title,
            'section_id': case.section_id,
            'section_name': case.section.name,
            'steps': case.steps,
            'expected_result': case.expected_result,
            'priority': case.priority,
            'owner_id': case.owner_id,
            'owner_name': case.owner.name if case.owner else None,
            'status': case.status,
            'tags': [t.name for t in case.tags],
            'created_at': case.created_at.isoformat(),
            'updated_at': case.updated_at.isoformat()
        })
    
    # PATCH: Auto-save 인라인 편집
    if current_user.role not in ['admin', 'author']:
        return jsonify({'error': '권한이 없습니다'}), 403
    
    data = request.get_json()
    
    if 'title' in data:
        case.title = data['title']
    if 'order_index' in data:
        case.order_index = data['order_index']
    if 'steps' in data:
        case.steps = data['steps']
    if 'expected_result' in data:
        case.expected_result = data['expected_result']
    if 'priority' in data:
        case.priority = data['priority']
    if 'owner_id' in data:
        case.owner_id = data['owner_id']
    if 'section_id' in data:
        case.section_id = data['section_id']
    
    # 태그 업데이트
    if 'tags' in data:
        # 기존 태그 제거
        CaseTag.query.filter_by(case_id=case.id).delete()
        
        # 새 태그 추가
        for tag_name in data['tags']:
            tag = Tag.query.filter_by(
                project_id=case.project_id,
                name=tag_name.lower()
            ).first()
            
            if not tag:
                tag = Tag(project_id=case.project_id, name=tag_name.lower())
                db.session.add(tag)
                db.session.flush()
            
            case_tag = CaseTag(case_id=case.id, tag_id=tag.id)
            db.session.add(case_tag)
    
    db.session.commit()
    
    return jsonify({'status': 'saved', 'updated_at': case.updated_at.isoformat()})


@bp.route('/cases/<int:case_id>/archive', methods=['POST'])
@login_required
def archive_case(case_id):
    """케이스 아카이브"""
    if current_user.role not in ['admin', 'author']:
        return jsonify({'error': '권한이 없습니다'}), 403
    
    case = Case.query.get_or_404(case_id)
    case.status = 'archived'
    db.session.commit()
    
    return jsonify({'status': 'archived'})


@bp.route('/cases/<int:case_id>/unarchive', methods=['POST'])
@login_required
def unarchive_case(case_id):
    """케이스 복원"""
    if current_user.role not in ['admin', 'author']:
        return jsonify({'error': '권한이 없습니다'}), 403
    
    case = Case.query.get_or_404(case_id)
    case.status = 'active'
    db.session.commit()
    
    return jsonify({'status': 'active'})


@bp.route('/cases/<int:case_id>/copy', methods=['POST'])
@login_required
def copy_case(case_id):
    """케이스 복사"""
    if current_user.role not in ['admin', 'author']:
        return jsonify({'error': '권한이 없습니다'}), 403
    
    original_case = Case.query.get_or_404(case_id)
    data = request.get_json() or {}
    
    # 원본 케이스의 order_index 바로 다음에 삽입
    insert_after = data.get('insert_after')
    if insert_after is not None:
        new_order_index = original_case.order_index + 1
        # 이후 케이스들의 order_index 증가
        Case.query.filter(
            Case.section_id == original_case.section_id,
            Case.order_index >= new_order_index
        ).update({Case.order_index: Case.order_index + 1})
    else:
        new_order_index = original_case.order_index + 1
    
    # 새 케이스 생성
    new_case = Case(
        project_id=original_case.project_id,
        section_id=original_case.section_id,
        title=f"{original_case.title} (복사본)",
        steps=original_case.steps,
        expected_result=original_case.expected_result,
        priority=original_case.priority,
        owner_id=current_user.id,
        created_by=current_user.id,
        updated_by=current_user.id,
        order_index=new_order_index,
        status='active'
    )
    
    db.session.add(new_case)
    db.session.flush()
    
    # 태그 복사
    for tag in original_case.tags:
        new_case.tags.append(tag)
    
    db.session.commit()
    
    return jsonify({
        'id': new_case.id,
        'title': new_case.title,
        'message': '케이스가 복사되었습니다'
    }), 201


@bp.route('/projects/<int:project_id>/cases/check-duplicates', methods=['POST'])
@login_required
def check_duplicate_cases(project_id):
    """케이스 중복 감지 (제목 기반)"""
    project = Project.query.get_or_404(project_id)
    data = request.get_json()
    title = data.get('title', '').strip().lower()
    
    if not title:
        return jsonify({'duplicates': []})
    
    # 유사도 계산을 위한 간단한 알고리즘
    # 1. 정확히 일치
    # 2. 부분 문자열 포함
    # 3. 단어 기반 유사도
    
    all_cases = Case.query.filter_by(
        project_id=project_id,
        status='active'
    ).all()
    
    duplicates = []
    title_words = set(title.split())
    
    for case in all_cases:
        case_title_lower = case.title.lower()
        similarity_score = 0
        match_type = None
        
        # 정확히 일치
        if case_title_lower == title:
            similarity_score = 100
            match_type = 'exact'
        # 부분 문자열 포함
        elif title in case_title_lower or case_title_lower in title:
            similarity_score = 80
            match_type = 'substring'
        else:
            # 단어 기반 유사도
            case_words = set(case_title_lower.split())
            common_words = title_words.intersection(case_words)
            if common_words:
                similarity_score = int((len(common_words) / max(len(title_words), len(case_words))) * 70)
                match_type = 'words'
        
        if similarity_score >= 50:  # 50% 이상 유사도
            duplicates.append({
                'id': case.id,
                'title': case.title,
                'section_name': case.section.name,
                'priority': case.priority,
                'similarity': similarity_score,
                'match_type': match_type,
                'updated_at': case.updated_at.isoformat()
            })
    
    # 유사도 순으로 정렬
    duplicates.sort(key=lambda x: x['similarity'], reverse=True)
    
    return jsonify({
        'duplicates': duplicates[:5],  # 상위 5개만
        'count': len(duplicates)
    })


# ============ Tag API ============

@bp.route('/projects/<int:project_id>/tags', methods=['GET', 'POST'])
@login_required
def tags(project_id):
    """태그 목록 조회 / 생성"""
    project = Project.query.get_or_404(project_id)
    
    if request.method == 'GET':
        tags = Tag.query.filter_by(project_id=project_id).order_by(Tag.name).all()
        return jsonify([{
            'id': t.id,
            'name': t.name
        } for t in tags])
    
    # POST
    if current_user.role not in ['admin', 'author']:
        return jsonify({'error': '권한이 없습니다'}), 403
    
    data = request.get_json()
    tag_name = data['name'].lower()
    
    # 중복 체크
    existing = Tag.query.filter_by(project_id=project_id, name=tag_name).first()
    if existing:
        return jsonify({'id': existing.id, 'name': existing.name})
    
    tag = Tag(project_id=project_id, name=tag_name)
    db.session.add(tag)
    db.session.commit()
    
    return jsonify({'id': tag.id, 'name': tag.name}), 201


# ============ Run API ============

@bp.route('/projects/<int:project_id>/runs', methods=['GET', 'POST'])
@login_required
def runs(project_id):
    """런 목록 조회 / 생성"""
    project = Project.query.get_or_404(project_id)
    
    if request.method == 'GET':
        runs = Run.query.filter_by(project_id=project_id).order_by(Run.created_at.desc()).all()
        return jsonify([{
            'id': r.id,
            'name': r.name,
            'description': r.description,
            'run_type': r.run_type,
            'is_closed': r.is_closed,
            'created_by': r.creator.name,
            'created_at': r.created_at.isoformat(),
            'stats': r.get_stats()
        } for r in runs])
    
    # POST: 런 생성
    data = request.get_json()
    
    run = Run(
        project_id=project_id,
        name=data['name'],
        description=data.get('description', ''),
        created_by=current_user.id,
        run_type=data.get('run_type', 'custom')
    )
    db.session.add(run)
    db.session.flush()
    
    # RunCase 스냅샷 생성
    case_ids = data.get('case_ids', [])
    for idx, case_id in enumerate(case_ids):
        run_case = RunCase(
            run_id=run.id,
            case_id=case_id,
            order_index=idx
        )
        db.session.add(run_case)
    
    db.session.commit()
    
    return jsonify({
        'id': run.id,
        'name': run.name,
        'case_count': len(case_ids)
    }), 201


@bp.route('/runs/<int:run_id>', methods=['GET', 'DELETE'])
@login_required
def get_run(run_id):
    """런 상세 / 삭제"""
    run = Run.query.get_or_404(run_id)
    
    if request.method == 'DELETE':
        # 권한 체크 (생성자 또는 admin/author)
        if run.created_by != current_user.id and current_user.role not in ['admin', 'author']:
            return jsonify({'error': '권한이 없습니다'}), 403
        
        db.session.delete(run)
        db.session.commit()
        return '', 204
    
    return jsonify({
        'id': run.id,
        'name': run.name,
        'description': run.description,
        'run_type': run.run_type,
        'is_closed': run.is_closed,
        'created_by': run.creator.name,
        'created_at': run.created_at.isoformat(),
        'stats': run.get_stats()
    })


@bp.route('/runs/<int:run_id>/close', methods=['POST'])
@login_required
def close_run(run_id):
    """런 종료"""
    run = Run.query.get_or_404(run_id)
    run.is_closed = True
    db.session.commit()
    
    return jsonify({'is_closed': True})


@bp.route('/runs/<int:run_id>/reopen', methods=['POST'])
@login_required
def reopen_run(run_id):
    """런 재오픈"""
    run = Run.query.get_or_404(run_id)
    run.is_closed = False
    db.session.commit()
    
    return jsonify({'is_closed': False})


# ============ Run Execution API ============

@bp.route('/runs/<int:run_id>/cases', methods=['GET'])
@login_required
def run_cases(run_id):
    """런의 케이스 목록 (최신 결과 포함)"""
    run = Run.query.get_or_404(run_id)
    run_cases = run.run_cases.order_by(RunCase.order_index).all()
    
    result_list = []
    for rc in run_cases:
        latest_result = rc.get_latest_result()
        result_list.append({
            'run_case_id': rc.id,
            'case_id': rc.case_id,
            'case_title': rc.case.title,
            'case_steps': rc.case.steps,
            'case_expected': rc.case.expected_result,
            'case_priority': rc.case.priority,
            'result': {
                'id': latest_result.id,
                'status': latest_result.status,
                'comment': latest_result.comment,
                'executor': latest_result.executor.name,
                'created_at': latest_result.created_at.isoformat()
            } if latest_result else None
        })
    
    return jsonify(result_list)


@bp.route('/runs/<int:run_id>/results', methods=['POST'])
@login_required
def create_result(run_id):
    """결과 기록 (핫키 실행)"""
    run = Run.query.get_or_404(run_id)
    data = request.get_json()
    
    # 해당 케이스에 대한 최신 결과가 있는지 확인
    existing_result = Result.query.filter_by(
        run_id=run_id,
        case_id=data['case_id']
    ).order_by(Result.created_at.desc()).first()
    
    # 기존 결과가 있고, 같은 실행자가 바로 업데이트하는 경우 (5분 이내)
    from datetime import datetime, timedelta
    if existing_result and existing_result.executor_id == current_user.id:
        time_diff = datetime.utcnow() - existing_result.created_at
        if time_diff < timedelta(minutes=5):
            # 기존 결과 업데이트
            existing_result.status = data['status']
            existing_result.comment = data.get('comment', '')
            existing_result.created_at = datetime.utcnow()
            db.session.commit()
            
            return jsonify({
                'id': existing_result.id,
                'status': existing_result.status,
                'created_at': existing_result.created_at.isoformat()
            }), 200
    
    # 새 결과 생성 (다른 실행자이거나 시간이 많이 지난 경우)
    result = Result(
        run_id=run_id,
        case_id=data['case_id'],
        executor_id=current_user.id,
        status=data['status'],
        comment=data.get('comment', '')
    )
    db.session.add(result)
    db.session.commit()
    
    return jsonify({
        'id': result.id,
        'status': result.status,
        'created_at': result.created_at.isoformat()
    }), 201


@bp.route('/runs/<int:run_id>/results', methods=['GET'])
@login_required
def get_results(run_id):
    """런의 모든 결과"""
    run = Run.query.get_or_404(run_id)
    results = Result.query.filter_by(run_id=run_id).order_by(Result.created_at.desc()).all()
    
    return jsonify([{
        'id': r.id,
        'case_id': r.case_id,
        'case_title': r.case.title,
        'status': r.status,
        'comment': r.comment,
        'executor': r.executor.name,
        'created_at': r.created_at.isoformat()
    } for r in results])


# ============ Attachment API ============

@bp.route('/results/<int:result_id>/attachments', methods=['POST'])
@login_required
def upload_attachment(result_id):
    """첨부파일 업로드"""
    result = Result.query.get_or_404(result_id)
    
    if 'file' not in request.files:
        return jsonify({'error': '파일이 없습니다'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': '파일이 선택되지 않았습니다'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # 파일명 중복 방지
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{filename}"
        
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        attachment = Attachment(
            result_id=result_id,
            file_path=filepath,
            original_name=file.filename
        )
        db.session.add(attachment)
        db.session.commit()
        
        return jsonify({
            'id': attachment.id,
            'original_name': attachment.original_name,
            'created_at': attachment.created_at.isoformat()
        }), 201
    
    return jsonify({'error': '허용되지 않은 파일 형식입니다'}), 400


@bp.route('/attachments/<int:attachment_id>', methods=['GET'])
@login_required
def get_attachment(attachment_id):
    """첨부파일 다운로드"""
    attachment = Attachment.query.get_or_404(attachment_id)
    return send_file(attachment.file_path, as_attachment=True, download_name=attachment.original_name)


# ============ Run Template API (Phase 2) ============

@bp.route('/projects/<int:project_id>/run-templates', methods=['GET', 'POST'])
@login_required
def run_templates(project_id):
    """런 템플릿 목록 조회 / 생성"""
    project = Project.query.get_or_404(project_id)
    
    if request.method == 'GET':
        # 공개 템플릿 + 내가 만든 비공개 템플릿
        templates = RunTemplate.query.filter(
            RunTemplate.project_id == project_id,
            db.or_(
                RunTemplate.is_public == True,
                RunTemplate.created_by == current_user.id
            )
        ).order_by(RunTemplate.updated_at.desc()).all()
        
        return jsonify([{
            'id': t.id,
            'name': t.name,
            'description': t.description,
            'run_type': t.run_type,
            'is_public': t.is_public,
            'created_by': t.creator.name,
            'is_mine': t.created_by == current_user.id,
            'case_count': len(t.case_ids.split(',')) if t.case_ids else 0,
            'created_at': t.created_at.isoformat(),
            'updated_at': t.updated_at.isoformat()
        } for t in templates])
    
    # POST: 템플릿 생성
    data = request.get_json()
    
    template = RunTemplate(
        project_id=project_id,
        name=data['name'],
        description=data.get('description', ''),
        created_by=current_user.id,
        case_ids=','.join(map(str, data.get('case_ids', []))),
        filter_json=data.get('filter_json'),
        run_type=data.get('run_type', 'custom'),
        is_public=data.get('is_public', True)
    )
    db.session.add(template)
    db.session.commit()
    
    return jsonify({
        'id': template.id,
        'name': template.name,
        'message': '템플릿이 저장되었습니다'
    }), 201


@bp.route('/run-templates/<int:template_id>', methods=['GET', 'PATCH', 'DELETE'])
@login_required
def run_template(template_id):
    """런 템플릿 상세 / 수정 / 삭제"""
    template = RunTemplate.query.get_or_404(template_id)
    
    # 권한 체크 (본인 또는 admin)
    if request.method in ['PATCH', 'DELETE']:
        if template.created_by != current_user.id and current_user.role != 'admin':
            return jsonify({'error': '권한이 없습니다'}), 403
    
    if request.method == 'GET':
        case_ids = [int(id) for id in template.case_ids.split(',') if id] if template.case_ids else []
        
        return jsonify({
            'id': template.id,
            'name': template.name,
            'description': template.description,
            'run_type': template.run_type,
            'is_public': template.is_public,
            'case_ids': case_ids,
            'filter_json': template.filter_json,
            'created_by': template.creator.name,
            'created_at': template.created_at.isoformat()
        })
    
    if request.method == 'PATCH':
        data = request.get_json()
        
        if 'name' in data:
            template.name = data['name']
        if 'description' in data:
            template.description = data['description']
        if 'case_ids' in data:
            template.case_ids = ','.join(map(str, data['case_ids']))
        if 'run_type' in data:
            template.run_type = data['run_type']
        if 'is_public' in data:
            template.is_public = data['is_public']
        
        db.session.commit()
        return jsonify({'message': '템플릿이 업데이트되었습니다'})
    
    # DELETE
    db.session.delete(template)
    db.session.commit()
    return '', 204


@bp.route('/run-templates/<int:template_id>/create-run', methods=['POST'])
@login_required
def create_run_from_template(template_id):
    """템플릿으로부터 런 생성"""
    template = RunTemplate.query.get_or_404(template_id)
    data = request.get_json()
    
    # 런 이름 자동 생성 (템플릿 이름 + 날짜)
    from datetime import datetime
    default_name = f"{template.name} - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    
    run = Run(
        project_id=template.project_id,
        name=data.get('name', default_name),
        description=data.get('description', template.description),
        created_by=current_user.id,
        run_type=template.run_type or 'custom'
    )
    db.session.add(run)
    db.session.flush()
    
    # 템플릿의 케이스로 RunCase 생성
    case_ids = [int(id) for id in template.case_ids.split(',') if id] if template.case_ids else []
    for idx, case_id in enumerate(case_ids):
        run_case = RunCase(
            run_id=run.id,
            case_id=case_id,
            order_index=idx
        )
        db.session.add(run_case)
    
    db.session.commit()
    
    return jsonify({
        'id': run.id,
        'name': run.name,
        'case_count': len(case_ids),
        'message': '템플릿으로부터 런이 생성되었습니다'
    }), 201


# ============ Analytics API (Phase 2) ============

@bp.route('/projects/<int:project_id>/analytics/failed-cases', methods=['GET'])
@login_required
def get_failed_cases(project_id):
    """최근 실패 많은 케이스 Top"""
    project = Project.query.get_or_404(project_id)
    
    # 최근 30일 내 결과 집계
    from datetime import datetime, timedelta
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    # 케이스별 실패 횟수 집계
    failed_results = db.session.query(
        Result.case_id,
        func.count(Result.id).label('fail_count'),
        func.max(Result.created_at).label('last_failed')
    ).filter(
        Result.status == 'fail',
        Result.created_at >= thirty_days_ago
    ).join(
        Case, Result.case_id == Case.id
    ).filter(
        Case.project_id == project_id,
        Case.status == 'active'
    ).group_by(
        Result.case_id
    ).order_by(
        func.count(Result.id).desc()
    ).limit(10).all()
    
    result_list = []
    for case_id, fail_count, last_failed in failed_results:
        case = Case.query.get(case_id)
        if case:
            result_list.append({
                'case_id': case.id,
                'title': case.title,
                'section_name': case.section.name,
                'priority': case.priority,
                'fail_count': fail_count,
                'last_failed': last_failed.isoformat()
            })
    
    return jsonify(result_list)


@bp.route('/projects/<int:project_id>/analytics/stale-cases', methods=['GET'])
@login_required
def get_stale_cases(project_id):
    """오래된 케이스 (90일 이상 미수정)"""
    project = Project.query.get_or_404(project_id)
    
    from datetime import datetime, timedelta
    ninety_days_ago = datetime.utcnow() - timedelta(days=90)
    
    stale_cases = Case.query.filter(
        Case.project_id == project_id,
        Case.status == 'active',
        Case.updated_at < ninety_days_ago
    ).order_by(
        Case.updated_at.asc()
    ).limit(20).all()
    
    return jsonify([{
        'id': c.id,
        'title': c.title,
        'section_name': c.section.name,
        'priority': c.priority,
        'updated_at': c.updated_at.isoformat(),
        'days_ago': (datetime.utcnow() - c.updated_at).days
    } for c in stale_cases])


@bp.route('/projects/<int:project_id>/analytics/flaky-cases', methods=['GET'])
@login_required
def get_flaky_cases(project_id):
    """불안정한 케이스 (Pass/Fail이 번갈아 나타나는 케이스)"""
    project = Project.query.get_or_404(project_id)
    
    from datetime import datetime, timedelta
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    # 최근 결과가 있는 케이스들
    cases_with_results = db.session.query(
        Result.case_id,
        func.count(Result.id).label('total_count'),
        func.sum(db.case((Result.status == 'pass', 1), else_=0)).label('pass_count'),
        func.sum(db.case((Result.status == 'fail', 1), else_=0)).label('fail_count')
    ).filter(
        Result.created_at >= thirty_days_ago
    ).join(
        Case, Result.case_id == Case.id
    ).filter(
        Case.project_id == project_id,
        Case.status == 'active'
    ).group_by(
        Result.case_id
    ).having(
        func.count(Result.id) >= 3  # 최소 3번 이상 실행
    ).all()
    
    flaky_list = []
    for case_id, total, pass_count, fail_count in cases_with_results:
        # Pass와 Fail이 모두 있고, 둘 다 20% 이상인 경우
        if pass_count > 0 and fail_count > 0:
            pass_rate = (pass_count / total) * 100
            if 20 <= pass_rate <= 80:  # 불안정한 범위
                case = Case.query.get(case_id)
                if case:
                    flaky_list.append({
                        'case_id': case.id,
                        'title': case.title,
                        'section_name': case.section.name,
                        'priority': case.priority,
                        'total_runs': total,
                        'pass_count': pass_count,
                        'fail_count': fail_count,
                        'pass_rate': round(pass_rate, 1),
                        'flaky_score': round(abs(50 - pass_rate), 1)  # 50%에서 멀수록 덜 불안정
                    })
    
    # Flaky score로 정렬 (50%에 가까울수록 더 불안정)
    flaky_list.sort(key=lambda x: x['flaky_score'])
    
    return jsonify(flaky_list[:10])


