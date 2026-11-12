import argparse
import json
import uuid

from sqlalchemy import select

from app.core.errors import BusinessError
from app.core.security import SYNC_ACTOR_ID, seed_dev_users
from app.db import AuthIdentity, SessionLocal, User, init_db
from app.domain import Role
from app.services.common import conditional_update, fail, mutate, record_change, snapshot


def provision(db, actor, issuer, subject, name, role, department):
    if not issuer.startswith("https://") or not 1 <= len(issuer) <= 500 or not 1 <= len(subject) <= 150:
        fail(400, "INVALID_IDENTITY", "Issuer或subject不符合约束")
    if not 1 <= len(name.strip()) <= 100 or not 1 <= len(department.strip()) <= 100:
        fail(400, "INVALID_USER", "姓名/部门不符合约束")
    role = Role(role)
    existing = db.scalar(select(AuthIdentity).where(AuthIdentity.issuer == issuer, AuthIdentity.subject == subject))
    if existing:
        user = db.get(User, existing.user_id)
        if not existing.active or existing.deleted_at or user is None or (user.display_name, user.role, user.department, user.active) != (name, role.value, department, True):
            fail(409, "IDENTITY_EXISTS", "身份已配置且状态/权限不同；不会自动变更权限")
        return {"user_id": user.id, "identity_id": existing.id, "version": existing.version}
    user = User(display_name=name, role=role.value, department=department, active=True)
    db.add(user)
    record_change(db, user, actor, "provision_sso_user", reason="服务器操作员显式配置")
    identity = AuthIdentity(issuer=issuer, subject=subject, user_id=user.id)
    db.add(identity)
    record_change(db, identity, actor, "provision_sso_identity", reason="服务器操作员显式配置")
    return {"user_id": user.id, "identity_id": identity.id, "version": identity.version}


def revoke(db, actor, identity_id, version, reason):
    row = db.get(AuthIdentity, identity_id)
    if row is None:
        fail(404, "NOT_FOUND", "身份映射不存在")
    if not row.active or not reason.strip():
        fail(409, "INVALID_STATE", "身份已停用或未提供依据")
    before = snapshot(row)
    conditional_update(db, row, version, {"active": False})
    record_change(db, row, actor, "revoke_sso_identity", before, reason)
    return {"identity_id": row.id, "version": row.version, "active": False}


def main():
    parser = argparse.ArgumentParser(description="Explicit SSO authorization; never accepts roles from JWT")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("provision")
    for flag in ("issuer", "subject", "name", "department"):
        add.add_argument("--" + flag, required=True)
    add.add_argument("--role", required=True, choices=[r.value for r in Role])
    remove = sub.add_parser("revoke")
    remove.add_argument("--identity-id", required=True)
    remove.add_argument("--version", type=int, required=True)
    remove.add_argument("--reason", required=True)
    for command in (add, remove):
        command.add_argument("--key", default=None)
    args = vars(parser.parse_args())
    key, operation = args.pop("key") or uuid.uuid4().hex, args.pop("command")
    init_db()
    seed_dev_users()
    with SessionLocal() as db:
        actor = db.get(User, SYNC_ACTOR_ID)
        assert actor is not None, "System actor missing"
        result = mutate(db, actor, "operator_" + operation, key, args,
            lambda: provision(db, actor, **args) if operation == "provision" else revoke(db, actor, **args))
        print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except (BusinessError, ValueError) as exc:
        print(exc.code if isinstance(exc, BusinessError) else "INVALID_CONFIGURATION")
        raise SystemExit(2) from None
