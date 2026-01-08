#!/usr/bin/env python
"""
/p/4 (Quickrail Phase1) 전체 케이스로 런 생성 -> 전부 PASS 기록 -> 런 완료 처리

주의:
- DB는 instance/quickrail.db 기준(기본 config normalize)
- 결과 기록은 'pass'로 일괄 생성
"""

from __future__ import annotations

from datetime import datetime

from app import create_app, db
from app.models import Project, Case, Run, RunCase, Result


PROJECT_ID = 4
RUN_NAME = f"Phase1 자동 런 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"


def main() -> None:
    app = create_app("production")
    with app.app_context():
        project = Project.query.get(PROJECT_ID)
        if not project:
            raise RuntimeError(f"프로젝트를 찾을 수 없습니다: {PROJECT_ID}")

        # executor: 가장 먼저 존재하는 유저(혹은 admin)
        from app.models import User

        executor = User.query.filter_by(email="admin@quickrail.com").first() or User.query.first()
        if not executor:
            raise RuntimeError("유저가 없습니다. 먼저 유저를 생성하세요.")

        # 프로젝트의 active 케이스 전체
        cases = Case.query.filter_by(project_id=PROJECT_ID, status="active").order_by(Case.section_id, Case.order_index).all()
        if not cases:
            raise RuntimeError("케이스가 없습니다.")

        run = Run(
            project_id=PROJECT_ID,
            name=RUN_NAME,
            run_type="custom",
            build_label="phase1",
            created_by=executor.id,
            is_closed=False,
            language="original",
        )
        db.session.add(run)
        db.session.flush()

        # RunCase 생성 (기본 스냅샷도 채워줌: close 시 업데이트되긴 하지만, 생성 시점 스냅샷도 유의미)
        for idx, c in enumerate(cases, start=1):
            rc = RunCase(
                run_id=run.id,
                case_id=c.id,
                order_index=idx,
                case_version_snapshot=c.version or 1,
                title_snapshot=c.title,
                steps_snapshot=c.steps,
                expected_result_snapshot=c.expected_result,
                priority_snapshot=c.priority,
            )
            db.session.add(rc)
        db.session.flush()

        # 결과 PASS 기록
        for c in cases:
            db.session.add(
                Result(
                    run_id=run.id,
                    case_id=c.id,
                    status="pass",
                    comment="phase1 자동 실행: PASS",
                    bug_links="",
                    executor_id=executor.id,
                    created_at=datetime.utcnow(),
                )
            )
        db.session.flush()

        # 런 완료 처리 + 스냅샷 갱신
        run.is_closed = True
        run.closed_at = datetime.utcnow()
        db.session.commit()

        print(f"[DONE] Run created & closed: run_id={run.id} name={run.name}")
        print(f"확인 URL: http://127.0.0.1:5000/p/{PROJECT_ID}/runs/{run.id}")


if __name__ == "__main__":
    main()


