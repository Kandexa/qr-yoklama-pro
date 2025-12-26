from alembic import op
import sqlalchemy as sa

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=True),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_role", "users", ["role"], unique=False)

    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_courses_teacher_id", "courses", ["teacher_id"], unique=False)
    op.create_index("ix_courses_name", "courses", ["name"], unique=False)

    op.create_table(
        "attendance_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_code", sa.String(length=16), nullable=False),
        sa.Column("started_at_utc", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("ends_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_min", sa.Integer(), nullable=False),
        sa.Column("late_after_min", sa.Integer(), nullable=False),
        sa.Column("is_closed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("current_key", sa.String(length=64), nullable=False),
        sa.Column("key_expires_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_attendance_sessions_course_id", "attendance_sessions", ["course_id"], unique=False)
    op.create_index("ix_attendance_sessions_session_code", "attendance_sessions", ["session_code"], unique=True)
    op.create_index("ix_attendance_sessions_current_key", "attendance_sessions", ["current_key"], unique=False)
    op.create_index("ix_attendance_sessions_ends_at_utc", "attendance_sessions", ["ends_at_utc"], unique=False)

    op.create_table(
        "checkins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("attendance_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("checked_in_at_utc", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.UniqueConstraint("session_id", "student_id", name="uq_checkin_student_once"),
        sa.UniqueConstraint("session_id", "device_id", name="uq_checkin_one_student_per_device"),
    )
    op.create_index("ix_checkins_session_id", "checkins", ["session_id"], unique=False)
    op.create_index("ix_checkins_student_id", "checkins", ["student_id"], unique=False)
    op.create_index("ix_checkins_device_id", "checkins", ["device_id"], unique=False)
    op.create_index("ix_checkins_status", "checkins", ["status"], unique=False)

def downgrade():
    op.drop_table("checkins")
    op.drop_table("attendance_sessions")
    op.drop_table("courses")
    op.drop_table("users")
