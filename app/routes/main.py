from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, current_app, send_file
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload, selectinload
from app import db
from app.models import Project, Section, Case, Run, Tag, User, TranslationPrompt, APIKey, Result, FeedbackPost, FeedbackAttachment, FeedbackPostView, CaseJiraLink, CaseMedia
from werkzeug.utils import secure_filename
from datetime import datetime
import os
from sqlalchemy.exc import IntegrityError

bp = Blueprint('main', __name__)

def _is_feedback_admin(user) -> bool:
    """관리자(admin/super admin) 판별 (레거시 role 값까지 방어적으로 처리)"""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    try:
        if user.is_admin() or user.is_super_admin():
            return True
    except Exception:
        pass
    role = (getattr(user, 'role', '') or '').strip()
    return role in ['admin', 'Admin', 'super admin', 'Super Admin', 'super_admin', 'superadmin']


def _allowed_feedback_file(filename: str) -> bool:
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in {
        'png', 'jpg', 'jpeg', 'gif', 'webp',
        'mp4', 'webm', 'mov'
    }


def _save_feedback_attachments(post: FeedbackPost, files) -> tuple[int, list[str]]:
    """첨부 파일 저장 및 DB row 생성. (저장 실패 파일은 에러 메시지로 반환)"""
    if not files:
        return 0, []

    upload_root = current_app.config.get('UPLOAD_FOLDER')
    if not upload_root:
        return 0, ['UPLOAD_FOLDER 설정이 없습니다.']

    max_mb = int(current_app.config.get('FEEDBACK_ATTACHMENT_MAX_MB', 25) or 25)
    max_bytes = max(1, max_mb) * 1024 * 1024

    saved = 0
    errors: list[str] = []
    base_dir = os.path.join(upload_root, 'feedback', f'post_{post.id}')
    os.makedirs(base_dir, exist_ok=True)

    for f in files:
        if not f or not getattr(f, 'filename', None):
            continue
        if not _allowed_feedback_file(f.filename):
            errors.append(f'허용되지 않는 파일 형식: {f.filename}')
            continue

        try:
            original_name = f.filename
            safe = secure_filename(original_name) or 'file'
            ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')
            filename = f'fb_{post.id}_{ts}_{safe}'
            filepath = os.path.join(base_dir, filename)
            f.save(filepath)

            size = None
            try:
                size = os.path.getsize(filepath)
            except Exception:
                size = None

            # 파일 1개당 용량 제한(기본 25MB)
            if size is not None and size > max_bytes:
                try:
                    os.remove(filepath)
                except Exception:
                    pass
                errors.append(f'파일 용량 초과({max_mb}MB): {original_name}')
                continue

            att = FeedbackAttachment(
                post_id=post.id,
                file_path=filepath,
                original_name=original_name,
                mime_type=getattr(f, 'mimetype', None),
                file_size=size,
                uploaded_by=current_user.id if current_user.is_authenticated else None,
            )
            db.session.add(att)
            saved += 1
        except Exception as e:
            errors.append(f'첨부 저장 실패({getattr(f, "filename", "unknown")}): {str(e)}')

    return saved, errors


@bp.route('/feedback')
@login_required
def feedback_list():
    """피드백/공지 게시판 목록 (모든 역할 접근 가능)"""
    is_admin = _is_feedback_admin(current_user)

    query = FeedbackPost.query.options(joinedload(FeedbackPost.creator))
    if not is_admin:
        # 비관리자는 "공개글" + "내가 작성한 글(관리자만 보기 포함)"만 볼 수 있게 처리
        query = query.filter(
            db.or_(
                FeedbackPost.is_admin_only.is_(False),
                FeedbackPost.created_by == current_user.id
            )
        )

    sort = (request.args.get('sort') or 'created_desc').strip()

    # 정렬: 기본은 생성일 최신순
    if sort == 'created_asc':
        order = (FeedbackPost.created_at.asc(), FeedbackPost.id.asc())
    elif sort == 'updated_desc':
        order = (FeedbackPost.updated_at.desc(), FeedbackPost.created_at.desc(), FeedbackPost.id.desc())
    elif sort == 'views_desc':
        order = (FeedbackPost.view_count.desc(), FeedbackPost.created_at.desc(), FeedbackPost.id.desc())
    else:  # created_desc
        sort = 'created_desc'
        order = (FeedbackPost.created_at.desc(), FeedbackPost.id.desc())

    # 공지글 최상단 고정 (여러 개 가능)
    posts = query.order_by(
        FeedbackPost.is_notice.desc(),
        *order
    ).all()

    return render_template('main/feedback_list.html', posts=posts, is_admin=is_admin, current_sort=sort)


