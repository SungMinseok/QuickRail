from flask import Blueprint, request, jsonify, current_app, send_file
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import requests
import mimetypes
from app import db
from app.models import Project, Section, Case, Tag, CaseTag, Run, RunCase, Result, Attachment, RunTemplate, User, CaseTranslation, TranslationPrompt, APIKey, TranslationUsage, JiraConfig, ActivityLog, CaseJiraLink, CaseMedia
from app.utils.translator import detect_language, translate_case, translate_cases_batch, TranslationError
from app.utils.activity import log_activity_safe
from sqlalchemy import func
from sqlalchemy.orm import selectinload, joinedload

bp = Blueprint('api', __name__, url_prefix='/api')


def _ensure_case_translations(case_ids, target_lang: str, force: bool = False):
    """
    cases.html changeLanguage()와 동일한 규칙:
    - target_lang 캐시가 있으면 사용
    - 없으면 번역 후 CaseTranslation으로 저장
    - force=True면 해당 target_lang 캐시를 삭제 후 재번역

    Returns:
      (cached_translations: dict[int, dict], translated_count: int, cached_count: int)
    """
    if not case_ids or not target_lang:
        return {}, 0, 0

    case_ids = [int(x) for x in case_ids if str(x).isdigit()]
    if not case_ids:
        return {}, 0, 0

    if force:
        CaseTranslation.query.filter(
            CaseTranslation.case_id.in_(case_ids),
            CaseTranslation.target_lang == target_lang
        ).delete(synchronize_session=False)
        db.session.commit()

    cases_to_translate = []
    cached_translations = {}

    for case_id in case_ids:
        case = Case.query.get(case_id)
        if not case:
            continue

        source_lang = detect_language(case.title)
        cached = CaseTranslation.query.filter_by(
            case_id=case_id,
            target_lang=target_lang
        ).first()

        if cached and not force:
            cached_translations[case_id] = {
                'title': cached.title,
                'steps': cached.steps,
                'expected_result': cached.expected_result
            }
        else:
            cases_to_translate.append({
                'case_id': case_id,
                'title': case.title,
                'steps': case.steps,
                'expected_result': case.expected_result,
                'source_lang': source_lang
            })

    if cases_to_translate:
        by_source_lang = {}
        for case_data in cases_to_translate:
            src = case_data['source_lang']
            by_source_lang.setdefault(src, []).append(case_data)

        for source_lang, cases in by_source_lang.items():
            translated_results = translate_cases_batch(cases, source_lang, target_lang)
            for result in translated_results:
                cid = result['case_id']
                translation = result.get('translation')
                if not translation:
                    continue
                db.session.add(CaseTranslation(
                    case_id=cid,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    title=translation.get('title'),
                    steps=translation.get('steps'),
                    expected_result=translation.get('expected_result')
                ))
                cached_translations[cid] = translation

        db.session.commit()

    translated_count = len(cases_to_translate)
    cached_count = 0 if force else max(0, len(cached_translations) - translated_count)
    return cached_translations, translated_count, cached_count

# ============================================================
# Presence (Online users) - lightweight in-memory tracker
# NOTE: 개발/단일 프로세스 기준. 멀티프로세스/멀티서버 환경에서는 Redis/DB 기반으로 교체 필요.
# ============================================================
_ONLINE_USERS = {}  # user_id -> {id, name, last_seen_ms}
_PRESENCE_TTL_MS = 90 * 1000  # 90초 내 heartbeat가 있으면 온라인으로 간주

def _presence_cleanup(now_ms: int):
    stale = [uid for uid, v in _ONLINE_USERS.items() if now_ms - v.get('last_seen_ms', 0) > _PRESENCE_TTL_MS]
    for uid in stale:
        _ONLINE_USERS.pop(uid, None)


