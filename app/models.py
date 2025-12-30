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
    
    def __repr__(self):
        return f'<User {self.email}>'


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
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # 생성자
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # 수정자
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    tags = db.relationship('Tag', secondary='case_tags', backref='cases', lazy='dynamic')
    run_cases = db.relationship('RunCase', backref='case', lazy='dynamic')
    results = db.relationship('Result', backref='case', lazy='dynamic')
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_cases')
    updater = db.relationship('User', foreign_keys=[updated_by], backref='updated_cases')
    
    def __repr__(self):
        return f'<Case {self.title}>'


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
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    run_type = db.Column(db.String(50))  # smoke, regression, hotfix, custom
    is_closed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    run_cases = db.relationship('RunCase', backref='run', lazy='dynamic', cascade='all, delete-orphan')
    results = db.relationship('Result', backref='run', lazy='dynamic', cascade='all, delete-orphan')
    
    def get_stats(self):
        """런의 통계 반환"""
        results = {}
        for result in self.results:
            status = result.status
            results[status] = results.get(status, 0) + 1
        
        total = self.run_cases.count()
        executed = sum(results.values())
        passed = results.get('pass', 0)
        
        return {
            'total': total,
            'executed': executed,
            'pending': total - executed,
            'pass': passed,
            'fail': results.get('fail', 0),
            'blocked': results.get('blocked', 0),
            'retest': results.get('retest', 0),
            'na': results.get('na', 0),
            'pass_rate': round(passed / executed * 100, 1) if executed > 0 else 0,
            'progress': round(executed / total * 100, 1) if total > 0 else 0
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def get_latest_result(self):
        """이 런케이스의 최신 결과 반환"""
        return Result.query.filter_by(
            run_id=self.run_id,
            case_id=self.case_id
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
    status = db.Column(db.String(20), nullable=False)  # pass, fail, blocked, retest, na
    comment = db.Column(db.Text)
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