@bp.route('/feedback/new', methods=['GET', 'POST'])
@login_required
def feedback_new():
    """피드백 글 작성"""
    is_admin = _is_feedback_admin(current_user)

    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()
        content = (request.form.get('content') or '').strip()
        status = (request.form.get('status') or 'To do').strip()

        if not title:
            flash('제목을 입력하세요.', 'error')
            return render_template('main/feedback_form.html', post=None, is_admin=is_admin)
        if not content:
            flash('내용을 입력하세요.', 'error')
            return render_template('main/feedback_form.html', post=None, is_admin=is_admin)

        # 옵션
        is_notice = bool(request.form.get('is_notice')) if is_admin else False
        # 관리자만 보기: 누구나 설정 가능
        is_admin_only = bool(request.form.get('is_admin_only'))

        post = FeedbackPost(
            title=title,
            content=content,
            status=status or 'To do',
            is_notice=is_notice,
            is_admin_only=is_admin_only,
            created_by=current_user.id
        )
        db.session.add(post)
        db.session.commit()

        files = request.files.getlist('attachments')
        saved, errors = _save_feedback_attachments(post, files)
        if saved > 0:
            db.session.commit()
        if errors:
            for msg in errors[:3]:
                flash(msg, 'error')
            if len(errors) > 3:
                flash(f'첨부 오류가 {len(errors)}건 발생했습니다.', 'error')
        if saved > 0:
            flash(f'첨부 {saved}개가 업로드되었습니다.', 'success')

        flash('게시글이 등록되었습니다.', 'success')
        return redirect(url_for('main.feedback_detail', post_id=post.id))

    return render_template('main/feedback_form.html', post=None, is_admin=is_admin)


@bp.route('/feedback/<int:post_id>')
@login_required
def feedback_detail(post_id: int):
    """피드백 글 상세"""
    is_admin = _is_feedback_admin(current_user)
    post = FeedbackPost.query.options(
        joinedload(FeedbackPost.creator),
        selectinload(FeedbackPost.attachments)
    ).get_or_404(post_id)

    # 관리자만 보기 글은 관리자 또는 작성자만 접근 가능
    if post.is_admin_only and not is_admin and post.created_by != current_user.id:
        abort(403)

    # 조회수 증가(유저당 1회)
    try:
        db.session.add(FeedbackPostView(post_id=post.id, user_id=current_user.id))
        db.session.query(FeedbackPost).filter(FeedbackPost.id == post.id).update({
            FeedbackPost.view_count: db.func.coalesce(FeedbackPost.view_count, 0) + 1
        })
        db.session.commit()
        # 갱신된 값이 템플릿에 보이도록 리프레시
        try:
            db.session.refresh(post)
        except Exception:
            pass
    except IntegrityError:
        db.session.rollback()
    except Exception:
        db.session.rollback()

    can_edit = (post.created_by == current_user.id) or is_admin
    can_delete = (post.created_by == current_user.id) or is_admin

    return render_template(
        'main/feedback_detail.html',
        post=post,
        is_admin=is_admin,
        can_edit=can_edit,
        can_delete=can_delete
    )


