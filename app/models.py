from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db


class User(UserMixin, db.Model):
    """사용자 모델"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='runner')  # admin, author, runner
    is_active = db.Column(db.Boolean, default=True, nullable=False)  # 계정 활성화 여부
    avatar_filename = db.Column(db.String(300), nullable=True)  # 프로필 이미지(uploads/avatars/<filename>)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    created_runs = db.relationship('Run', backref='creator', lazy='dynamic', foreign_keys='Run.created_by')
    executed_results = db.relationship('Result', backref='executor', lazy='dynamic')
    owned_cases = db.relationship('Case', backref='owner', lazy='dynamic', foreign_keys='Case.owner_id')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_admin(self):
        """관리자 권한 체크 (admin@pubg.com 또는 role='admin')"""
        return self.email == 'admin@pubg.com' or self.role == 'admin'
    
    def is_super_admin(self):
        """슈퍼 관리자 권한 체크 (admin@pubg.com만)"""
        return self.email == 'admin@pubg.com'
    
    def __repr__(self):
        return f'<User {self.email}>'


class ActivityLog(db.Model):
    """사용자 활동 로그"""
    __tablename__ = 'activity_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    action = db.Column(db.String(80), nullable=False, index=True)  # e.g. project.create, case.update, run.result
    entity_type = db.Column(db.String(80), nullable=True, index=True)  # e.g. project/case/run/result
    entity_id = db.Column(db.Integer, nullable=True, index=True)
    project_id = db.Column(db.Integer, nullable=True, index=True)

    description = db.Column(db.Text, nullable=True)
    meta_json = db.Column(db.Text, nullable=True)  # JSON string

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship('User', backref=db.backref('activity_logs', lazy='dynamic'))

    def __repr__(self):
        return f'<ActivityLog {self.user_id} {self.action}>'


class Project(db.Model):
    """프로젝트 모델"""
    __tablename__ = 'projects'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    sections = db.relationship('Section', backref='project', lazy='dynamic', cascade='all, delete-orphan')
    cases = db.relationship('Case', backref='project', lazy='dynamic', cascade='all, delete-orphan')
    tags = db.relationship('Tag', backref='project', lazy='dynamic', cascade='all, delete-orphan')
    runs = db.relationship('Run', backref='project', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Project {self.name}>'


class Section(db.Model):
    """섹션(트리 구조) 모델"""
    __tablename__ = 'sections'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('sections.id'), nullable=True, index=True)
    name = db.Column(db.String(200), nullable=False)
    order_index = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Self-referential relationship for tree structure
    children = db.relationship('Section', backref=db.backref('parent', remote_side=[id]), lazy='dynamic')
    cases = db.relationship('Case', backref='section', lazy='dynamic')
    
    def get_full_path(self):
        """섹션의 전체 경로 반환 (예: 'Parent > Child > Current')"""
        path = [self.name]
        current = self
        while current.parent:
            current = current.parent
            path.insert(0, current.name)
        return ' > '.join(path)
    
    def __repr__(self):
        return f'<Section {self.name}>'


class Case(db.Model):
    """테스트 케이스 모델"""
    __tablename__ = 'cases'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False, index=True)
    section_id = db.Column(db.Integer, db.ForeignKey('sections.id'), nullable=False, index=True)
    title = db.Column(db.String(500), nullable=False)
    steps = db.Column(db.Text)
    expected_result = db.Column(db.Text)
    priority = db.Column(db.String(10), default='Medium')  # Critical, High, Medium, Low
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    status = db.Column(db.String(20), default='active')  # active, archived
    order_index = db.Column(db.Integer, default=0)  # 섹션 내 순서
    version = db.Column(db.Integer, default=1, nullable=False)  # Phase 1: 케이스 버전 추적
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # 생성자
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # 수정자
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    # NOTE: 이전에는 lazy='dynamic'이라 템플릿에서 case.tags 접근 시 케이스마다 별도 SELECT가 발생(N+1).
    # selectin은 "케이스들 먼저 로드 -> tags를 IN (...)로 한 번 더 로드" 방식이라 케이스 수가 늘어도 빠름.
    tags = db.relationship(
        'Tag',
        secondary='case_tags',
        backref=db.backref('cases', lazy='selectin'),
        lazy='selectin'
    )
    run_cases = db.relationship('RunCase', backref='case', lazy='dynamic')
    results = db.relationship('Result', backref='case', lazy='dynamic')
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_cases')
    updater = db.relationship('User', foreign_keys=[updated_by], backref='updated_cases')
    
    def __repr__(self):
        return f'<Case {self.title}>'


class CaseJiraLink(db.Model):
    """케이스별 Jira 링크(여러개)"""
    __tablename__ = 'case_jira_links'

    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('cases.id', ondelete='CASCADE'), nullable=False, index=True)
    url = db.Column(db.String(800), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    case = db.relationship('Case', backref=db.backref('jira_links', lazy='dynamic', cascade='all, delete-orphan'))


class CaseMedia(db.Model):
    """케이스별 미디어(이미지/영상)"""
    __tablename__ = 'case_media'

    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('cases.id', ondelete='CASCADE'), nullable=False, index=True)
    file_path = db.Column(db.String(500), nullable=False)
    original_name = db.Column(db.String(300), nullable=False)
    mime_type = db.Column(db.String(100), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    case = db.relationship('Case', backref=db.backref('media', lazy='dynamic', cascade='all, delete-orphan'))


class CaseTranslation(db.Model):
    """케이스 번역 모델"""
    __tablename__ = 'case_translations'
    
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('cases.id', ondelete='CASCADE'), nullable=False, index=True)
    source_lang = db.Column(db.String(10), nullable=False)  # 'ko', 'en'
    target_lang = db.Column(db.String(10), nullable=False)  # 'ko', 'en'
    title = db.Column(db.String(500))
    steps = db.Column(db.Text)
    expected_result = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Unique constraint: one translation per case per target language
    __table_args__ = (
        db.UniqueConstraint('case_id', 'target_lang', name='uq_case_target_lang'),
    )
    
    # Relationship
    case = db.relationship('Case', backref='translations')
    
    def __repr__(self):
        return f'<CaseTranslation {self.case_id} -> {self.target_lang}>'


class TranslationPrompt(db.Model):
    """번역 프롬프트 설정 모델"""
    __tablename__ = 'translation_prompts'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)  # 'default', 'custom', etc.
    system_prompt = db.Column(db.Text, nullable=False)  # 시스템 프롬프트
    user_prompt_template = db.Column(db.Text, nullable=False)  # 사용자 프롬프트 템플릿
    model = db.Column(db.String(50), default='gpt-3.5-turbo')  # 사용할 OpenAI 모델
    is_active = db.Column(db.Boolean, default=False)  # 활성화 여부
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<TranslationPrompt {self.name}>'


class SummaryPrompt(db.Model):
    """요약 프롬프트 설정 모델"""
    __tablename__ = 'summary_prompts'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)  # 'default', 'custom', etc.
    system_prompt = db.Column(db.Text, nullable=False)  # 시스템 프롬프트
    user_prompt_template = db.Column(db.Text, nullable=False)  # 사용자 프롬프트 템플릿
    model = db.Column(db.String(50), default='gpt-3.5-turbo')  # 사용할 OpenAI 모델
    is_active = db.Column(db.Boolean, default=False)  # 활성화 여부
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<SummaryPrompt {self.name}>'


class APIKey(db.Model):
    """OpenAI API 키 관리 모델"""
    __tablename__ = 'api_keys'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # 키 이름 (예: Production, Test)
    api_key = db.Column(db.String(500), nullable=False)  # 암호화된 API 키
    is_active = db.Column(db.Boolean, default=False)  # 활성화 여부
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_used_at = db.Column(db.DateTime, nullable=True)  # 마지막 사용 시간
    
    def __repr__(self):
        return f'<APIKey {self.name}>'


class JiraConfig(db.Model):
    """Jira 원버튼 등록 설정 (프로젝트 공통, 싱글톤 사용 권장)"""
    __tablename__ = 'jira_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    
    enabled = db.Column(db.Boolean, default=False)
    
    # Jira Cloud 기본 설정
    base_url = db.Column(db.String(300))  # 예: https://your-domain.atlassian.net
    email = db.Column(db.String(200))
    api_token = db.Column(db.String(500))  # Jira API Token
    
    # 기본 생성 대상
    project_key = db.Column(db.String(50))
    issue_type = db.Column(db.String(100), default='Bug')
    
    # 기본값(프론트 원버튼에 사용)
    default_components = db.Column(db.String(500))  # "UI,Matchmaking" (쉼표 구분)
    default_labels = db.Column(db.String(500))  # "quickrail,automation" (쉼표 구분)
    default_priority = db.Column(db.String(100))  # 예: "High"
    
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<JiraConfig enabled={self.enabled} project={self.project_key}>'


class TranslationUsage(db.Model):
    """번역 API 사용량 추적 모델"""
    __tablename__ = 'translation_usage'
    
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey('cases.id'), nullable=True)  # 관련 케이스 (선택)
    source_lang = db.Column(db.String(10), nullable=False)  # 원본 언어
    target_lang = db.Column(db.String(10), nullable=False)  # 대상 언어
    input_tokens = db.Column(db.Integer, default=0)  # 입력 토큰 수
    output_tokens = db.Column(db.Integer, default=0)  # 출력 토큰 수
    total_tokens = db.Column(db.Integer, default=0)  # 총 토큰 수
    model = db.Column(db.String(50), default='gpt-3.5-turbo')  # 사용된 모델
    cost = db.Column(db.Float, default=0.0)  # 예상 비용 (USD)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # 요청한 사용자
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<TranslationUsage {self.id} - {self.total_tokens} tokens>'


class Tag(db.Model):
    """태그 모델"""
    __tablename__ = 'tags'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    
    # Unique constraint: tag name per project
    __table_args__ = (
        db.UniqueConstraint('project_id', 'name', name='uq_project_tag'),
    )
    
    def __repr__(self):
        return f'<Tag {self.name}>'


class CaseTag(db.Model):
    """케이스-태그 다대다 관계"""
    __tablename__ = 'case_tags'
    
    case_id = db.Column(db.Integer, db.ForeignKey('cases.id'), primary_key=True)
    tag_id = db.Column(db.Integer, db.ForeignKey('tags.id'), primary_key=True)


class Run(db.Model):
    """테스트 런 모델"""
    __tablename__ = 'runs'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    build_label = db.Column(db.String(100))  # Phase 1: 빌드 라벨 (예: 1.3.0-rc1)
    summary = db.Column(db.Text)  # AI 요약
    summary_prompt_id = db.Column(db.Integer, db.ForeignKey('summary_prompts.id'), nullable=True)  # 사용된 요약 프롬프트
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    run_type = db.Column(db.String(50))  # smoke, regression, hotfix, custom
    language = db.Column(db.String(10), default='original')  # original, ko, en
    is_closed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    run_cases = db.relationship('RunCase', backref='run', lazy='dynamic', cascade='all, delete-orphan')
    results = db.relationship('Result', backref='run', lazy='dynamic', cascade='all, delete-orphan')
    
    def get_stats(self):
        """런의 통계 반환 (각 케이스당 최신 결과만 카운트)"""
        results = {}
        executed_count = 0
        
        # 각 RunCase의 최신 결과만 카운트
        for run_case in self.run_cases:
            latest_result = run_case.get_latest_result()
            if latest_result:
                status = latest_result.status
                results[status] = results.get(status, 0) + 1
                executed_count += 1
        
        total = self.run_cases.count()
        passed = results.get('pass', 0)
        
        return {
            'total': total,
            'executed': executed_count,
            'pending': total - executed_count,
            'pass': passed,
            'fail': results.get('fail', 0),
            'blocked': results.get('blocked', 0),
            'retest': results.get('retest', 0),
            'na': results.get('na', 0),
            'pass_rate': round(passed / executed_count * 100, 1) if executed_count > 0 else 0,
            'progress': round(executed_count / total * 100, 1) if total > 0 else 0
        }
    
    def __repr__(self):
        return f'<Run {self.name}>'


class RunCase(db.Model):
    """런에 포함된 케이스 스냅샷"""
    __tablename__ = 'run_cases'
    
    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey('runs.id'), nullable=False, index=True)
    case_id = db.Column(db.Integer, db.ForeignKey('cases.id'), nullable=False, index=True)
    order_index = db.Column(db.Integer, default=0)
    # Phase 1: 런에 포함된 시점의 케이스 버전 및 내용 스냅샷
    case_version_snapshot = db.Column(db.Integer)  # 케이스 버전
    title_snapshot = db.Column(db.String(500))  # 제목 스냅샷
    steps_snapshot = db.Column(db.Text)  # 단계 스냅샷
    expected_result_snapshot = db.Column(db.Text)  # 예상 결과 스냅샷
    priority_snapshot = db.Column(db.String(10))  # 우선순위 스냅샷 (Phase 1 수정)
    jira_links_snapshot = db.Column(db.Text)  # 케이스 Jira 링크 스냅샷(쉼표/개행)
    media_names_snapshot = db.Column(db.Text)  # 케이스 미디어 파일명 스냅샷(쉼표/개행)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def get_latest_result(self):
        """이 런케이스의 최신 '실행 결과' 반환 (코멘트 전용 결과(status='comment') 제외)

        주의:
        - 코멘트는 Phase 1에서 Result(status='comment')로 별도 저장되므로,
          실행 상태(pass/fail/...)를 덮어쓰지 않도록 여기서는 제외한다.
        """
        return Result.query.filter(
            Result.run_id == self.run_id,
            Result.case_id == self.case_id,
            Result.status.notin_(['comment', 'artifact'])
        ).order_by(Result.created_at.desc()).first()
    
    def __repr__(self):
        return f'<RunCase run_id={self.run_id} case_id={self.case_id}>'


class Result(db.Model):
    """테스트 실행 결과 모델"""
    __tablename__ = 'results'
    
    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey('runs.id'), nullable=False, index=True)
    case_id = db.Column(db.Integer, db.ForeignKey('cases.id'), nullable=False, index=True)
    executor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False)  # pass, fail, blocked, retest, na, skipped, notrun
    comment = db.Column(db.Text)
    bug_links = db.Column(db.Text)  # Phase 1: 버그 링크 (JSON 배열 또는 쉼표 구분 문자열)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    attachments = db.relationship('Attachment', backref='result', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Result {self.status} for case_id={self.case_id}>'


class Attachment(db.Model):
    """첨부파일 모델"""
    __tablename__ = 'attachments'
    
    id = db.Column(db.Integer, primary_key=True)
    result_id = db.Column(db.Integer, db.ForeignKey('results.id'), nullable=False, index=True)
    file_path = db.Column(db.String(500), nullable=False)
    original_name = db.Column(db.String(300), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Attachment {self.original_name}>'


class AuditLog(db.Model):
    """감사 로그 모델 (Phase 2)"""
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(50), nullable=False)  # case, section, run
    entity_id = db.Column(db.Integer, nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(50), nullable=False)  # create, update, delete, move, archive
    diff_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    actor = db.relationship('User', backref='audit_logs')
    
    def __repr__(self):
        return f'<AuditLog {self.action} {self.entity_type}:{self.entity_id}>'


class RunTemplate(db.Model):
    """런 템플릿 모델 (Phase 2)"""
    __tablename__ = 'run_templates'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # 필터 조건 저장 (JSON)
    filter_json = db.Column(db.Text)  # section_ids, tag_names, priorities, etc.
    
    # 또는 직접 케이스 ID 저장
    case_ids = db.Column(db.Text)  # comma-separated case IDs
    
    run_type = db.Column(db.String(50))  # smoke, regression, hotfix, custom
    is_public = db.Column(db.Boolean, default=True)  # 팀 전체 공유 여부
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    project = db.relationship('Project', backref='run_templates')
    creator = db.relationship('User', backref='created_templates', foreign_keys=[created_by])
    
    def __repr__(self):
        return f'<RunTemplate {self.name}>'


class FeedbackPost(db.Model):
    """피드백/공지 게시글 모델"""
    __tablename__ = 'feedback_posts'

    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(300), nullable=False)
    content = db.Column(db.Text, nullable=False)

    # Jira 스타일 상태값 (To do, In progress, Done, Won't do ...)
    status = db.Column(db.String(30), nullable=False, default='To do', index=True)

    # 공지/고정
    is_notice = db.Column(db.Boolean, nullable=False, default=False, index=True)

    # 관리자만 보기 (admin/super admin)
    is_admin_only = db.Column(db.Boolean, nullable=False, default=False, index=True)

    # 조회수(유저당 1회 집계)
    view_count = db.Column(db.Integer, nullable=False, default=0, index=True)

    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    creator = db.relationship('User', foreign_keys=[created_by], backref=db.backref('feedback_posts', lazy='dynamic'))
    attachments = db.relationship(
        'FeedbackAttachment',
        backref='post',
        lazy='selectin',
        cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f'<FeedbackPost {self.id} {self.title}>'


class FeedbackAttachment(db.Model):
    """피드백/공지 첨부파일(이미지/영상 등)"""
    __tablename__ = 'feedback_attachments'

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('feedback_posts.id', ondelete='CASCADE'), nullable=False, index=True)

    file_path = db.Column(db.String(600), nullable=False)  # absolute path
    original_name = db.Column(db.String(300), nullable=False)
    mime_type = db.Column(db.String(120), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)

    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    uploader = db.relationship('User', foreign_keys=[uploaded_by], backref=db.backref('feedback_attachments', lazy='dynamic'))

    def __repr__(self):
        return f'<FeedbackAttachment {self.id} {self.original_name}>'


class FeedbackPostView(db.Model):
    """피드백 게시글 조회 기록(유저당 1회 집계용)"""
    __tablename__ = 'feedback_post_views'

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('feedback_posts.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        db.UniqueConstraint('post_id', 'user_id', name='uq_feedback_post_view_post_user'),
    )

    post = db.relationship('FeedbackPost', backref=db.backref('views', lazy='dynamic'))
    user = db.relationship('User', backref=db.backref('feedback_post_views', lazy='dynamic'))

    def __repr__(self):
        return f'<FeedbackPostView post={self.post_id} user={self.user_id}>'