def allowed_file(filename):
    """허용된 파일 확장자인지 확인"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


def _get_or_create_artifact_result(run_id: int, case_id: int) -> Result:
    """
    결과(status) 없이도 버그링크/첨부파일을 저장할 수 있도록,
    (run_id, case_id) 단위로 하나의 'artifact' Result를 유지한다.
    """
    existing = Result.query.filter_by(run_id=run_id, case_id=case_id, status='artifact').first()
    if existing:
        return existing

    r = Result(
        run_id=run_id,
        case_id=case_id,
        executor_id=current_user.id,
        status='artifact',
        comment='',
        bug_links=''
    )
    db.session.add(r)
    db.session.commit()
    return r


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


@bp.route('/online-users-panel-state', methods=['POST'])
@login_required
def set_online_users_panel_state():
    """접속자 패널 접기/펼치기 상태 저장"""
    from flask import session
    data = request.get_json()
    session['onlineUsersPanelCollapsed'] = data.get('collapsed', False)
    return jsonify({'status': 'ok'})


@bp.route('/presence/heartbeat', methods=['POST'])
@login_required
def presence_heartbeat():
    """현재 사용자의 온라인 상태(heartbeat) 갱신"""
    now_ms = int(datetime.utcnow().timestamp() * 1000)
    _ONLINE_USERS[current_user.id] = {
        'id': current_user.id,
        'name': current_user.name,
        'last_seen_ms': now_ms
    }
    _presence_cleanup(now_ms)
    users = sorted(_ONLINE_USERS.values(), key=lambda u: (u['name'] or '').lower())
    return jsonify({'count': len(users), 'users': users})


@bp.route('/presence/online', methods=['GET'])
@login_required
def presence_online():
    """온라인 사용자 목록"""
    now_ms = int(datetime.utcnow().timestamp() * 1000)
    _presence_cleanup(now_ms)
    users = sorted(_ONLINE_USERS.values(), key=lambda u: (u['name'] or '').lower())
    return jsonify({'count': len(users), 'users': users})


# ============ User Management API (Admin) ============

@bp.route('/users', methods=['GET'])
@login_required
def get_users():
    """모든 사용자 목록 (Super Admin 전용)"""
    if not current_user.is_super_admin():
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
    """사용자 수정/삭제 (Super Admin 전용)"""
    if not current_user.is_super_admin():
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

    log_activity_safe(
        user_id=current_user.id,
        action='profile.name.update',
        entity_type='user',
        entity_id=current_user.id,
        description=f'이름 변경: {name}',
    )
    
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

    log_activity_safe(
        user_id=current_user.id,
        action='profile.password.update',
        entity_type='user',
        entity_id=current_user.id,
        description='비밀번호 변경',
    )
    
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


@bp.route('/profile/avatar', methods=['GET', 'POST', 'DELETE'])
@login_required
def profile_avatar():
    """프로필 이미지 조회/업로드/삭제"""
    # GET: 현재 사용자 아바타 반환
    if request.method == 'GET':
        filename = current_user.avatar_filename
        if not filename:
            return jsonify({'error': '프로필 이미지가 없습니다'}), 404

        avatar_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'avatars')
        filepath = os.path.join(avatar_dir, filename)
        if not os.path.exists(filepath):
            return jsonify({'error': '프로필 이미지 파일을 찾을 수 없습니다'}), 404
        return send_file(filepath)

    # DELETE: 아바타 제거
    if request.method == 'DELETE':
        old = current_user.avatar_filename
        current_user.avatar_filename = None
        db.session.commit()

        if old:
            try:
                avatar_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'avatars')
                old_path = os.path.join(avatar_dir, old)
                if os.path.exists(old_path):
                    os.remove(old_path)
            except Exception:
                pass

        log_activity_safe(
            user_id=current_user.id,
            action='profile.avatar.delete',
            entity_type='user',
            entity_id=current_user.id,
            description='프로필 이미지 삭제',
        )
        return jsonify({'message': '프로필 이미지가 삭제되었습니다'})

    # POST: 업로드
    if 'file' not in request.files:
        return jsonify({'error': '파일이 없습니다'}), 400

    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': '파일이 선택되지 않았습니다'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': '허용되지 않은 파일 형식입니다'}), 400

    avatar_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'avatars')
    os.makedirs(avatar_dir, exist_ok=True)

    original = secure_filename(file.filename)
    ext = original.rsplit('.', 1)[1].lower() if '.' in original else 'png'
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"user_{current_user.id}_{ts}.{ext}"
    filepath = os.path.join(avatar_dir, filename)
    file.save(filepath)

    # 이전 파일 정리
    old = current_user.avatar_filename
    current_user.avatar_filename = filename
    db.session.commit()

    if old and old != filename:
        try:
            old_path = os.path.join(avatar_dir, old)
            if os.path.exists(old_path):
                os.remove(old_path)
        except Exception:
            pass

    log_activity_safe(
        user_id=current_user.id,
        action='profile.avatar.update',
        entity_type='user',
        entity_id=current_user.id,
        description='프로필 이미지 변경',
    )

    return jsonify({'message': '프로필 이미지가 저장되었습니다'})


@bp.route('/profile/activity', methods=['GET'])
@login_required
def profile_activity():
    """내 활동 내역 조회"""
    limit = request.args.get('limit', default=50, type=int)
    offset = request.args.get('offset', default=0, type=int)
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    q = ActivityLog.query.filter_by(user_id=current_user.id).order_by(ActivityLog.created_at.desc())
    items = q.offset(offset).limit(limit).all()

    return jsonify({
        'items': [{
            'id': a.id,
            'action': a.action,
            'entity_type': a.entity_type,
            'entity_id': a.entity_id,
            'project_id': a.project_id,
            'description': a.description,
            'meta_json': a.meta_json,
            'created_at': a.created_at.isoformat() if a.created_at else None
        } for a in items]
    })


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

    log_activity_safe(
        user_id=current_user.id,
        action='project.create',
        entity_type='project',
        entity_id=project.id,
        project_id=project.id,
        description=f'프로젝트 생성: {project.name}',
    )
    
    return jsonify({
        'id': project.id,
        'name': project.name,
        'description': project.description
    }), 201


@bp.route('/projects/<int:project_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def get_project(project_id):
    """프로젝트 상세 / 수정 / 삭제"""
    project = Project.query.get_or_404(project_id)
    
    if request.method == 'GET':
        return jsonify({
            'id': project.id,
            'name': project.name,
            'description': project.description,
            'created_at': project.created_at.isoformat(),
            'updated_at': project.updated_at.isoformat()
        })
    
    elif request.method == 'PUT':
        # 프로젝트 수정
        if current_user.role not in ['admin', 'author']:
            return jsonify({'error': '권한이 없습니다'}), 403
        
        data = request.get_json()
        project.name = data.get('name', project.name)
        project.description = data.get('description', project.description)
        db.session.commit()
        
        return jsonify({
            'id': project.id,
            'name': project.name,
            'description': project.description
        })
    
    elif request.method == 'DELETE':
        # 프로젝트 삭제 (Super Admin만 가능)
        if current_user.email != 'admin@pubg.com':
            return jsonify({'error': 'Super Admin 계정만 프로젝트를 삭제할 수 있습니다.'}), 403
        
        db.session.delete(project)
        db.session.commit()
        
        return jsonify({'message': '프로젝트가 삭제되었습니다'})


@bp.route('/projects/<int:project_id>/copy', methods=['POST'])
@login_required
def copy_project(project_id):
    """프로젝트 복제"""
    if current_user.role not in ['admin', 'author']:
        return jsonify({'error': '권한이 없습니다'}), 403
    
    original_project = Project.query.get_or_404(project_id)
    
    # 새 프로젝트 생성
    new_project = Project(
        name=f"{original_project.name} (복사본)",
        description=original_project.description
    )
    db.session.add(new_project)
    db.session.flush()
    
    # 섹션 복제 (재귀적으로)
    def copy_sections(parent_section, new_parent_id=None):
        sections = Section.query.filter_by(
            project_id=original_project.id,
            parent_id=parent_section.id if parent_section else None
        ).all()
        
        for section in sections:
            new_section = Section(
                project_id=new_project.id,
                parent_id=new_parent_id,
                name=section.name,
                order_index=section.order_index
            )
            db.session.add(new_section)
            db.session.flush()
            
            # 하위 섹션 복제
            copy_sections(section, new_section.id)
            
            # 케이스 복제
            cases = Case.query.filter_by(section_id=section.id).all()
            for case in cases:
                new_case = Case(
                    project_id=new_project.id,
                    section_id=new_section.id,
                    title=case.title,
                    steps=case.steps,
                    expected_result=case.expected_result,
                    priority=case.priority,
                    order_index=case.order_index
                )
                db.session.add(new_case)
    
    copy_sections(None)
    db.session.commit()
    
    return jsonify({
        'id': new_project.id,
        'name': new_project.name,
        'description': new_project.description
    }), 201


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
    
    # depth 체크 (최대 4단계, depth 0~3까지만 허용)
    parent_id = data.get('parent_id')
    if parent_id:
        def get_section_depth(section_id, depth=0):
            """섹션의 depth 계산"""
            if depth >= 4:  # 이미 4단계면 더 이상 허용 안 함
                return 4
            section = Section.query.get(section_id)
            if not section or not section.parent_id:
                return depth
            return get_section_depth(section.parent_id, depth + 1)
        
        parent_depth = get_section_depth(parent_id)
        if parent_depth >= 3:  # 부모가 depth 3이면 자식은 depth 4가 되어 최대치
            return jsonify({'error': '섹션은 최대 4단계까지만 생성할 수 있습니다.'}), 400
    
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
    # autoflush를 비활성화하여 외래키 제약 조건 문제 방지
    with db.session.no_autoflush:
        # 하위 섹션들을 재귀적으로 수집
        def collect_sections(sec, sections_list):
            sections_list.append(sec)
            children = Section.query.filter_by(parent_id=sec.id).all()
            for child in children:
                collect_sections(child, sections_list)
        
        sections_to_delete = []
        collect_sections(section, sections_to_delete)
        
        # 모든 섹션의 케이스들을 먼저 삭제 (archived가 아닌 완전 삭제)
        for sec in sections_to_delete:
            # 해당 섹션의 모든 케이스를 삭제
            Case.query.filter_by(section_id=sec.id).delete()
        
        # 섹션들을 역순으로 삭제 (자식부터 부모 순서)
        for sec in reversed(sections_to_delete):
            db.session.delete(sec)
    
    db.session.commit()
    return '', 204


# ============ Case API ============

@bp.route('/projects/<int:project_id>/cases', methods=['GET', 'POST'])
@login_required
def cases(project_id):
    """케이스 목록 조회 / 생성"""
    project = Project.query.get_or_404(project_id)
    
    if request.method == 'GET':
        query = Case.query.options(
            selectinload(Case.tags),   # N+1 태그 쿼리 방지
            joinedload(Case.section),  # section_name 접근 최적화
            joinedload(Case.owner)     # owner_name 접근 최적화
        ).filter_by(project_id=project_id)
        
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
    
    # order_index 처리
    order_index = data.get('order_index')
    if order_index is not None:
        # 같은 섹션의 order_index가 같거나 큰 케이스들을 1씩 증가
        Case.query.filter(
            Case.section_id == data['section_id'],
            Case.order_index >= order_index
        ).update({Case.order_index: Case.order_index + 1})
        db.session.flush()
    
    case = Case(
        project_id=project_id,
        section_id=data['section_id'],
        title=data['title'],
        steps=data.get('steps', ''),
        expected_result=data.get('expected_result', ''),
        priority=data.get('priority', 'Medium'),
        owner_id=data.get('owner_id'),
        order_index=order_index if order_index is not None else 0,
        created_by=current_user.id,
        updated_by=current_user.id
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

    log_activity_safe(
        user_id=current_user.id,
        action='case.create',
        entity_type='case',
        entity_id=case.id,
        project_id=project_id,
        description=f'테스트케이스 생성: {case.title}',
        meta={'section_id': case.section_id, 'priority': case.priority},
    )
    
    # 원본 언어로만 캐시 저장 (번역은 언어 변경 시에만 수행)
    try:
        source_lang = detect_language(case.title)
        current_app.logger.info(f'케이스 {case.id} 생성 - 언어 감지: {source_lang}')
        
        # 원본 언어로 캐시 저장
        original_translation = CaseTranslation(
            case_id=case.id,
            source_lang=source_lang,
            target_lang=source_lang,  # 원본 언어로 저장
            title=case.title,
            steps=case.steps,
            expected_result=case.expected_result
        )
        db.session.add(original_translation)
        db.session.commit()
        current_app.logger.info(f'케이스 {case.id} 원본 캐시 저장: {source_lang}')
    except Exception as e:
        current_app.logger.error(f'케이스 {case.id} 원본 캐시 저장 실패: {e}')
        db.session.rollback()
    
    response_data = {
        'id': case.id,
        'title': case.title,
        'section_id': case.section_id,
        'priority': case.priority,
        'order_index': case.order_index,
        'steps': case.steps,
        'expected_result': case.expected_result,
        'status': case.status,
        'owner_id': case.owner_id,
        'created_at': case.created_at.isoformat(),
        'updated_at': case.updated_at.isoformat()
    }
    
    return jsonify(response_data), 201


@bp.route('/cases/<int:case_id>', methods=['GET', 'PATCH'])
@login_required
def case(case_id):
    """케이스 상세 조회 / 수정 (인라인 편집)"""
    case = Case.query.get_or_404(case_id)
    
    if request.method == 'GET':
        jira_links = [l.url for l in CaseJiraLink.query.filter_by(case_id=case.id).order_by(CaseJiraLink.created_at.desc()).all()]
        media_items = CaseMedia.query.filter_by(case_id=case.id).order_by(CaseMedia.created_at.desc()).all()
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
            'jira_links': jira_links,
            'media': [{
                'id': m.id,
                'original_name': m.original_name,
                'url': f'/api/case-media/{m.id}'
            } for m in media_items],
            'version': case.version or 1,  # Phase 1: 버전 정보 추가
            'created_at': case.created_at.isoformat(),
            'updated_at': case.updated_at.isoformat()
        })
    
    # PATCH: Auto-save 인라인 편집
    if current_user.role not in ['admin', 'author']:
        return jsonify({'error': '권한이 없습니다'}), 403
    
    data = request.get_json()
    
    # Phase 1: 케이스 내용 변경 시 버전 증가
    content_changed = any(key in data for key in ['title', 'steps', 'expected_result'])
    if content_changed:
        case.version = (case.version or 1) + 1
        case.updated_by = current_user.id
    
    if 'title' in data:
        case.title = data['title']
    if 'order_index' in data:
        # 같은 섹션 내의 케이스 순서 재정렬
        new_order = data['order_index']
        old_order = case.order_index
        section_id = case.section_id
        
        if new_order != old_order:
            # 같은 섹션의 다른 케이스들 조회
            other_cases = Case.query.filter(
                Case.section_id == section_id,
                Case.id != case.id,
                Case.status == 'active'
            ).order_by(Case.order_index.asc()).all()
            
            # 순서 재정렬
            if new_order < old_order:
                # 위로 이동: new_order와 old_order 사이의 케이스들을 아래로
                for c in other_cases:
                    if new_order <= c.order_index < old_order:
                        c.order_index += 1
            else:
                # 아래로 이동: old_order와 new_order 사이의 케이스들을 위로
                for c in other_cases:
                    if old_order < c.order_index <= new_order:
                        c.order_index -= 1
            
            case.order_index = new_order
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

    log_activity_safe(
        user_id=current_user.id,
        action='case.update',
        entity_type='case',
        entity_id=case.id,
        project_id=case.project_id,
        description=f'테스트케이스 수정: {case.title}',
        meta={'updated_fields': sorted(list(data.keys()))},
    )
    
    # 원본 캐시 업데이트 (title, steps, expected_result 중 하나라도 변경되었으면)
    translation_error = None
    if any(key in data for key in ['title', 'steps', 'expected_result']):
        try:
            source_lang = detect_language(case.title)
            current_app.logger.info(f'케이스 {case.id} 수정 - 언어 감지: {source_lang}')
            
            # 기존 번역 모두 삭제
            CaseTranslation.query.filter_by(case_id=case.id).delete()
            
            # 원본 언어로 캐시 저장 (번역은 언어 변경 시에만 수행)
            original_translation = CaseTranslation(
                case_id=case.id,
                source_lang=source_lang,
                target_lang=source_lang,  # 원본 언어로 저장
                title=case.title,
                steps=case.steps,
                expected_result=case.expected_result
            )
            db.session.add(original_translation)
            db.session.commit()
            current_app.logger.info(f'케이스 {case.id} 원본 캐시 업데이트: {source_lang}')
        except TranslationError as e:
            translation_error = str(e)
            current_app.logger.error(f'케이스 {case.id} 번역 업데이트 실패: {e}')
            db.session.rollback()
        except Exception as e:
            translation_error = f'번역 중 예기치 않은 오류가 발생했습니다: {str(e)}'
            current_app.logger.error(f'케이스 {case.id} 번역 업데이트 실패: {e}')
            db.session.rollback()
    
    response_data = {'status': 'saved', 'updated_at': case.updated_at.isoformat()}
    if translation_error:
        response_data['translation_warning'] = translation_error
    
    return jsonify(response_data)


@bp.route('/cases/<int:case_id>/jira-links', methods=['GET', 'POST'])
@login_required
def case_jira_links(case_id):
    """케이스 Jira 링크 목록/추가"""
    case = Case.query.get_or_404(case_id)

    if request.method == 'GET':
        links = CaseJiraLink.query.filter_by(case_id=case_id).order_by(CaseJiraLink.created_at.desc()).all()
        return jsonify([{'id': l.id, 'url': l.url, 'created_at': l.created_at.isoformat() if l.created_at else None} for l in links])

    if current_user.role not in ['admin', 'author']:
        return jsonify({'error': '권한이 없습니다'}), 403

    data = request.get_json() or {}
    url = (data.get('url') or '').strip()
    if not url:
        return jsonify({'error': 'URL이 필요합니다'}), 400

    link = CaseJiraLink(case_id=case_id, url=url, created_by=current_user.id)
    db.session.add(link)
    db.session.commit()

    log_activity_safe(
        user_id=current_user.id,
        action='case.jira_link.add',
        entity_type='case',
        entity_id=case_id,
        project_id=case.project_id,
        description=f'케이스 Jira 링크 추가: {url}',
    )

    return jsonify({'id': link.id, 'url': link.url}), 201


@bp.route('/cases/jira-links/<int:link_id>', methods=['DELETE'])
@login_required
def delete_case_jira_link(link_id):
    link = CaseJiraLink.query.get_or_404(link_id)
    case = Case.query.get(link.case_id)

    if current_user.role not in ['admin', 'author']:
        return jsonify({'error': '권한이 없습니다'}), 403

    db.session.delete(link)
    db.session.commit()

    log_activity_safe(
        user_id=current_user.id,
        action='case.jira_link.delete',
        entity_type='case',
        entity_id=link.case_id,
        project_id=case.project_id if case else None,
        description='케이스 Jira 링크 삭제',
    )
    return jsonify({'success': True})


@bp.route('/cases/<int:case_id>/media', methods=['GET', 'POST'])
@login_required
def case_media(case_id):
    """케이스 미디어 목록/업로드"""
    case = Case.query.get_or_404(case_id)

    if request.method == 'GET':
        items = CaseMedia.query.filter_by(case_id=case_id).order_by(CaseMedia.created_at.desc()).all()
        return jsonify([{
            'id': m.id,
            'original_name': m.original_name,
            'url': f'/api/case-media/{m.id}',
            'created_at': m.created_at.isoformat() if m.created_at else None
        } for m in items])

    if current_user.role not in ['admin', 'author']:
        return jsonify({'error': '권한이 없습니다'}), 403

    if 'file' not in request.files:
        return jsonify({'error': '파일이 없습니다'}), 400
    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': '파일이 선택되지 않았습니다'}), 400
    if not allowed_file(file.filename):
        return jsonify({'error': '허용되지 않은 파일 형식입니다'}), 400

    media_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'case_media')
    os.makedirs(media_dir, exist_ok=True)

    original = file.filename
    filename = secure_filename(original)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    stored = f"{ts}_{filename}"
    filepath = os.path.join(media_dir, stored)
    file.save(filepath)

    m = CaseMedia(
        case_id=case_id,
        file_path=filepath,
        original_name=original,
        mime_type=file.mimetype,
        created_by=current_user.id
    )
    db.session.add(m)
    db.session.commit()

    log_activity_safe(
        user_id=current_user.id,
        action='case.media.upload',
        entity_type='case',
        entity_id=case_id,
        project_id=case.project_id,
        description=f'케이스 미디어 업로드: {original}',
    )

    return jsonify({'id': m.id, 'original_name': m.original_name, 'url': f'/api/case-media/{m.id}'}), 201


@bp.route('/case-media/<int:media_id>', methods=['GET', 'DELETE'])
@login_required
def get_case_media(media_id):
    """케이스 미디어 보기/삭제 (기본 inline, 다운로드: ?download=1)"""
    media = CaseMedia.query.get_or_404(media_id)
    case = Case.query.get(media.case_id)

    if request.method == 'DELETE':
        if current_user.role not in ['admin', 'author']:
            return jsonify({'error': '권한이 없습니다'}), 403

        file_path = media.file_path
        db.session.delete(media)
        db.session.commit()
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass

        log_activity_safe(
            user_id=current_user.id,
            action='case.media.delete',
            entity_type='case',
            entity_id=media.case_id,
            project_id=case.project_id if case else None,
            description='케이스 미디어 삭제',
        )

        return jsonify({'success': True})

    download = request.args.get('download', '0') in ['1', 'true', 'True', 'yes', 'y']
    guessed_type, _ = mimetypes.guess_type(media.original_name or media.file_path)
    return send_file(
        media.file_path,
        as_attachment=download,
        download_name=media.original_name,
        mimetype=guessed_type or media.mime_type
    )


@bp.route('/cases/<int:case_id>/translation', methods=['GET'])
@login_required
def get_case_translation(case_id):
    """케이스 번역 조회"""
    case = Case.query.get_or_404(case_id)
    target_lang = request.args.get('lang', 'en')
    
    current_app.logger.info(f'번역 요청: 케이스 {case_id}, 대상 언어: {target_lang}')
    
    # 기존 번역 조회
    translation = CaseTranslation.query.filter_by(
        case_id=case_id,
        target_lang=target_lang
    ).first()
    
    if translation:
        current_app.logger.info(f'케이스 {case_id} 캐시된 번역 반환')
        return jsonify({
            'case_id': case.id,
            'source_lang': translation.source_lang,
            'target_lang': translation.target_lang,
            'title': translation.title,
            'steps': translation.steps,
            'expected_result': translation.expected_result,
            'cached': True,
            'updated_at': translation.updated_at.isoformat()
        })
    
    # 번역이 없으면 즉시 생성
    try:
        source_lang = detect_language(case.title)
        current_app.logger.info(f'케이스 {case_id} 언어 감지: {source_lang} -> {target_lang}')
        
        # 같은 언어면 원본 반환
        if source_lang == target_lang:
            current_app.logger.info(f'케이스 {case_id} 동일 언어, 원본 반환')
            return jsonify({
                'case_id': case.id,
                'source_lang': source_lang,
                'target_lang': target_lang,
                'title': case.title,
                'steps': case.steps,
                'expected_result': case.expected_result,
                'cached': False,
                'same_language': True
            })
        
        # 번역 수행
        current_app.logger.info(f'케이스 {case_id} 번역 시작...')
        translated = translate_case({
            'title': case.title,
            'steps': case.steps,
            'expected_result': case.expected_result
        }, source_lang, target_lang)
        
        current_app.logger.info(f'케이스 {case_id} 번역 완료, 저장 중...')
        
        # 번역 저장
        translation = CaseTranslation(
            case_id=case.id,
            source_lang=source_lang,
            target_lang=target_lang,
            title=translated.get('title'),
            steps=translated.get('steps'),
            expected_result=translated.get('expected_result')
        )
        db.session.add(translation)
        db.session.commit()
        
        current_app.logger.info(f'케이스 {case_id} 번역 저장 완료')
        
        return jsonify({
            'case_id': case.id,
            'source_lang': source_lang,
            'target_lang': target_lang,
            'title': translated.get('title'),
            'steps': translated.get('steps'),
            'expected_result': translated.get('expected_result'),
            'cached': False,
            'updated_at': translation.updated_at.isoformat()
        })
    except TranslationError as e:
        current_app.logger.error(f'케이스 {case_id} 번역 실패 (TranslationError): {e}')
        return jsonify({'error': str(e), 'case_id': case_id}), 500
    except Exception as e:
        current_app.logger.error(f'케이스 {case_id} 번역 실패 (Exception): {e}', exc_info=True)
        return jsonify({'error': f'번역 중 예기치 않은 오류가 발생했습니다: {str(e)}', 'case_id': case_id}), 500


@bp.route('/cases/<int:case_id>/archive', methods=['POST'])
@login_required
def archive_case(case_id):
    """케이스 아카이브"""
    if current_user.role not in ['admin', 'author']:
        return jsonify({'error': '권한이 없습니다'}), 403
    
    case = Case.query.get_or_404(case_id)
    case.status = 'archived'
    db.session.commit()

    log_activity_safe(
        user_id=current_user.id,
        action='case.archive',
        entity_type='case',
        entity_id=case.id,
        project_id=case.project_id,
        description=f'테스트케이스 삭제(아카이브): {case.title}',
    )
    
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

    log_activity_safe(
        user_id=current_user.id,
        action='case.unarchive',
        entity_type='case',
        entity_id=case.id,
        project_id=case.project_id,
        description=f'테스트케이스 복원(언아카이브): {case.title}',
    )
    
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
    language = (data.get('language') or 'original').strip()
    if language not in ['original', 'ko', 'en']:
        language = 'original'
    
    run = Run(
        project_id=project_id,
        name=data['name'],
        description=data.get('description', ''),
        build_label=data.get('build_label', ''),  # Phase 1: 빌드 라벨
        created_by=current_user.id,
        run_type=data.get('run_type', 'custom'),
        language=language
    )
    db.session.add(run)
    db.session.flush()
    
    # RunCase 스냅샷 생성 (언어 선택 지원)
    case_ids = data.get('case_ids', [])

    # 케이스 Jira/미디어 스냅샷(문자열)
    jira_map = {}
    media_map = {}
    if case_ids:
        for l in CaseJiraLink.query.filter(CaseJiraLink.case_id.in_(case_ids)).all():
            jira_map.setdefault(l.case_id, []).append(l.url)
        for m in CaseMedia.query.filter(CaseMedia.case_id.in_(case_ids)).all():
            media_map.setdefault(m.case_id, []).append(m.original_name)

    translations = {}
    if language in ['ko', 'en']:
        translations, _, _ = _ensure_case_translations(case_ids, language, force=False)

    for idx, case_id in enumerate(case_ids):
        case = Case.query.get(case_id)
        if case:
            t = translations.get(case_id) if language in ['ko', 'en'] else None
            title_snapshot = (t or {}).get('title') or case.title
            steps_snapshot = (t or {}).get('steps') or case.steps
            expected_snapshot = (t or {}).get('expected_result') or case.expected_result

            run_case = RunCase(
                run_id=run.id,
                case_id=case_id,
                order_index=idx,
                case_version_snapshot=case.version,
                title_snapshot=title_snapshot,
                steps_snapshot=steps_snapshot,
                expected_result_snapshot=expected_snapshot,
                priority_snapshot=case.priority  # Phase 1 수정: 우선순위 스냅샷
                ,
                jira_links_snapshot=' | '.join(jira_map.get(case_id, [])),
                media_names_snapshot=' | '.join(media_map.get(case_id, []))
            )
            db.session.add(run_case)
    
    db.session.commit()

    log_activity_safe(
        user_id=current_user.id,
        action='run.create',
        entity_type='run',
        entity_id=run.id,
        project_id=project_id,
        description=f'런 생성: {run.name}',
        meta={'case_count': len(case_ids), 'run_type': run.run_type, 'build_label': run.build_label or ''},
    )
    
    return jsonify({
        'id': run.id,
        'name': run.name,
        'build_label': run.build_label,
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
        
        run_name = run.name
        project_id = run.project_id
        db.session.delete(run)
        db.session.commit()

        log_activity_safe(
            user_id=current_user.id,
            action='run.delete',
            entity_type='run',
            entity_id=run_id,
            project_id=project_id,
            description=f'런 삭제: {run_name}',
        )
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
    """런 종료 - Phase 1 개선: 런 완료 시점의 케이스 스냅샷 저장"""
    run = Run.query.get_or_404(run_id)
    
    # 런 완료 시점의 케이스 스냅샷 저장
    language = getattr(run, 'language', None) or 'original'
    case_ids = [rc.case_id for rc in run.run_cases]
    translations = {}
    if language in ['ko', 'en'] and case_ids:
        translations, _, _ = _ensure_case_translations(case_ids, language, force=False)

    jira_map = {}
    media_map = {}
    if case_ids:
        for l in CaseJiraLink.query.filter(CaseJiraLink.case_id.in_(case_ids)).all():
            jira_map.setdefault(l.case_id, []).append(l.url)
        for m in CaseMedia.query.filter(CaseMedia.case_id.in_(case_ids)).all():
            media_map.setdefault(m.case_id, []).append(m.original_name)

    for rc in run.run_cases:
        case = rc.case
        rc.case_version_snapshot = case.version or 1
        if language in ['ko', 'en']:
            t = translations.get(rc.case_id) or {}
            rc.title_snapshot = t.get('title') or case.title
            rc.steps_snapshot = t.get('steps') or case.steps
            rc.expected_result_snapshot = t.get('expected_result') or case.expected_result
        else:
            rc.title_snapshot = case.title
            rc.steps_snapshot = case.steps
            rc.expected_result_snapshot = case.expected_result
        rc.priority_snapshot = case.priority
        rc.jira_links_snapshot = ' | '.join(jira_map.get(rc.case_id, []))
        rc.media_names_snapshot = ' | '.join(media_map.get(rc.case_id, []))
    
    run.is_closed = True
    db.session.commit()

    log_activity_safe(
        user_id=current_user.id,
        action='run.close',
        entity_type='run',
        entity_id=run.id,
        project_id=run.project_id,
        description=f'런 완료(닫기): {run.name}',
    )
    
    return jsonify({'is_closed': True})


@bp.route('/runs/<int:run_id>/reopen', methods=['POST'])
@login_required
def reopen_run(run_id):
    """런 재오픈"""
    run = Run.query.get_or_404(run_id)
    run.is_closed = False
    db.session.commit()

    log_activity_safe(
        user_id=current_user.id,
        action='run.reopen',
        entity_type='run',
        entity_id=run.id,
        project_id=run.project_id,
        description=f'런 재오픈: {run.name}',
    )
    
    return jsonify({'is_closed': False})


@bp.route('/runs/<int:run_id>/generate-summary', methods=['POST'])
@login_required
def generate_run_summary(run_id):
    """AI 요약 생성"""
    run = Run.query.get_or_404(run_id)
    
    # 완료된 런만 요약 생성 가능
    if not run.is_closed:
        return jsonify({'error': '완료된 런만 요약을 생성할 수 있습니다.'}), 400
    
    data = request.get_json()
    prompt_id = data.get('prompt_id')
    current_page_data = data.get('current_page_data')  # 프론트엔드에서 전달한 현재 페이지 데이터
    
    if not prompt_id:
        return jsonify({'error': '프롬프트 ID가 필요합니다.'}), 400
    
    from app.models import SummaryPrompt
    prompt = SummaryPrompt.query.get(prompt_id)
    if not prompt:
        return jsonify({'error': '프롬프트를 찾을 수 없습니다.'}), 404
    
    # 현재 페이지의 실제 데이터 사용 (프론트엔드에서 전달한 데이터 우선)
    if current_page_data:
        # 프론트엔드에서 전달한 현재 페이지의 실제 데이터 사용
        current_app.logger.info(f'[AI 요약] 프론트엔드 데이터 사용: Run ID {run_id}')
        current_app.logger.info(f'[AI 요약] Run Name: {current_page_data.get("run_name")}')
        current_app.logger.info(f'[AI 요약] Build Label: {current_page_data.get("build_label")}')
        current_app.logger.info(f'[AI 요약] Test Results Count: {len(current_page_data.get("test_results", []))}')
        
        test_results = []
        stats = current_page_data.get('stats', {})
        
        for item in current_page_data.get('test_results', []):
            result_line = f"- {item['case_title']}: {item['status']}"
            if item.get('bug_links'):
                result_line += f" (버그: {item['bug_links']})"
            if item.get('comment'):
                result_line += f" - {item['comment']}"
            test_results.append(result_line)
        
        build_label = current_page_data.get('build_label', run.build_label or 'N/A')
        run_name = current_page_data.get('run_name', run.name)
        
        current_app.logger.info(f'[AI 요약] 수집된 테스트 결과:\n{chr(10).join(test_results[:5])}...')
    else:
        # 기존 방식: 서버에서 데이터 수집 (백업)
        current_app.logger.warning(f'[AI 요약] 프론트엔드 데이터 없음, 서버 DB에서 수집: Run ID {run_id}')
        
        stats = run.get_stats()
        test_results = []
        failed_cases = []
        bug_links = []
        comments = []
        
        for rc in run.run_cases.order_by(RunCase.order_index):
            result = rc.get_latest_result()
            if result and result.status != 'comment':
                # 완료된 런의 경우 스냅샷 데이터 사용, 진행 중인 경우 현재 데이터 사용
                if run.is_closed:
                    case_title = rc.title_snapshot or rc.case.title
                else:
                    case_title = rc.case.title
                
                result_line = f"- {case_title}: {result.status.upper()}"
                
                # Fail 케이스 상세 정보 수집
                if result.status == 'fail':
                    if result.bug_links:
                        bug_link = result.bug_links.strip()
                        result_line += f" (버그: {bug_link})"
                        bug_links.append(bug_link)
                    if result.comment:
                        result_line += f" - {result.comment}"
                        comments.append(result.comment)
                    failed_cases.append(result_line)
                
                test_results.append(result_line)
        
        build_label = run.build_label or 'N/A'
        run_name = run.name
    
    # 프롬프트 템플릿에 데이터 채우기
    # 중요: 프롬프트가 실제 데이터를 사용하도록 명확히 지시
    test_results_text = '\n'.join(test_results) if test_results else '테스트 결과 없음'
    notes_text = f"총 {stats.get('total', 0)}개 케이스 중 {stats.get('executed', 0)}개 실행, Pass: {stats.get('pass', 0)}, Fail: {stats.get('fail', 0)}, Blocked: {stats.get('blocked', 0)}, Retest: {stats.get('retest', 0)}"
    
    current_app.logger.info(f'[AI 요약] 프롬프트 데이터 - Build: {build_label}, Notes: {notes_text}')
    
    user_prompt = prompt.user_prompt_template.format(
        build_label=build_label,
        backend_info='N/A',  # TODO: 백엔드 정보 추가 필요
        test_results=test_results_text,
        notes=notes_text
    )
    
    # OpenAI API 호출
    try:
        from app.utils.translator import get_openai_client
        
        client = get_openai_client()
        if not client:
            return jsonify({'error': '활성화된 API 키가 없습니다.'}), 400
        
        current_app.logger.info(f'[AI 요약] OpenAI API 호출 시작 - Model: {prompt.model}')
        current_app.logger.info(f'[AI 요약] System Prompt: {prompt.system_prompt[:100]}...')
        current_app.logger.info(f'[AI 요약] User Prompt: {user_prompt[:500]}...')
        
        response = client.chat.completions.create(
            model=prompt.model,
            messages=[
                {'role': 'system', 'content': prompt.system_prompt},
                {'role': 'user', 'content': user_prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        summary = response.choices[0].message.content.strip()
        
        # 요약 저장
        run.summary = summary
        run.summary_prompt_id = prompt_id
        db.session.commit()
        
        return jsonify({
            'summary': summary,
            'prompt_id': prompt_id
        })
        
    except Exception as e:
        current_app.logger.error(f'AI 요약 생성 오류: {str(e)}')
        return jsonify({'error': f'요약 생성 실패: {str(e)}'}), 500


# ============ Run Execution API ============

@bp.route('/runs/<int:run_id>/cases', methods=['GET'])
@login_required
def run_cases(run_id):
    """런의 케이스 목록 (최신 결과 포함) - Phase 1: 스냅샷 데이터 사용"""
    run = Run.query.get_or_404(run_id)
    run_cases = run.run_cases.order_by(RunCase.order_index).all()
    
    # 케이스 Jira/미디어 사전 로드
    case_ids = [rc.case_id for rc in run_cases]
    jira_map = {}
    media_map = {}
    if case_ids:
        for l in CaseJiraLink.query.filter(CaseJiraLink.case_id.in_(case_ids)).all():
            jira_map.setdefault(l.case_id, []).append(l.url)
        for m in CaseMedia.query.filter(CaseMedia.case_id.in_(case_ids)).all():
            media_map.setdefault(m.case_id, []).append({
                'id': m.id,
                'original_name': m.original_name,
                'url': f'/api/case-media/{m.id}'
            })

    result_list = []
    for rc in run_cases:
        latest_result = rc.get_latest_result()
        
        # 런이 완료된 경우 또는 런 언어가 original이 아닌 경우: 스냅샷 데이터 사용
        use_snapshot = bool(run.is_closed) or bool(getattr(run, 'language', None) and run.language != 'original')
        if use_snapshot:
            # 완료된 런: 스냅샷 데이터 사용
            case_title = rc.title_snapshot or rc.case.title
            case_steps = rc.steps_snapshot or rc.case.steps
            case_expected = rc.expected_result_snapshot or rc.case.expected_result
            case_priority = rc.priority_snapshot or rc.case.priority
            case_version = rc.case_version_snapshot or rc.case.version or 1
        else:
            # 진행 중인 런: 현재 데이터 사용 (편의성을 위해)
            case_title = rc.case.title
            case_steps = rc.case.steps
            case_expected = rc.case.expected_result
            case_priority = rc.case.priority
            case_version = rc.case.version or 1
        
        result_list.append({
            'run_case_id': rc.id,
            'case_id': rc.case_id,
            'case_title': case_title,
            'case_steps': case_steps,
            'case_expected': case_expected,
            'case_priority': case_priority,
            'case_version': case_version,
            'case_jira_links': (rc.jira_links_snapshot or '').split(' | ') if (run.is_closed and rc.jira_links_snapshot) else jira_map.get(rc.case_id, []),
            'case_media': media_map.get(rc.case_id, []),
            'case_jira_links_snapshot': rc.jira_links_snapshot or '',
            'case_media_names_snapshot': rc.media_names_snapshot or '',
            'case_created_at': rc.case.created_at.isoformat() if rc.case.created_at else None,
            'case_created_by': rc.case.creator.name if rc.case.creator else None,
            'case_updated_at': rc.case.updated_at.isoformat() if rc.case.updated_at else None,
            'case_updated_by': rc.case.updater.name if rc.case.updater else None,
            'result': {
                'id': latest_result.id,
                'status': latest_result.status,
                'comment': latest_result.comment,
                'bug_links': latest_result.bug_links,
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
            # 기존 결과 업데이트 (Phase 1: bug_links 포함)
            existing_result.status = data['status']
            existing_result.comment = data.get('comment', '')
            existing_result.bug_links = data.get('bug_links', '')
            existing_result.created_at = datetime.utcnow()
            db.session.commit()

            log_activity_safe(
                user_id=current_user.id,
                action='run.result.update',
                entity_type='result',
                entity_id=existing_result.id,
                project_id=run.project_id,
                description=f'런 결과 업데이트: {run.name} / case_id={data.get("case_id")} -> {existing_result.status}',
                meta={'run_id': run_id, 'case_id': data.get('case_id'), 'status': existing_result.status},
            )
            
            return jsonify({
                'id': existing_result.id,
                'status': existing_result.status,
                'bug_links': existing_result.bug_links,
                'created_at': existing_result.created_at.isoformat()
            }), 200
    
    # 새 결과 생성 (다른 실행자이거나 시간이 많이 지난 경우) (Phase 1: bug_links 포함)
    result = Result(
        run_id=run_id,
        case_id=data['case_id'],
        executor_id=current_user.id,
        status=data['status'],
        comment=data.get('comment', ''),
        bug_links=data.get('bug_links', '')
    )
    db.session.add(result)
    db.session.commit()

    log_activity_safe(
        user_id=current_user.id,
        action='run.result.create',
        entity_type='result',
        entity_id=result.id,
        project_id=run.project_id,
        description=f'런 결과 기록: {run.name} / case_id={data.get("case_id")} -> {result.status}',
        meta={'run_id': run_id, 'case_id': data.get('case_id'), 'status': result.status},
    )
    
    return jsonify({
        'id': result.id,
        'status': result.status,
        'bug_links': result.bug_links,
        'created_at': result.created_at.isoformat()
    }), 201


@bp.route('/results/<int:result_id>', methods=['PATCH'])
@login_required
def update_result(result_id):
    """결과 업데이트 (Phase 1 개선: 버그 링크 업데이트)"""
    result = Result.query.get_or_404(result_id)
    data = request.get_json()
    
    # 버그 링크 업데이트
    if 'bug_links' in data:
        result.bug_links = data['bug_links']
    
    # 코멘트 업데이트
    if 'comment' in data:
        result.comment = data['comment']
    
    db.session.commit()

    log_activity_safe(
        user_id=current_user.id,
        action='run.result.edit',
        entity_type='result',
        entity_id=result.id,
        project_id=result.run.project_id if result.run else None,
        description=f'결과 수정: result_id={result.id}',
        meta={'updated_fields': sorted(list(data.keys()))},
    )
    
    return jsonify({
        'id': result.id,
        'bug_links': result.bug_links,
        'comment': result.comment
    })


@bp.route('/runs/<int:run_id>/comments', methods=['POST'])
@login_required
def create_comment(run_id):
    """코멘트 저장 (결과값과 무관하게)"""
    run = Run.query.get_or_404(run_id)
    data = request.get_json()
    
    # 코멘트만 저장하는 Result 생성 (status='comment')
    result = Result(
        run_id=run_id,
        case_id=data['case_id'],
        executor_id=current_user.id,
        status='comment',  # 코멘트 전용 상태
        comment=data.get('comment', ''),
        bug_links=''
    )
    db.session.add(result)
    db.session.commit()

    log_activity_safe(
        user_id=current_user.id,
        action='run.comment.create',
        entity_type='result',
        entity_id=result.id,
        project_id=run.project_id,
        description=f'코멘트 작성: {run.name} / case_id={data.get("case_id")}',
        meta={'run_id': run_id, 'case_id': data.get('case_id')},
    )
    
    return jsonify({
        'id': result.id,
        'comment': result.comment,
        'executor': result.executor.name,
        'created_at': result.created_at.isoformat()
    }), 201


@bp.route('/runs/<int:run_id>/cases/<int:case_id>/comments', methods=['GET'])
@login_required
def get_case_comments(run_id, case_id):
    """케이스의 모든 코멘트 조회"""
    run = Run.query.get_or_404(run_id)
    comments = Result.query.filter_by(
        run_id=run_id,
        case_id=case_id,
        status='comment'
    ).order_by(Result.created_at.desc()).all()
    
    return jsonify([{
        'id': c.id,
        'comment': c.comment,
        'executor': c.executor.name,
        'created_at': c.created_at.isoformat()
    } for c in comments])


@bp.route('/runs/<int:run_id>/cases/<int:case_id>/bug-links', methods=['GET', 'PUT'])
@login_required
def run_case_bug_links(run_id, case_id):
    """버그 링크 조회/저장 (결과 입력 없이도 저장 가능)"""
    Run.query.get_or_404(run_id)

    if request.method == 'GET':
        # 실행 결과의 bug_links 또는 artifact bug_links 중 최신 non-empty를 반환
        latest = Result.query.filter(
            Result.run_id == run_id,
            Result.case_id == case_id,
            Result.bug_links.isnot(None),
            Result.bug_links != ''
        ).order_by(Result.created_at.desc()).first()
        return jsonify({'bug_links': latest.bug_links if latest else ''})

    data = request.get_json() or {}
    bug_links = (data.get('bug_links') or '').strip()

    artifact = _get_or_create_artifact_result(run_id, case_id)
    artifact.bug_links = bug_links
    artifact.created_at = datetime.utcnow()
    db.session.commit()

    log_activity_safe(
        user_id=current_user.id,
        action='run.bug_links.update',
        entity_type='result',
        entity_id=artifact.id,
        project_id=artifact.run.project_id if artifact.run else None,
        description=f'버그 링크 저장: run_id={run_id} case_id={case_id}',
    )

    return jsonify({'bug_links': artifact.bug_links, 'result_id': artifact.id})


@bp.route('/runs/<int:run_id>/cases/<int:case_id>/attachments', methods=['GET', 'POST'])
@login_required
def run_case_attachments(run_id, case_id):
    """첨부파일 목록/업로드 (결과 입력 없이도 업로드 가능)"""
    Run.query.get_or_404(run_id)

    if request.method == 'GET':
        # 해당 런/케이스의 모든 첨부(결과 status 무관)
        attachments = Attachment.query.join(Result, Attachment.result_id == Result.id).filter(
            Result.run_id == run_id,
            Result.case_id == case_id
        ).order_by(Attachment.created_at.desc()).all()

        return jsonify([{
            'id': a.id,
            'original_name': a.original_name,
            'created_at': a.created_at.isoformat() if a.created_at else None
        } for a in attachments])

    # POST: 업로드
    if 'file' not in request.files:
        return jsonify({'error': '파일이 없습니다'}), 400
    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': '파일이 선택되지 않았습니다'}), 400
    if not allowed_file(file.filename):
        return jsonify({'error': '허용되지 않은 파일 형식입니다'}), 400

    artifact = _get_or_create_artifact_result(run_id, case_id)

    filename = secure_filename(file.filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{timestamp}_{filename}"
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    attachment = Attachment(
        result_id=artifact.id,
        file_path=filepath,
        original_name=file.filename
    )
    db.session.add(attachment)
    db.session.commit()

    log_activity_safe(
        user_id=current_user.id,
        action='attachment.upload',
        entity_type='attachment',
        entity_id=attachment.id,
        project_id=artifact.run.project_id if artifact.run else None,
        description=f'첨부파일 업로드: {attachment.original_name}',
        meta={'run_id': run_id, 'case_id': case_id},
    )

    return jsonify({
        'id': attachment.id,
        'original_name': attachment.original_name,
        'created_at': attachment.created_at.isoformat()
    }), 201


@bp.route('/results/<int:result_id>', methods=['DELETE'])
@login_required
def delete_result(result_id):
    """결과/코멘트 삭제"""
    result = Result.query.get_or_404(result_id)
    
    # 본인이 작성한 것만 삭제 가능
    if result.executor_id != current_user.id:
        return jsonify({'error': '권한이 없습니다.'}), 403
    
    db.session.delete(result)
    db.session.commit()

    log_activity_safe(
        user_id=current_user.id,
        action='run.result.delete',
        entity_type='result',
        entity_id=result_id,
        project_id=result.run.project_id if result.run else None,
        description=f'결과/코멘트 삭제: result_id={result_id}',
    )
    
    return jsonify({'success': True}), 200


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
        'bug_links': r.bug_links,
        'executor': r.executor.name,
        'created_at': r.created_at.isoformat()
    } for r in results])


@bp.route('/sections/<int:section_id>/cases/export.csv', methods=['GET'])
@login_required
def export_section_cases_csv(section_id):
    """섹션의 케이스들을 CSV로 내보내기"""
    from flask import make_response
    import csv
    from io import StringIO
    from urllib.parse import quote
    
    section = Section.query.get_or_404(section_id)
    
    # 섹션의 모든 케이스 가져오기 (하위 섹션 포함)
    def get_all_cases_recursive(sec):
        cases = list(
            sec.cases
            .filter_by(status='active')
            .options(
                joinedload(Case.section),
                joinedload(Case.creator),
                selectinload(Case.tags)
            )
            .order_by(Case.order_index)
            .all()
        )
        for child in sec.children.order_by(Section.order_index).all():
            cases.extend(get_all_cases_recursive(child))
        return cases
    
    cases = get_all_cases_recursive(section)
    
    # CSV 데이터 생성
    output = StringIO()
    writer = csv.writer(output)
    
    # 번역 타이틀(ko/en) 사전 로드
    case_ids = [c.id for c in cases]
    translation_map = {}
    if case_ids:
        translations = CaseTranslation.query.filter(
            CaseTranslation.case_id.in_(case_ids),
            CaseTranslation.target_lang.in_(['ko', 'en'])
        ).all()
        for t in translations:
            translation_map[(t.case_id, t.target_lang)] = t.title

    # 케이스 Jira/미디어 사전 로드
    jira_map = {}
    media_map = {}
    if case_ids:
        for l in CaseJiraLink.query.filter(CaseJiraLink.case_id.in_(case_ids)).all():
            jira_map.setdefault(l.case_id, []).append(l.url)
        for m in CaseMedia.query.filter(CaseMedia.case_id.in_(case_ids)).all():
            media_map.setdefault(m.case_id, []).append(m.original_name)

    # 헤더 작성
    writer.writerow([
        'Section Path', 'Test Case ID', 'Test Case Title (KO)', 'Test Case Title (EN)', 'Version',
        'Priority', 'Steps', 'Expected Result', 'Tags', 'Jira Links', 'Media', 'Created By', 'Created At'
    ])
    
    # 데이터 작성
    for case in cases:
        section_path = case.section.get_full_path() if case.section else 'N/A'
        tags = ', '.join([tag.name for tag in case.tags])

        # KO/EN 타이틀 가져오기 (없으면 원본 언어에 따라 fallback)
        title_ko = translation_map.get((case.id, 'ko'))
        title_en = translation_map.get((case.id, 'en'))
        try:
            src = detect_language(case.title)
        except Exception:
            src = None
        if not title_ko and src == 'ko':
            title_ko = case.title
        if not title_en and src == 'en':
            title_en = case.title
        
        writer.writerow([
            section_path,
            case.id,
            title_ko or '',
            title_en or '',
            case.version or 1,
            case.priority or 'Medium',
            case.steps or '',
            case.expected_result or '',
            tags,
            ' | '.join(jira_map.get(case.id, [])),
            ' | '.join(media_map.get(case.id, [])),
            case.creator.name if case.creator else 'N/A',
            case.created_at.strftime('%Y-%m-%d %H:%M:%S') if case.created_at else 'N/A'
        ])
    
    # UTF-8 BOM 추가 (Excel에서 한글 깨짐 방지)
    csv_data = '\ufeff' + output.getvalue()
    
    # 응답 생성
    response = make_response(csv_data)
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    
    # 파일명 인코딩
    filename = f"{section.name}_cases_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    encoded_filename = quote(filename)
    response.headers['Content-Disposition'] = f"attachment; filename*=UTF-8''{encoded_filename}"
    
    return response


@bp.route('/runs/<int:run_id>/export.csv', methods=['GET'])
@login_required
def export_run_csv(run_id):
    """Phase 1: 런 결과 CSV 내보내기"""
    from flask import make_response
    import csv
    from io import StringIO, BytesIO
    from urllib.parse import quote
    
    run = Run.query.get_or_404(run_id)
    
    # CSV 데이터 생성
    output = StringIO()
    writer = csv.writer(output)
    
    # 헤더 작성 (MVP 정의 문서 기준)
    writer.writerow([
        'Run ID', 'Run Name', 'Build Label', 'Run Status', 'Run Type',
        'Section Path', 'Test Case ID', 'Test Case Title', 'Case Version',
        'Priority', 'Result Status', 'Executed By', 'Executed At',
        'Bug Links', 'Comment', 'Case Jira Links', 'Case Media'
    ])
    
    # 데이터 작성
    for run_case in run.run_cases.order_by(RunCase.order_index):
        case = run_case.case
        section_path = case.section.get_full_path() if case.section else 'N/A'
        
        # 최신 결과 가져오기
        latest_result = run_case.get_latest_result()
        
        if latest_result:
            result_status = latest_result.status
            executed_by = latest_result.executor.name if latest_result.executor else 'N/A'
            executed_at = latest_result.created_at.strftime('%Y-%m-%d %H:%M:%S')
            bug_links = latest_result.bug_links or ''
            comment = latest_result.comment or ''
        else:
            result_status = 'NotRun'
            executed_by = ''
            executed_at = ''
            bug_links = ''
            comment = ''
        
        case_jira_links = run_case.jira_links_snapshot or ''
        case_media = run_case.media_names_snapshot or ''

        writer.writerow([
            run.id,
            run.name,
            run.build_label or '',
            'Closed' if run.is_closed else 'Active',
            run.run_type or 'custom',
            section_path,
            case.id,
            case.title,
            run_case.case_version_snapshot or case.version,
            case.priority,
            result_status,
            executed_by,
            executed_at,
            bug_links,
            comment,
            case_jira_links,
            case_media
        ])
    
    # UTF-8 BOM 추가 (Excel에서 한글 깨짐 방지)
    csv_data = '\ufeff' + output.getvalue()
    
    # CSV 응답 생성
    response = make_response(csv_data.encode('utf-8'))
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    
    # 파일명 인코딩 처리 (한글 파일명 지원)
    filename = f'run_{run.id}_{run.name}.csv'
    encoded_filename = quote(filename.encode('utf-8'))
    response.headers['Content-Disposition'] = f"attachment; filename*=UTF-8''{encoded_filename}"
    
    return response


@bp.route('/runs/<int:run_id>/wiki-draft/ai-fill', methods=['POST'])
@login_required
def ai_fill_run_wiki_draft(run_id):
    """
    위키 초안(런 결과 기반) AI 자동 작성.
    - 의도: 사용자가 입력하기 번거로운 '기타 참고사항' 등을 런 결과/코멘트 기반으로 정리
    - 안전: 제공된 데이터(통계/케이스 리스트/버그 링크/코멘트) 기반으로만 작성하도록 지시
    """
    run = Run.query.get_or_404(run_id)
    data = request.get_json(silent=True) or {}
    current_page_data = data.get('current_page_data') or {}

    # 프론트에서 넘어온 실제 데이터 우선
    run_name = current_page_data.get('run_name') or run.name
    build_label = current_page_data.get('build_label') or (run.build_label or '')
    stats = current_page_data.get('stats') or {}
    test_results = current_page_data.get('test_results') or []

    # 버그 링크/코멘트만 추출해서 입력 프롬프트를 짧게 유지
    bug_links = []
    fail_comments = []
    for item in test_results:
        st = (item.get('status') or '').lower()
        if item.get('bug_links'):
            bug_links.append(str(item.get('bug_links')))
        if st in ('fail', 'blocked', 'retest') and item.get('comment'):
            fail_comments.append(str(item.get('comment')))

    bug_links_text = '\n'.join(f'- {b}' for b in bug_links[:50]) if bug_links else '(없음)'
    comments_text = '\n'.join(f'- {c}' for c in fail_comments[:50]) if fail_comments else '(없음)'
    notes_text = (
        f"총 {stats.get('total', 0)}개 중 실행 {stats.get('executed', 0)}개. "
        f"Pass {stats.get('pass', 0)}, Fail {stats.get('fail', 0)}, "
        f"Blocked {stats.get('blocked', 0)}, Retest {stats.get('retest', 0)}, N/A {stats.get('na', 0)}."
    )

    try:
        from app.utils.translator import get_openai_client
        client = get_openai_client()
        if not client:
            return jsonify({'error': '활성화된 API 키가 없습니다.'}), 400

        system_prompt = (
            "너는 QA 리포트 작성 보조 AI다. 반드시 사용자가 제공한 데이터(통계/버그 링크/코멘트)만 기반으로 작성한다. "
            "제공되지 않은 사실(티켓 상태/원인/결론 등)을 추측하거나 만들어내지 않는다. "
            "출력은 JSON 한 덩어리로만 반환한다."
        )
        user_prompt = (
            f"아래는 테스트 런 위키 초안 작성을 위한 입력 데이터다.\n\n"
            f"[Run]\n- 이름: {run_name}\n- Build: {build_label or 'N/A'}\n- 요약: {notes_text}\n\n"
            f"[버그 링크(원문)]\n{bug_links_text}\n\n"
            f"[Fail/Blocked/Retest 코멘트(원문)]\n{comments_text}\n\n"
            "요구사항:\n"
            "- remaining_issues: 위 버그 링크를 중복 제거해 보기 좋게 정리(없으면 빈 문자열)\n"
            "- closed_issues: '기획 의도/수정 안 함 등으로 Closed된 티켓' 섹션에 넣을 수 있는 템플릿(실제 티켓은 제공되지 않았으므로 예시/가정 금지)\n"
            "- notes: 기타 참고사항을 3~6줄로 간결하게 정리(사실 기반)\n\n"
            "반환 JSON 스키마:\n"
            "{ \"remaining_issues\": \"...\", \"closed_issues\": \"...\", \"notes\": \"...\" }\n"
        )

        resp = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            temperature=0.2,
            max_tokens=700
        )
        text = resp.choices[0].message.content.strip()

        # 모델이 JSON 외 텍스트를 섞는 경우를 대비해 매우 방어적으로 파싱
        import json as _json
        obj = None
        try:
            obj = _json.loads(text)
        except Exception:
            # 첫 '{'부터 마지막 '}'까지 슬라이스 시도
            try:
                start = text.find('{')
                end = text.rfind('}')
                if start != -1 and end != -1 and end > start:
                    obj = _json.loads(text[start:end+1])
            except Exception:
                obj = None

        if not isinstance(obj, dict):
            return jsonify({'error': 'AI 응답 파싱 실패', 'raw': text}), 500

        return jsonify({
            'remaining_issues': str(obj.get('remaining_issues') or '').strip(),
            'closed_issues': str(obj.get('closed_issues') or '').strip(),
            'notes': str(obj.get('notes') or '').strip(),
        })

    except Exception as e:
        current_app.logger.error(f'[WikiDraft AI] 오류: {str(e)}')
        return jsonify({'error': f'AI 작성 실패: {str(e)}'}), 500


@bp.route('/runs/<int:run_id>/wiki-draft/publish', methods=['POST'])
@login_required
def publish_run_wiki_draft(run_id):
    """
    위키 링크로 내보내기(옵션).
    - 기본 동작은 '서버 위키 연동 설정이 없는 경우' 501로 안내.
    - Confluence Cloud 연동이 환경변수로 설정된 경우에만, pageId가 포함된 URL에 한해 업데이트를 시도한다.
      (마크다운을 Confluence storage로 변환하는 것은 범위가 커서, 현재는 <pre>로 안전하게 업로드)
    """
    Run.query.get_or_404(run_id)  # 권한/존재 확인용
    data = request.get_json(silent=True) or {}
    wiki_url = (data.get('wiki_url') or '').strip()
    markdown = (data.get('markdown') or '').strip()
    title = (data.get('title') or 'QuickRail Wiki Draft').strip()

    if not wiki_url:
        return jsonify({'error': 'wiki_url이 필요합니다.'}), 400
    if not markdown:
        return jsonify({'error': 'markdown이 비어있습니다.'}), 400

    import os
    base_url = (os.getenv('CONFLUENCE_BASE_URL') or '').rstrip('/')
    email = (os.getenv('CONFLUENCE_EMAIL') or '').strip()
    token = (os.getenv('CONFLUENCE_API_TOKEN') or '').strip()

    if not (base_url and email and token):
        return jsonify({
            'error': '서버에 위키(Confluence) 연동 설정이 없습니다.',
            'hint': '다운로드(md/pdf) 또는 클립보드 복사 후 위키에 붙여넣기 방식으로 사용하세요.'
        }), 501

    # pageId 추출: ?pageId=12345 또는 /pages/12345/
    import re
    page_id = None
    m = re.search(r'[?&]pageId=(\d+)', wiki_url)
    if m:
        page_id = m.group(1)
    if not page_id:
        m = re.search(r'/pages/(\d+)(/|$)', wiki_url)
        if m:
            page_id = m.group(1)

    if not page_id:
        return jsonify({'error': 'Confluence pageId를 URL에서 찾지 못했습니다.'}), 400

    import requests
    from html import escape as html_escape

    # 현재 페이지 버전 조회
    get_url = f'{base_url}/wiki/rest/api/content/{page_id}?expand=version,title'
    r = requests.get(get_url, auth=(email, token), timeout=15)
    if r.status_code >= 300:
        return jsonify({'error': 'Confluence 페이지 조회 실패', 'status': r.status_code, 'body': r.text}), 502

    j = r.json()
    cur_ver = int(((j.get('version') or {}).get('number')) or 1)
    cur_title = j.get('title') or title

    # storage representation: 최소 범위로 <pre>에 markdown을 넣어 업로드 (서식 변환은 추후)
    storage_value = f'<pre>{html_escape(markdown)}</pre>'
    put_payload = {
        'id': str(page_id),
        'type': 'page',
        'title': cur_title,
        'version': {'number': cur_ver + 1},
        'body': {'storage': {'value': storage_value, 'representation': 'storage'}},
    }
    put_url = f'{base_url}/wiki/rest/api/content/{page_id}'
    r2 = requests.put(
        put_url,
        json=put_payload,
        auth=(email, token),
        headers={'Content-Type': 'application/json'},
        timeout=20
    )
    if r2.status_code >= 300:
        return jsonify({'error': 'Confluence 업데이트 실패', 'status': r2.status_code, 'body': r2.text}), 502

    return jsonify({'success': True, 'page_id': page_id, 'wiki_url': wiki_url})


@bp.route('/runs/<int:run_id>/reset', methods=['POST'])
@login_required
def reset_run_results(run_id):
    """런의 모든 결과 초기화"""
    run = Run.query.get_or_404(run_id)
    
    try:
        # 해당 런의 모든 결과 삭제
        Result.query.filter_by(run_id=run_id).delete()
        db.session.commit()
        
        current_app.logger.info(f'Run {run_id} 결과 초기화 by {current_user.email}')
        return jsonify({'success': True, 'message': '모든 결과가 초기화되었습니다.'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Run {run_id} 결과 초기화 실패: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/runs/<int:run_id>/cases/<int:case_id>/history', methods=['GET'])
@login_required
def get_case_result_history(run_id, case_id):
    """특정 케이스의 결과 히스토리"""
    run = Run.query.get_or_404(run_id)
    
    # 해당 런과 케이스의 모든 결과를 시간순으로 조회
    results = Result.query.filter_by(
        run_id=run_id,
        case_id=case_id
    ).order_by(Result.created_at.desc()).all()
    
    return jsonify([{
        'id': r.id,
        'status': r.status,
        'comment': r.comment,
        'executor': r.executor.name,
        'executor_email': r.executor.email,
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

        log_activity_safe(
            user_id=current_user.id,
            action='attachment.upload',
            entity_type='attachment',
            entity_id=attachment.id,
            project_id=result.run.project_id if result.run else None,
            description=f'첨부파일 업로드: {attachment.original_name}',
            meta={'result_id': result_id},
        )
        
        return jsonify({
            'id': attachment.id,
            'original_name': attachment.original_name,
            'created_at': attachment.created_at.isoformat()
        }), 201
    
    return jsonify({'error': '허용되지 않은 파일 형식입니다'}), 400


@bp.route('/attachments/<int:attachment_id>', methods=['GET', 'DELETE'])
@login_required
def get_attachment(attachment_id):
    """첨부파일 보기/다운로드

    기본: 브라우저에서 바로 보기(inline)
    다운로드: ?download=1
    """
    attachment = Attachment.query.get_or_404(attachment_id)

    if request.method == 'DELETE':
        run = attachment.result.run if attachment.result else None
        if run and run.is_closed:
            return jsonify({'error': '완료된 런은 첨부파일을 삭제할 수 없습니다.'}), 400

        # 권한: 업로더(result.executor) 또는 런 생성자 또는 admin/author
        allowed = False
        try:
            if current_user.role in ['admin', 'author']:
                allowed = True
            if attachment.result and attachment.result.executor_id == current_user.id:
                allowed = True
            if run and run.created_by == current_user.id:
                allowed = True
        except Exception:
            pass

        if not allowed:
            return jsonify({'error': '권한이 없습니다.'}), 403

        file_path = attachment.file_path
        attachment_id_val = attachment.id
        original = attachment.original_name
        project_id = run.project_id if run else None

        db.session.delete(attachment)
        db.session.commit()

        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass

        log_activity_safe(
            user_id=current_user.id,
            action='attachment.delete',
            entity_type='attachment',
            entity_id=attachment_id_val,
            project_id=project_id,
            description=f'첨부파일 삭제: {original or attachment_id_val}',
        )

        return jsonify({'success': True})

    download = request.args.get('download', '0') in ['1', 'true', 'True', 'yes', 'y']
    guessed_type, _ = mimetypes.guess_type(attachment.original_name or attachment.file_path)
    return send_file(
        attachment.file_path,
        as_attachment=download,
        download_name=attachment.original_name,
        mimetype=guessed_type
    )


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

    language = (data.get('language') or 'original').strip()
    if language not in ['original', 'ko', 'en']:
        language = 'original'
    
    # 런 이름 자동 생성 (템플릿 이름 + 날짜)
    from datetime import datetime
    default_name = f"{template.name} - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    
    run = Run(
        project_id=template.project_id,
        name=data.get('name', default_name),
        description=data.get('description', template.description),
        build_label=data.get('build_label', ''),  # Phase 1: 빌드 라벨
        created_by=current_user.id,
        run_type=template.run_type or 'custom',
        language=language
    )
    db.session.add(run)
    db.session.flush()
    
    # 템플릿의 케이스로 RunCase 생성 (Phase 1: 케이스 버전 및 내용 스냅샷)
    case_ids = [int(id) for id in template.case_ids.split(',') if id] if template.case_ids else []

    jira_map = {}
    media_map = {}
    if case_ids:
        for l in CaseJiraLink.query.filter(CaseJiraLink.case_id.in_(case_ids)).all():
            jira_map.setdefault(l.case_id, []).append(l.url)
        for m in CaseMedia.query.filter(CaseMedia.case_id.in_(case_ids)).all():
            media_map.setdefault(m.case_id, []).append(m.original_name)

    translations = {}
    if language in ['ko', 'en'] and case_ids:
        translations, _, _ = _ensure_case_translations(case_ids, language, force=False)

    for idx, case_id in enumerate(case_ids):
        case = Case.query.get(case_id)
        if case:
            t = translations.get(case_id) if language in ['ko', 'en'] else None
            title_snapshot = (t or {}).get('title') or case.title
            steps_snapshot = (t or {}).get('steps') or case.steps
            expected_snapshot = (t or {}).get('expected_result') or case.expected_result

            run_case = RunCase(
                run_id=run.id,
                case_id=case_id,
                order_index=idx,
                case_version_snapshot=case.version,
                title_snapshot=title_snapshot,
                steps_snapshot=steps_snapshot,
                expected_result_snapshot=expected_snapshot,
                priority_snapshot=case.priority  # Phase 1 수정: 우선순위 스냅샷
                ,
                jira_links_snapshot=' | '.join(jira_map.get(case_id, [])),
                media_names_snapshot=' | '.join(media_map.get(case_id, []))
            )
            db.session.add(run_case)
    
    db.session.commit()
    
    return jsonify({
        'id': run.id,
        'name': run.name,
        'build_label': run.build_label,
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


# ============================================================
# Translation Prompt API
# ============================================================

@bp.route('/translation-prompts', methods=['GET', 'POST'])
@login_required
def translation_prompts():
    """번역 프롬프트 목록 조회 / 생성"""
    if request.method == 'GET':
        # GET: 모든 사용자 접근 가능
        prompts = TranslationPrompt.query.order_by(TranslationPrompt.updated_at.desc()).all()
        return jsonify([{
            'id': p.id,
            'name': p.name,
            'system_prompt': p.system_prompt,
            'user_prompt_template': p.user_prompt_template,
            'model': p.model or 'gpt-4o-mini',
            'is_active': p.is_active,
            'created_at': p.created_at.isoformat(),
            'updated_at': p.updated_at.isoformat()
        } for p in prompts])
    
    # POST: Admin/Super Admin만 가능
    if current_user.role not in ['Super Admin', 'admin']:
        return jsonify({'error': '권한이 없습니다'}), 403
    
    data = request.get_json()
    
    # 이름 중복 체크
    existing = TranslationPrompt.query.filter_by(name=data['name']).first()
    if existing:
        return jsonify({'error': '이미 존재하는 프롬프트 이름입니다'}), 400
    
    prompt = TranslationPrompt(
        name=data['name'],
        system_prompt=data['system_prompt'],
        user_prompt_template=data['user_prompt_template'],
        model=data.get('model', 'gpt-4o-mini'),
        is_active=False,
        created_by=current_user.id,
        updated_by=current_user.id
    )
    
    db.session.add(prompt)
    db.session.commit()
    
    current_app.logger.info(f'번역 프롬프트 생성: {prompt.name} (모델: {prompt.model}) by {current_user.email}')
    
    return jsonify({
        'id': prompt.id,
        'name': prompt.name,
        'system_prompt': prompt.system_prompt,
        'user_prompt_template': prompt.user_prompt_template,
        'model': prompt.model,
        'is_active': prompt.is_active
    }), 201


@bp.route('/translation-prompts/<int:prompt_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def translation_prompt(prompt_id):
    """번역 프롬프트 조회 / 수정 / 삭제"""
    prompt = TranslationPrompt.query.get_or_404(prompt_id)
    
    if request.method == 'GET':
        # GET: 모든 사용자 접근 가능
        return jsonify({
            'id': prompt.id,
            'name': prompt.name,
            'system_prompt': prompt.system_prompt,
            'user_prompt_template': prompt.user_prompt_template,
            'model': prompt.model or 'gpt-4o-mini',
            'is_active': prompt.is_active,
            'created_at': prompt.created_at.isoformat(),
            'updated_at': prompt.updated_at.isoformat()
        })
    
    # PUT/DELETE: Admin/Super Admin만 가능
    if current_user.role not in ['Super Admin', 'admin']:
        return jsonify({'error': '권한이 없습니다'}), 403
    
    if request.method == 'PUT':
        data = request.get_json()
        
        # 이름 변경 시 중복 체크
        if 'name' in data and data['name'] != prompt.name:
            existing = TranslationPrompt.query.filter_by(name=data['name']).first()
            if existing:
                return jsonify({'error': '이미 존재하는 프롬프트 이름입니다'}), 400
            prompt.name = data['name']
        
        if 'system_prompt' in data:
            prompt.system_prompt = data['system_prompt']
        if 'user_prompt_template' in data:
            prompt.user_prompt_template = data['user_prompt_template']
        if 'model' in data:
            prompt.model = data['model']
        
        prompt.updated_by = current_user.id
        db.session.commit()
        
        current_app.logger.info(f'번역 프롬프트 수정: {prompt.name} (모델: {prompt.model}) by {current_user.email}')
        
        return jsonify({'status': 'updated'})
    
    if request.method == 'DELETE':
        # 활성 프롬프트는 삭제 불가
        if prompt.is_active:
            return jsonify({'error': '활성 프롬프트는 삭제할 수 없습니다'}), 400
        
        name = prompt.name
        db.session.delete(prompt)
        db.session.commit()
        
        current_app.logger.info(f'번역 프롬프트 삭제: {name} by {current_user.email}')
        
        return '', 204


@bp.route('/translation-models', methods=['GET'])
@login_required
def translation_models():
    """사용 가능한 OpenAI 모델 목록 조회 (모든 사용자 접근 가능)"""
    # GET: 모든 사용자 접근 가능 (프롬프트 생성/수정 시 모델 선택을 위해)
    
    from app.utils.model_pricing import get_model_list
    
    models = get_model_list()
    return jsonify(models)


@bp.route('/cases/translate-batch', methods=['POST'])
@login_required
def translate_cases_batch_api():
    """여러 케이스를 일괄 번역합니다"""
    data = request.get_json()
    case_ids = data.get('case_ids', [])
    target_lang = data.get('target_lang')
    force = bool(data.get('force', False))
    
    if not case_ids or not target_lang:
        return jsonify({'error': '케이스 ID 목록과 대상 언어가 필요합니다'}), 400
    
    try:
        cached_translations, translated_count, cached_count = _ensure_case_translations(case_ids, target_lang, force=force)

        results = [{'case_id': cid, 'translation': cached_translations[cid]} for cid in case_ids if cid in cached_translations]

        return jsonify({
            'status': 'success',
            'translated_count': translated_count,
            'cached_count': cached_count,
            'results': results
        })
        
    except TranslationError as e:
        current_app.logger.error(f'배치 번역 실패: {e}')
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        current_app.logger.error(f'배치 번역 중 오류: {e}')
        return jsonify({'error': f'번역 중 오류가 발생했습니다: {str(e)}'}), 500


@bp.route('/translation-prompts/<int:prompt_id>/activate', methods=['POST'])
@login_required
def activate_translation_prompt(prompt_id):
    """번역 프롬프트 활성화"""
    if current_user.role not in ['Super Admin', 'admin']:
        return jsonify({'error': '권한이 없습니다'}), 403
    
    prompt = TranslationPrompt.query.get_or_404(prompt_id)
    
    # 기존 활성 프롬프트 비활성화
    TranslationPrompt.query.filter_by(is_active=True).update({'is_active': False})
    
    # 선택한 프롬프트 활성화
    prompt.is_active = True
    prompt.updated_by = current_user.id
    db.session.commit()
    
    current_app.logger.info(f'번역 프롬프트 활성화: {prompt.name} by {current_user.email}')
    
    return jsonify({'status': 'activated'})


# ============================================================
# Summary Prompt Management API
# ============================================================

@bp.route('/summary-prompts', methods=['GET', 'POST'])
@login_required
def summary_prompts():
    """요약 프롬프트 목록 조회 / 생성"""
    from app.models import SummaryPrompt
    
    if request.method == 'GET':
        # GET: 모든 사용자 접근 가능
        prompts = SummaryPrompt.query.order_by(SummaryPrompt.updated_at.desc()).all()
        return jsonify([{
            'id': p.id,
            'name': p.name,
            'system_prompt': p.system_prompt,
            'user_prompt_template': p.user_prompt_template,
            'model': p.model or 'gpt-4o-mini',
            'is_active': p.is_active,
            'created_at': p.created_at.isoformat(),
            'updated_at': p.updated_at.isoformat()
        } for p in prompts])
    
    # POST: Admin/Super Admin만 가능
    if current_user.role not in ['Super Admin', 'admin']:
        return jsonify({'error': '권한이 없습니다'}), 403
    
    data = request.get_json()
    
    # 이름 중복 체크
    existing = SummaryPrompt.query.filter_by(name=data['name']).first()
    if existing:
        return jsonify({'error': '이미 존재하는 프롬프트 이름입니다'}), 400
    
    prompt = SummaryPrompt(
        name=data['name'],
        system_prompt=data['system_prompt'],
        user_prompt_template=data['user_prompt_template'],
        model=data.get('model', 'gpt-4o-mini'),
        is_active=False,
        created_by=current_user.id,
        updated_by=current_user.id
    )
    
    db.session.add(prompt)
    db.session.commit()
    
    current_app.logger.info(f'요약 프롬프트 생성: {prompt.name} (모델: {prompt.model}) by {current_user.email}')
    
    return jsonify({
        'id': prompt.id,
        'name': prompt.name,
        'system_prompt': prompt.system_prompt,
        'user_prompt_template': prompt.user_prompt_template,
        'model': prompt.model,
        'is_active': prompt.is_active
    }), 201


@bp.route('/summary-prompts/<int:prompt_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def summary_prompt(prompt_id):
    """요약 프롬프트 조회 / 수정 / 삭제"""
    from app.models import SummaryPrompt
    prompt = SummaryPrompt.query.get_or_404(prompt_id)
    
    if request.method == 'GET':
        # GET: 모든 사용자 접근 가능
        return jsonify({
            'id': prompt.id,
            'name': prompt.name,
            'system_prompt': prompt.system_prompt,
            'user_prompt_template': prompt.user_prompt_template,
            'model': prompt.model or 'gpt-4o-mini',
            'is_active': prompt.is_active,
            'created_at': prompt.created_at.isoformat(),
            'updated_at': prompt.updated_at.isoformat()
        })
    
    # PUT/DELETE: Admin/Super Admin만 가능
    if current_user.role not in ['Super Admin', 'admin']:
        return jsonify({'error': '권한이 없습니다'}), 403
    
    if request.method == 'PUT':
        data = request.get_json()
        
        # 이름 변경 시 중복 체크
        if 'name' in data and data['name'] != prompt.name:
            existing = SummaryPrompt.query.filter_by(name=data['name']).first()
            if existing:
                return jsonify({'error': '이미 존재하는 프롬프트 이름입니다'}), 400
            prompt.name = data['name']
        
        if 'system_prompt' in data:
            prompt.system_prompt = data['system_prompt']
        if 'user_prompt_template' in data:
            prompt.user_prompt_template = data['user_prompt_template']
        if 'model' in data:
            prompt.model = data['model']
        
        prompt.updated_by = current_user.id
        db.session.commit()
        
        current_app.logger.info(f'요약 프롬프트 수정: {prompt.name} (모델: {prompt.model}) by {current_user.email}')
        
        return jsonify({'status': 'updated'})
    
    if request.method == 'DELETE':
        # 활성 프롬프트는 삭제 불가
        if prompt.is_active:
            return jsonify({'error': '활성 프롬프트는 삭제할 수 없습니다'}), 400
        
        name = prompt.name
        db.session.delete(prompt)
        db.session.commit()
        
        current_app.logger.info(f'요약 프롬프트 삭제: {name} by {current_user.email}')
        
        return jsonify({'status': 'deleted'})


@bp.route('/summary-prompts/<int:prompt_id>/activate', methods=['POST'])
@login_required
def activate_summary_prompt(prompt_id):
    """요약 프롬프트 활성화"""
    if current_user.role not in ['Super Admin', 'admin']:
        return jsonify({'error': '권한이 없습니다'}), 403
    
    from app.models import SummaryPrompt
    prompt = SummaryPrompt.query.get_or_404(prompt_id)
    
    # 기존 활성 프롬프트 비활성화
    SummaryPrompt.query.filter_by(is_active=True).update({'is_active': False})
    
    # 선택한 프롬프트 활성화
    prompt.is_active = True
    prompt.updated_by = current_user.id
    db.session.commit()
    
    current_app.logger.info(f'요약 프롬프트 활성화: {prompt.name} by {current_user.email}')
    
    return jsonify({'status': 'activated'})


# ============================================================
# Jira One-Button Issue API
# ============================================================

def _get_or_create_jira_config():
    cfg = JiraConfig.query.order_by(JiraConfig.id.asc()).first()
    if not cfg:
        cfg = JiraConfig(
            enabled=False,
            issue_type='Bug',
            created_by=getattr(current_user, 'id', None),
            updated_by=getattr(current_user, 'id', None)
        )
        db.session.add(cfg)
        db.session.commit()
    return cfg


def _split_csv(value: str):
    if not value:
        return []
    return [v.strip() for v in str(value).split(',') if v.strip()]


def _to_adf(text: str):
    """Plain text -> Atlassian Document Format(doc)"""
    if not text or not str(text).strip():
        return None
    lines = str(text).splitlines()
    content = []
    for line in lines:
        # 빈 줄도 단락으로 유지
        if line.strip():
            content.append({
                "type": "paragraph",
                "content": [{"type": "text", "text": line}]
            })
        else:
            content.append({"type": "paragraph", "content": []})
    return {"type": "doc", "version": 1, "content": content}


@bp.route('/jira/config/public', methods=['GET'])
@login_required
def get_jira_config_public():
    """Jira 설정 조회 (민감 정보 제외)"""
    cfg = _get_or_create_jira_config()
    return jsonify({
        'enabled': bool(cfg.enabled),
        'base_url': cfg.base_url or '',
        'project_key': cfg.project_key or '',
        'issue_type': cfg.issue_type or 'Bug',
        'default_components': cfg.default_components or '',
        'default_labels': cfg.default_labels or '',
        'default_priority': cfg.default_priority or ''
    })


@bp.route('/jira/config', methods=['GET', 'PUT'])
@login_required
def jira_config_admin():
    """Jira 설정 조회/수정 (Admin만)"""
    if not current_user.is_admin():
        return jsonify({'error': '권한이 없습니다'}), 403
    
    cfg = _get_or_create_jira_config()
    
    if request.method == 'GET':
        return jsonify({
            'enabled': bool(cfg.enabled),
            'base_url': cfg.base_url or '',
            'email': cfg.email or '',
            'api_token': cfg.api_token or '',
            'project_key': cfg.project_key or '',
            'issue_type': cfg.issue_type or 'Bug',
            'default_components': cfg.default_components or '',
            'default_labels': cfg.default_labels or '',
            'default_priority': cfg.default_priority or ''
        })
    
    data = request.get_json() or {}
    
    cfg.enabled = bool(data.get('enabled', False))
    cfg.base_url = (data.get('base_url') or '').strip() or None
    cfg.email = (data.get('email') or '').strip() or None
    # 보안/UX: api_token은 빈 값이면 기존 값 유지 (의도치 않은 삭제 방지)
    api_token_in = (data.get('api_token') or '').strip()
    if api_token_in:
        cfg.api_token = api_token_in
    cfg.project_key = (data.get('project_key') or '').strip() or None
    cfg.issue_type = (data.get('issue_type') or '').strip() or 'Bug'
    cfg.default_components = (data.get('default_components') or '').strip() or None
    cfg.default_labels = (data.get('default_labels') or '').strip() or None
    cfg.default_priority = (data.get('default_priority') or '').strip() or None
    cfg.updated_by = current_user.id
    
    db.session.commit()
    
    return jsonify({'status': 'updated'})


@bp.route('/jira/issues', methods=['POST'])
@login_required
def jira_create_issue():
    """Jira 이슈 생성 (원버튼)"""
    cfg = _get_or_create_jira_config()
    if not cfg.enabled:
        return jsonify({'success': False, 'error': 'Jira 연동이 비활성화되어 있습니다.'}), 400
    
    if not (cfg.base_url and cfg.email and cfg.api_token and cfg.project_key and cfg.issue_type):
        return jsonify({'success': False, 'error': 'Jira 설정이 불완전합니다. /settings에서 설정을 확인하세요.'}), 400
    
    data = request.get_json() or {}
    summary = (data.get('summary') or '').strip()
    if not summary:
        return jsonify({'success': False, 'error': 'summary는 필수입니다.'}), 400
    
    # 입력값 (문서 스키마 일부 지원)
    component = data.get('component') or data.get('components') or cfg.default_components or ''
    label = data.get('label') or data.get('labels') or cfg.default_labels or ''
    priority = data.get('priority') or cfg.default_priority or ''
    fixversion = data.get('fixversion') or ''
    description = data.get('description') or ''
    steps = data.get('steps') or ''
    
    fields = {
        "project": {"key": cfg.project_key},
        "issuetype": {"name": cfg.issue_type},
        "summary": summary
    }
    
    adf_desc_parts = []
    if steps and str(steps).strip():
        adf_desc_parts.append("[Steps to Reproduce]\n" + str(steps))
    if description and str(description).strip():
        adf_desc_parts.append("[Description]\n" + str(description))
    adf_text = "\n\n".join(adf_desc_parts).strip()
    adf = _to_adf(adf_text)
    if adf:
        fields["description"] = adf
    
    labels_list = _split_csv(label)
    if labels_list:
        fields["labels"] = labels_list
    
    components_list = _split_csv(component)
    if components_list:
        fields["components"] = [{"name": c} for c in components_list]
    
    fix_versions = _split_csv(fixversion)
    if fix_versions:
        fields["fixVersions"] = [{"name": v} for v in fix_versions]
    
    if priority and str(priority).strip():
        fields["priority"] = {"name": str(priority).strip()}
    
    payload = {"fields": fields}
    
    try:
        api_url = cfg.base_url.rstrip('/') + '/rest/api/3/issue'
        res = requests.post(
            api_url,
            json=payload,
            auth=(cfg.email, cfg.api_token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=15
        )
        if res.status_code >= 400:
            # Jira 에러 메시지 최대한 전달
            try:
                err_json = res.json()
            except Exception:
                err_json = None
            details = None
            field_errors = None
            if isinstance(err_json, dict):
                field_errors = err_json.get('errors')
                details = err_json.get('errorMessages')
            return jsonify({
                'success': False,
                'error': f'이슈 생성 실패 ({res.status_code})',
                'details': details,
                'field_errors': field_errors,
                'raw_error': res.text
            }), 400
        
        out = res.json()
        issue_key = out.get('key')
        issue_url = (cfg.base_url.rstrip('/') + f'/browse/{issue_key}') if issue_key else None
        return jsonify({
            'success': True,
            'issue_key': issue_key,
            'issue_url': issue_url,
            'message': 'JIRA 이슈가 성공적으로 생성되었습니다.'
        })
    except requests.RequestException as e:
        return jsonify({'success': False, 'error': f'Jira 요청 실패: {str(e)}'}), 500


# ============================================================
# API Key Management API
# ============================================================

@bp.route('/api-keys', methods=['GET', 'POST'])
@login_required
def api_keys():
    """API 키 목록 조회 / 생성 (Super Admin만)"""
    if not current_user.is_admin():
        return jsonify({'error': '권한이 없습니다'}), 403
    
    if request.method == 'GET':
        keys = APIKey.query.order_by(APIKey.updated_at.desc()).all()
        return jsonify([{
            'id': k.id,
            'name': k.name,
            'api_key': k.api_key,
            'is_active': k.is_active,
            'last_used_at': k.last_used_at.isoformat() if k.last_used_at else None,
            'created_at': k.created_at.isoformat(),
            'updated_at': k.updated_at.isoformat()
        } for k in keys])
    
    # POST: 새 API 키 생성
    data = request.get_json()
    
    # 이름 중복 체크
    existing = APIKey.query.filter_by(name=data['name']).first()
    if existing:
        return jsonify({'error': '이미 존재하는 키 이름입니다'}), 400
    
    # API 키 유효성 검사
    api_key = data['api_key'].strip()
    if not api_key.startswith('sk-'):
        return jsonify({'error': 'OpenAI API 키는 sk-로 시작해야 합니다'}), 400
    
    key = APIKey(
        name=data['name'],
        api_key=api_key,
        is_active=False,
        created_by=current_user.id,
        updated_by=current_user.id
    )
    
    db.session.add(key)
    db.session.commit()
    
    current_app.logger.info(f'API 키 생성: {key.name} by {current_user.email}')
    
    return jsonify({
        'id': key.id,
        'name': key.name,
        'is_active': key.is_active
    }), 201


@bp.route('/api-keys/<int:key_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def api_key(key_id):
    """API 키 조회 / 수정 / 삭제 (Super Admin만)"""
    if not current_user.is_admin():
        return jsonify({'error': '권한이 없습니다'}), 403
    
    key = APIKey.query.get_or_404(key_id)
    
    if request.method == 'GET':
        return jsonify({
            'id': key.id,
            'name': key.name,
            'api_key': key.api_key,
            'is_active': key.is_active,
            'last_used_at': key.last_used_at.isoformat() if key.last_used_at else None,
            'created_at': key.created_at.isoformat(),
            'updated_at': key.updated_at.isoformat()
        })
    
    if request.method == 'PUT':
        data = request.get_json()
        
        # 이름 변경 시 중복 체크
        if 'name' in data and data['name'] != key.name:
            existing = APIKey.query.filter_by(name=data['name']).first()
            if existing:
                return jsonify({'error': '이미 존재하는 키 이름입니다'}), 400
            key.name = data['name']
        
        if 'api_key' in data:
            api_key_value = data['api_key'].strip()
            if not api_key_value.startswith('sk-'):
                return jsonify({'error': 'OpenAI API 키는 sk-로 시작해야 합니다'}), 400
            key.api_key = api_key_value
        
        key.updated_by = current_user.id
        db.session.commit()
        
        current_app.logger.info(f'API 키 수정: {key.name} by {current_user.email}')
        
        return jsonify({'status': 'updated'})
    
    if request.method == 'DELETE':
        # 활성 키는 삭제 불가
        if key.is_active:
            return jsonify({'error': '활성 API 키는 삭제할 수 없습니다'}), 400
        
        name = key.name
        db.session.delete(key)
        db.session.commit()
        
        current_app.logger.info(f'API 키 삭제: {name} by {current_user.email}')
        
        return '', 204


@bp.route('/api-keys/<int:key_id>/activate', methods=['POST'])
@login_required
def activate_api_key(key_id):
    """API 키 활성화 (Super Admin만)"""
    if not current_user.is_admin():
        return jsonify({'error': '권한이 없습니다'}), 403
    
    key = APIKey.query.get_or_404(key_id)
    
    # 기존 활성 키 비활성화
    APIKey.query.filter_by(is_active=True).update({'is_active': False})
    
    # 선택한 키 활성화
    key.is_active = True
    key.updated_by = current_user.id
    db.session.commit()
    
    current_app.logger.info(f'API 키 활성화: {key.name} by {current_user.email}')
    
    return jsonify({'status': 'activated'})


@bp.route('/api-keys/usage', methods=['GET'])
@login_required
def api_key_usage():
    """API 사용량 조회 (Super Admin만)"""
    if not current_user.is_admin():
        return jsonify({'error': '권한이 없습니다'}), 403
    
    try:
        # 활성 API 키 조회
        active_key = APIKey.query.filter_by(is_active=True).first()
        if not active_key:
            return jsonify({'error': 'API 키가 설정되지 않았습니다'}), 400
        
        from datetime import datetime, timedelta
        
        # QuickRail 자체 사용량 통계 (TranslationUsage 테이블 기반)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        
        # 최근 30일 QuickRail 사용량
        quickrail_30d = db.session.query(
            func.count(TranslationUsage.id).label('requests'),
            func.sum(TranslationUsage.total_tokens).label('tokens'),
            func.sum(TranslationUsage.cost).label('cost')
        ).filter(TranslationUsage.created_at >= thirty_days_ago).first()
        
        # 최근 7일 QuickRail 사용량
        quickrail_7d = db.session.query(
            func.count(TranslationUsage.id).label('requests'),
            func.sum(TranslationUsage.total_tokens).label('tokens'),
            func.sum(TranslationUsage.cost).label('cost')
        ).filter(TranslationUsage.created_at >= seven_days_ago).first()
        
        # 전체 QuickRail 사용량
        quickrail_total = db.session.query(
            func.count(TranslationUsage.id).label('requests'),
            func.sum(TranslationUsage.total_tokens).label('tokens'),
            func.sum(TranslationUsage.cost).label('cost')
        ).first()
        
        # 최근 7일 일별 통계
        daily_breakdown = []
        for i in range(6, -1, -1):  # 6일 전부터 오늘까지
            day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=i)
            day_end = day_start + timedelta(days=1)
            
            day_usage = db.session.query(
                func.count(TranslationUsage.id).label('requests'),
                func.sum(TranslationUsage.total_tokens).label('tokens'),
                func.sum(TranslationUsage.cost).label('cost')
            ).filter(
                TranslationUsage.created_at >= day_start,
                TranslationUsage.created_at < day_end
            ).first()
            
            daily_breakdown.append({
                'date': day_start.strftime('%Y-%m-%d'),
                'requests': day_usage.requests or 0,
                'tokens': int(day_usage.tokens or 0),
                'cost': float(day_usage.cost or 0)
            })
        
        # 언어별 통계 (최근 30일)
        lang_stats = db.session.query(
            TranslationUsage.source_lang,
            TranslationUsage.target_lang,
            func.count(TranslationUsage.id).label('requests'),
            func.sum(TranslationUsage.total_tokens).label('tokens')
        ).filter(
            TranslationUsage.created_at >= thirty_days_ago
        ).group_by(
            TranslationUsage.source_lang,
            TranslationUsage.target_lang
        ).all()
        
        language_breakdown = [
            {
                'direction': f'{stat.source_lang} → {stat.target_lang}',
                'requests': stat.requests,
                'tokens': int(stat.tokens or 0)
            }
            for stat in lang_stats
        ]
        
        return jsonify({
            'quickrail_usage': {
                'total': {
                    'requests': quickrail_total.requests or 0,
                    'tokens': int(quickrail_total.tokens or 0),
                    'cost': float(quickrail_total.cost or 0)
                },
                'last_30_days': {
                    'requests': quickrail_30d.requests or 0,
                    'tokens': int(quickrail_30d.tokens or 0),
                    'cost': float(quickrail_30d.cost or 0)
                },
                'last_7_days': {
                    'requests': quickrail_7d.requests or 0,
                    'tokens': int(quickrail_7d.tokens or 0),
                    'cost': float(quickrail_7d.cost or 0)
                }
            },
            'daily_breakdown': daily_breakdown,
            'language_breakdown': language_breakdown,
            'note': '실제 OpenAI 사용량은 OpenAI 대시보드에서 확인하세요: https://platform.openai.com/usage'
        })
        
    except Exception as e:
        current_app.logger.error(f'API 사용량 조회 실패: {e}')
        return jsonify({'error': f'사용량 조회 실패: {str(e)}'}), 500


# ============================================================
# Case Import API (CSV/Excel)
# ============================================================

@bp.route('/projects/<int:project_id>/cases/import/preview', methods=['POST'])
@login_required
def import_cases_preview(project_id):
    """케이스 import 미리보기 (CSV/Excel 파일 파싱) - 컬럼 정보만 반환"""
    project = Project.query.get_or_404(project_id)
    
    if 'file' not in request.files:
        return jsonify({'error': '파일이 없습니다'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': '파일이 선택되지 않았습니다'}), 400
    
    filename = secure_filename(file.filename)
    file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    
    if file_ext not in ['csv', 'xlsx', 'xls']:
        return jsonify({'error': '지원하지 않는 파일 형식입니다. CSV 또는 Excel 파일만 가능합니다.'}), 400
    
    try:
        import pandas as pd
        import io
        
        # 파일 읽기
        if file_ext == 'csv':
            # CSV 파일 - 인코딩 자동 감지
            content = file.read()
            try:
                # UTF-8 시도
                df = pd.read_csv(io.BytesIO(content), encoding='utf-8')
            except UnicodeDecodeError:
                # CP949(한글 Windows) 시도
                df = pd.read_csv(io.BytesIO(content), encoding='cp949')
        else:
            # Excel 파일
            df = pd.read_excel(file, engine='openpyxl')
        
        # 원본 컬럼명 보존
        original_columns = df.columns.tolist()
        
        # 컬럼명 정규화 (소문자, 공백 제거) - 내부 처리용
        df.columns = df.columns.str.strip()
        
        # 첫 5개 행 샘플 데이터
        sample_data = []
        for idx, row in df.head(5).iterrows():
            sample_row = {}
            for col in df.columns:
                val = row[col]
                if pd.notna(val):
                    sample_row[col] = str(val).strip()
                else:
                    sample_row[col] = ''
            sample_data.append(sample_row)
        
        return jsonify({
            'success': True,
            'total_rows': len(df),
            'columns': original_columns,
            'sample_data': sample_data
        })
        
    except Exception as e:
        current_app.logger.error(f'파일 파싱 실패: {e}')
        return jsonify({'error': f'파일 파싱 실패: {str(e)}'}), 500


@bp.route('/projects/<int:project_id>/cases/import/parse', methods=['POST'])
@login_required
def import_cases_parse(project_id):
    """컬럼 매핑을 적용하여 데이터 파싱"""
    project = Project.query.get_or_404(project_id)
    
    if 'file' not in request.files:
        return jsonify({'error': '파일이 없습니다'}), 400
    
    file = request.files['file']
    data = request.form.get('column_mapping')
    
    if not data:
        return jsonify({'error': '컬럼 매핑 정보가 없습니다'}), 400
    
    import json
    column_mapping = json.loads(data)
    
    filename = secure_filename(file.filename)
    file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    
    try:
        import pandas as pd
        import io
        
        # 파일 읽기
        if file_ext == 'csv':
            content = file.read()
            try:
                df = pd.read_csv(io.BytesIO(content), encoding='utf-8')
            except UnicodeDecodeError:
                df = pd.read_csv(io.BytesIO(content), encoding='cp949')
        else:
            df = pd.read_excel(file, engine='openpyxl')
        
        # 컬럼명 정규화
        df.columns = df.columns.str.strip()
        
        # 데이터 파싱
        cases_preview = []
        section_names = set()  # 섹션 이름 수집
        
        for idx, row in df.iterrows():
            case_data = {
                'row_number': idx + 1,
                'title': '',
                'steps': '',
                'expected_result': '',
                'priority': 'Medium',
                'jira_links': '',
                'media': '',
                'section_full': '',
                'section_1': '',
                'section_2': '',
                'section_3': '',
                'section_4': ''
            }
            
            # 컬럼 매핑 적용
            for target_field, source_column in column_mapping.items():
                if source_column and source_column in df.columns:
                    val = row[source_column]
                    if pd.notna(val):
                        case_data[target_field] = str(val).strip()

            # 섹션 전체(section_full) 우선 적용: 'a > b > c' -> section_1..4
            if case_data.get('section_full'):
                parts = [p.strip() for p in str(case_data['section_full']).split('>')]
                parts = [p for p in parts if p]
                for i in range(1, 5):
                    case_data[f'section_{i}'] = parts[i - 1] if (i - 1) < len(parts) else ''
            
            # 빈 제목은 건너뛰기
            if not case_data['title'] or case_data['title'] == 'nan':
                continue
            
            # 우선순위 정규화
            priority_map = {
                'blocker': 'Blocker',
                'critical': 'Critical',
                'high': 'High',
                'medium': 'Medium',
                'low': 'Low',
                'p0': 'Blocker',
                'p1': 'Critical',
                'p2': 'High',
                'p3': 'Medium',
                'p4': 'Low'
            }
            case_data['priority'] = priority_map.get(case_data['priority'].lower(), 'Medium')
            
            # 섹션 정보 수집
            for i in range(1, 5):
                if case_data[f'section_{i}']:
                    section_names.add(case_data[f'section_{i}'])
            
            cases_preview.append(case_data)
        
        return jsonify({
            'success': True,
            'total_rows': len(df),
            'valid_cases': len(cases_preview),
            'skipped_rows': len(df) - len(cases_preview),
            'cases': cases_preview,
            'section_names': sorted(list(section_names))
        })
        
    except Exception as e:
        current_app.logger.error(f'데이터 파싱 실패: {e}')
        return jsonify({'error': f'데이터 파싱 실패: {str(e)}'}), 500


@bp.route('/projects/<int:project_id>/cases/import/confirm', methods=['POST'])
@login_required
def import_cases_confirm(project_id):
    """케이스 import 확정 (DB에 저장) - 섹션 자동 생성 지원"""
    project = Project.query.get_or_404(project_id)
    
    data = request.get_json()
    cases_data = data.get('cases', [])
    
    if not cases_data:
        return jsonify({'error': '가져올 케이스가 없습니다'}), 400
    
    try:
        # 섹션 캐시 (이름 -> Section 객체)
        section_cache = {}
        
        def get_or_create_section(section_names, parent_id=None, depth=1):
            """섹션 계층 구조 생성 또는 조회"""
            if not section_names or depth > 4:
                return parent_id
            
            section_name = section_names[0]
            if not section_name:
                return parent_id
            
            # 캐시 키 생성
            cache_key = f"{parent_id}_{section_name}"
            
            if cache_key in section_cache:
                section = section_cache[cache_key]
            else:
                # 기존 섹션 찾기
                section = Section.query.filter_by(
                    project_id=project_id,
                    name=section_name,
                    parent_id=parent_id
                ).first()
                
                if not section:
                    # 새 섹션 생성
                    max_order = db.session.query(func.max(Section.order_index)).filter_by(
                        project_id=project_id,
                        parent_id=parent_id
                    ).scalar() or 0
                    
                    section = Section(
                        project_id=project_id,
                        name=section_name,
                        parent_id=parent_id,
                        order_index=max_order + 1
                    )
                    db.session.add(section)
                    db.session.flush()  # ID 생성
                    current_app.logger.info(f'섹션 생성: {section_name} (depth: {depth}, parent: {parent_id})')
                
                section_cache[cache_key] = section
            
            # 다음 depth 처리
            if len(section_names) > 1:
                return get_or_create_section(section_names[1:], section.id, depth + 1)
            else:
                return section.id
        
        created_cases = []
        
        def _split_multi(value: str):
            if not value:
                return []
            text = str(value).replace('\r', '\n')
            # 흔한 구분자: 줄바꿈, 콤마, 파이프
            parts = []
            for chunk in text.split('\n'):
                for p in chunk.split('|'):
                    for q in p.split(','):
                        s = q.strip()
                        if s:
                            parts.append(s)
            # 중복 제거(순서 유지)
            seen = set()
            out = []
            for x in parts:
                if x not in seen:
                    seen.add(x)
                    out.append(x)
            return out

        def _download_media_to_case(media_url: str, case_id: int):
            """미디어 URL을 다운로드하여 CaseMedia로 저장 (실패 시 None)"""
            try:
                if not media_url.startswith('http://') and not media_url.startswith('https://'):
                    return None
                resp = requests.get(media_url, stream=True, timeout=10)
                if resp.status_code >= 400:
                    return None
                # 파일명 추출
                from urllib.parse import urlparse
                path = urlparse(media_url).path or ''
                name = os.path.basename(path) or f'case_media_{case_id}'
                name = secure_filename(name)
                if not name:
                    return None
                if not allowed_file(name):
                    return None
                media_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'case_media')
                os.makedirs(media_dir, exist_ok=True)
                ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                stored = f"{ts}_{name}"
                filepath = os.path.join(media_dir, stored)
                with open(filepath, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
                mime = resp.headers.get('Content-Type')
                cm = CaseMedia(
                    case_id=case_id,
                    file_path=filepath,
                    original_name=name,
                    mime_type=mime,
                    created_by=current_user.id
                )
                db.session.add(cm)
                return cm
            except Exception:
                return None

        for case_data in cases_data:
            # 섹션 계층 구조 생성
            section_names = []
            for i in range(1, 5):
                section_name = case_data.get(f'section_{i}', '').strip()
                if section_name:
                    section_names.append(section_name)
                else:
                    break
            
            # 섹션 ID 가져오기 (없으면 생성)
            if section_names:
                final_section_id = get_or_create_section(section_names)
            else:
                return jsonify({'error': '섹션 정보가 없습니다. 최소 1개의 섹션이 필요합니다.'}), 400
            
            # 현재 섹션의 최대 order_index 가져오기
            max_order = db.session.query(func.max(Case.order_index)).filter_by(
                section_id=final_section_id
            ).scalar() or 0
            
            # 케이스 생성
            new_case = Case(
                project_id=project_id,
                section_id=final_section_id,
                title=case_data['title'],
                steps=case_data.get('steps', ''),
                expected_result=case_data.get('expected_result', ''),
                priority=case_data.get('priority', 'Medium'),
                status='active',
                order_index=max_order + 1,
                created_by=current_user.id,
                updated_by=current_user.id
            )
            db.session.add(new_case)
            db.session.flush()  # ID 생성

            # Jira 링크 저장
            try:
                for u in _split_multi(case_data.get('jira_links', '')):
                    db.session.add(CaseJiraLink(case_id=new_case.id, url=u, created_by=current_user.id))
            except Exception:
                pass

            # 미디어(URL) 저장: 다운로드 후 CaseMedia 생성
            try:
                for media_url in _split_multi(case_data.get('media', '')):
                    _download_media_to_case(media_url, new_case.id)
            except Exception:
                pass
            
            # 원본 언어로 캐시 저장 (중복 체크)
            try:
                source_lang = detect_language(new_case.title)
                
                # 기존 번역이 있는지 확인
                existing_translation = CaseTranslation.query.filter_by(
                    case_id=new_case.id,
                    target_lang=source_lang
                ).first()
                
                if not existing_translation:
                    original_translation = CaseTranslation(
                        case_id=new_case.id,
                        source_lang=source_lang,
                        target_lang=source_lang,
                        title=new_case.title,
                        steps=new_case.steps,
                        expected_result=new_case.expected_result
                    )
                    db.session.add(original_translation)
            except Exception as e:
                current_app.logger.warning(f'케이스 {new_case.id} 번역 캐시 저장 실패: {e}')
            
            created_cases.append({
                'id': new_case.id,
                'title': new_case.title,
                'section_path': ' > '.join(section_names)
            })
        
        db.session.commit()
        
        current_app.logger.info(f'{len(created_cases)}개 케이스 import 완료 (프로젝트: {project_id}) by {current_user.email}')
        
        return jsonify({
            'success': True,
            'created_count': len(created_cases),
            'cases': created_cases,
            'created_sections': len(section_cache)
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'케이스 import 실패: {e}')
        return jsonify({'error': f'케이스 저장 실패: {str(e)}'}), 500