@bp.route('/feedback/<int:post_id>/edit', methods=['GET', 'POST'])
@login_required
def feedback_edit(post_id: int):
    """피드백 글 수정 (작성자 또는 관리자)"""
    is_admin = _is_feedback_admin(current_user)
    post = FeedbackPost.query.options(selectinload(FeedbackPost.attachments)).get_or_404(post_id)

    if post.created_by != current_user.id and not is_admin:
        abort(403)

    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()
        content = (request.form.get('content') or '').strip()
        status = (request.form.get('status') or post.status or 'To do').strip()

        if not title:
            flash('제목을 입력하세요.', 'error')
            return render_template('main/feedback_form.html', post=post, is_admin=is_admin)
        if not content:
            flash('내용을 입력하세요.', 'error')
            return render_template('main/feedback_form.html', post=post, is_admin=is_admin)

        post.title = title
        post.content = content
        post.status = status or 'To do'

        # 관리자만 공지/관리자만보기 토글 가능
        if is_admin:
            post.is_notice = bool(request.form.get('is_notice'))
        # 관리자만 보기: 누구나 토글 가능
        post.is_admin_only = bool(request.form.get('is_admin_only'))

        files = request.files.getlist('attachments')
        saved, errors = _save_feedback_attachments(post, files)

        db.session.commit()

        if errors:
            for msg in errors[:3]:
                flash(msg, 'error')
            if len(errors) > 3:
                flash(f'첨부 오류가 {len(errors)}건 발생했습니다.', 'error')
        if saved > 0:
            flash(f'첨부 {saved}개가 업로드되었습니다.', 'success')

        flash('게시글이 수정되었습니다.', 'success')
        return redirect(url_for('main.feedback_detail', post_id=post.id))

    return render_template('main/feedback_form.html', post=post, is_admin=is_admin)


@bp.route('/feedback/<int:post_id>/delete', methods=['POST'])
@login_required
def feedback_delete(post_id: int):
    """피드백 글 삭제 (작성자 또는 관리자, 관리자는 전체 삭제 가능)"""
    is_admin = _is_feedback_admin(current_user)
    post = FeedbackPost.query.get_or_404(post_id)

    if post.created_by != current_user.id and not is_admin:
        abort(403)

    # 첨부 파일(디스크) 정리
    try:
        atts = FeedbackAttachment.query.filter_by(post_id=post.id).all()
        for a in atts:
            try:
                if a.file_path and os.path.exists(a.file_path):
                    os.remove(a.file_path)
            except Exception:
                pass
    except Exception:
        pass

    db.session.delete(post)
    db.session.commit()
    flash('게시글이 삭제되었습니다.', 'success')
    return redirect(url_for('main.feedback_list'))


@bp.route('/feedback/attachments/<int:attachment_id>')
@login_required
def feedback_attachment_file(attachment_id: int):
    """피드백 첨부 파일 보기/다운로드 (권한: 게시글 접근 권한과 동일)"""
    att = FeedbackAttachment.query.options(joinedload(FeedbackAttachment.post)).get_or_404(attachment_id)
    post = att.post
    if not post:
        abort(404)

    is_admin = _is_feedback_admin(current_user)
    if post.is_admin_only and not is_admin:
        abort(403)

    if not att.file_path or not os.path.exists(att.file_path):
        abort(404)

    # download=1이면 강제 다운로드, 아니면 브라우저 inline(이미지/영상 미리보기)
    download = request.args.get('download') in ('1', 'true', 'True')
    return send_file(
        att.file_path,
        as_attachment=download,
        download_name=att.original_name,
        mimetype=att.mime_type or None
    )


@bp.route('/feedback/attachments/<int:attachment_id>/delete', methods=['POST'])
@login_required
def feedback_attachment_delete(attachment_id: int):
    """피드백 첨부 삭제 (작성자 또는 관리자)"""
    att = FeedbackAttachment.query.options(joinedload(FeedbackAttachment.post)).get_or_404(attachment_id)
    post = att.post
    if not post:
        abort(404)

    is_admin = _is_feedback_admin(current_user)
    if post.is_admin_only and not is_admin:
        abort(403)
    if post.created_by != current_user.id and not is_admin:
        abort(403)

    # 파일 삭제
    try:
        if att.file_path and os.path.exists(att.file_path):
            os.remove(att.file_path)
    except Exception:
        pass

    db.session.delete(att)
    db.session.commit()
    flash('첨부가 삭제되었습니다.', 'success')
    return redirect(url_for('main.feedback_edit', post_id=post.id))


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
    
    # 모든 섹션을 한 번에 로드 (최적화)
    all_sections = Section.query.filter_by(project_id=project_id).order_by(Section.order_index).all()
    
    # 섹션을 딕셔너리로 변환 (빠른 조회)
    sections_dict = {s.id: s for s in all_sections}
    
    # 섹션 트리 구조 빌드 (메모리에서 처리)
    def build_section_tree(parent_id=None, depth=0):
        """섹션 트리를 메모리에서 빌드 (최대 4단계)"""
        if depth >= 4:
            return []
        
        children = [s for s in all_sections if s.parent_id == parent_id]
        
        for section in children:
            section.children = build_section_tree(section.id, depth + 1)
        
        return children
    
    sections = build_section_tree()
    
    # section_id가 없으면 케이스를 로드하지 않음 (최초 오픈 시 빈 화면)
    cases = []
    cases_by_section = {}
    
    if section_id:
        # Case 쿼리 빌드 (생성자, 수정자 정보 포함)
        query = Case.query.options(
            joinedload(Case.creator),
            joinedload(Case.updater),
            selectinload(Case.tags)  # N+1 태그 쿼리 방지
        ).filter_by(project_id=project_id, status='active')
        # 상위 섹션 클릭 시 하위 섹션의 케이스도 포함 (메모리에서 처리)
        def get_all_descendant_section_ids(parent_section_id):
            """메모리에서 재귀적으로 모든 하위 섹션 ID 수집"""
            section_ids = [parent_section_id]
            children = [s.id for s in all_sections if s.parent_id == parent_section_id]
            for child_id in children:
                section_ids.extend(get_all_descendant_section_ids(child_id))
            return section_ids
        
        all_section_ids = get_all_descendant_section_ids(section_id)
        query = query.filter(Case.section_id.in_(all_section_ids))
        
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
        
        # 선택된 섹션과 모든 하위 섹션의 케이스 그룹화 (메모리에서 처리)
        def get_all_descendant_sections(parent_section_id):
            """메모리에서 재귀적으로 모든 하위 섹션 수집"""
            sections_list = [sections_dict.get(parent_section_id)]
            children = [s for s in all_sections if s.parent_id == parent_section_id]
            for child in children:
                sections_list.extend(get_all_descendant_sections(child.id))
            return sections_list
        
        descendant_sections = get_all_descendant_sections(section_id)
        for sec in descendant_sections:
            if sec:
                section_cases = [c for c in cases if c.section_id == sec.id]
                if section_cases:
                    cases_by_section[sec.id] = {
                        'section': sec,
                        'cases': section_cases
                    }
    
    # 프로젝트의 모든 태그
    tags = Tag.query.filter_by(project_id=project_id).order_by(Tag.name).all()
    
    return render_template('main/cases.html',
                         project=project,
                         sections=sections,
                         cases=cases,
                         cases_by_section=cases_by_section,
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


@bp.route('/p/<int:project_id>/runs/<int:run_id>')
@login_required
def run_execute(project_id, run_id):
    """런 실행 화면 (핫키 지원)"""
    project = Project.query.get_or_404(project_id)
    run = Run.query.get_or_404(run_id)
    
    # 런이 해당 프로젝트에 속하는지 확인
    if run.project_id != project_id:
        abort(404)
    
    # RunCase 목록
    run_cases = run.run_cases.order_by('order_index').all()

    # Phase 1: 코멘트(status='comment')는 Result로 별도 저장되므로, 사이드바 프리뷰용으로
    # 케이스별 최신 코멘트를 미리 로드한다 (1쿼리).
    latest_comment_result_by_case_id = {}
    comment_results = Result.query.filter_by(run_id=run_id, status='comment') \
        .order_by(Result.created_at.desc()).all()
    for cr in comment_results:
        if cr.case_id not in latest_comment_result_by_case_id:
            latest_comment_result_by_case_id[cr.case_id] = cr
    
    # 케이스 Jira/미디어 사전 로드(1쿼리씩)
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

    # 각 RunCase의 최신 결과 가져오기 (JSON 직렬화 가능하도록 딕셔너리로 변환)
    # Phase 1: 런 상태에 따라 스냅샷/현재 데이터 구분
    run_cases_with_results = []
    for rc in run_cases:
        result = rc.get_latest_result()
        
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
            # 진행 중인 런: 현재 데이터 사용 (편의성)
            case_title = rc.case.title
            case_steps = rc.case.steps
            case_expected = rc.case.expected_result
            case_priority = rc.case.priority
            case_version = rc.case.version or 1
        
        # 사이드바 코멘트 프리뷰: 실행 결과 코멘트 vs 코멘트 전용 결과 중 "가장 최신의 non-empty 코멘트" 선택
        sidebar_comment = ''
        sidebar_comment_candidates = []
        if result and result.comment and str(result.comment).strip():
            sidebar_comment_candidates.append((result.created_at, result.comment))
        latest_comment_result = latest_comment_result_by_case_id.get(rc.case_id)
        if latest_comment_result and latest_comment_result.comment and str(latest_comment_result.comment).strip():
            sidebar_comment_candidates.append((latest_comment_result.created_at, latest_comment_result.comment))
        if sidebar_comment_candidates:
            sidebar_comment = max(sidebar_comment_candidates, key=lambda x: x[0])[1]

        run_cases_with_results.append({
            'run_case': {
                'id': rc.id,
                'run_id': rc.run_id,
                'case_id': rc.case_id,
                'order_index': rc.order_index
            },
            'case': {
                'id': rc.case.id,
                'section_path': rc.case.section.get_full_path() if getattr(rc.case, 'section', None) else None,
                'title': case_title,
                'steps': case_steps or '',
                'expected': case_expected or '',
                'priority': case_priority,
                'version': case_version,
                'jira_links': jira_map.get(rc.case_id, []) if not run.is_closed else ((rc.jira_links_snapshot or '').split(' | ') if rc.jira_links_snapshot else jira_map.get(rc.case_id, [])),
                'media': media_map.get(rc.case_id, []) if not run.is_closed else media_map.get(rc.case_id, []),
                'jira_links_snapshot': rc.jira_links_snapshot or '',
                'media_names_snapshot': rc.media_names_snapshot or '',
                'created_at': rc.case.created_at.isoformat() if rc.case.created_at else None,
                'created_by': rc.case.creator.name if rc.case.creator else None,
                'updated_at': rc.case.updated_at.isoformat() if rc.case.updated_at else None,
                'updated_by': rc.case.updater.name if rc.case.updater else None
            },
            'result': {
                'id': result.id,
                'status': result.status,
                'comment': result.comment or '',
                'bug_links': result.bug_links or '',  # Phase 1: 버그 링크
                'executor': result.executor.name,
                'created_at': result.created_at.isoformat()
            } if result else None,
            'sidebar_comment': sidebar_comment
        })
    
    # 통계
    stats = run.get_stats()
    
    return render_template('main/run_execute.html',
                         project=project,
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
    """회원 관리 (Super Admin 전용)"""
    if not current_user.is_super_admin():
        flash('Super Admin만 접근할 수 있습니다.', 'error')
        return redirect(url_for('main.projects'))
    
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('main/manage_users.html', users=users)


@bp.route('/profile')
@login_required
def profile():
    """계정 정보"""
    return render_template('main/profile.html')


@bp.route('/settings')
@login_required
def settings():
    """설정 페이지 (모든 사용자 접근 가능, 편집은 Super Admin/Admin만)"""
    # 모든 프롬프트 조회
    prompts = TranslationPrompt.query.order_by(TranslationPrompt.updated_at.desc()).all()
    
    # 활성 프롬프트 조회
    active_prompt = TranslationPrompt.query.filter_by(is_active=True).first()
    
    # 모든 요약 프롬프트 조회
    from app.models import SummaryPrompt
    summary_prompts = SummaryPrompt.query.order_by(SummaryPrompt.updated_at.desc()).all()
    
    # 활성 요약 프롬프트 조회
    active_summary_prompt = SummaryPrompt.query.filter_by(is_active=True).first()
    
    return render_template('main/settings.html', 
                         prompts=prompts, 
                         active_prompt=active_prompt,
                         summary_prompts=summary_prompts,
                         active_summary_prompt=active_summary_prompt)


@bp.route('/advanced-settings')
@login_required
def advanced_settings():
    """고급 설정 페이지 (Super Admin만 접근 가능)"""
    if not current_user.is_admin():
        abort(403)
    
    # API 키 조회
    api_keys = APIKey.query.order_by(APIKey.updated_at.desc()).all()
    active_api_key = APIKey.query.filter_by(is_active=True).first()
    
    return render_template('main/advanced_settings.html',
                         api_keys=api_keys,
                         active_api_key=active_api_key)


