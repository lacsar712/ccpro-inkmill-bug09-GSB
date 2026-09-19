from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models.grind_pass import GrindPass
from app.models.mill import Mill
from app.serializers import grind_pass_json
from app.utils import error, normalize_datetime

bp = Blueprint("grind_passes", __name__, url_prefix="/api/grind-passes")


def _validate(db, body: dict) -> tuple[dict, str | None]:
    """Validate and coerce a grind pass payload before any row is written.

    Returns (values, None) on success or (None, message) on failure.
    """
    raw_mill_id = body.get("millId")
    try:
        mill_id = int(raw_mill_id)
    except (TypeError, ValueError):
        return None, "请选择研磨机"
    if mill_id <= 0 or not db.get(Mill, mill_id):
        return None, "请选择研磨机"

    raw_started_at = str(body.get("startedAt") or "").strip()
    if not raw_started_at:
        return None, "开始时间不能为空"
    started_at = normalize_datetime(raw_started_at, strict=True)
    if started_at is None:
        return None, "开始时间格式无效"

    try:
        pass_no = int(body.get("passNo"))
    except (TypeError, ValueError):
        return None, "遍次编号必须为 ≥ 1 的整数"
    if pass_no < 1:
        return None, "遍次编号必须 ≥ 1"

    if body.get("durationMin") is None or str(body.get("durationMin")).strip() == "":
        return None, "研磨时长(分钟)必须大于 0"
    try:
        duration = Decimal(str(body.get("durationMin")))
    except (InvalidOperation, ValueError):
        return None, "研磨时长(分钟)必须大于 0"
    if not duration.is_finite() or duration <= 0:
        return None, "研磨时长(分钟)必须大于 0"
    if duration > Decimal("999999.99"):
        return None, "研磨时长(分钟)数值过大"

    media_type = str(body.get("mediaType") or "").strip()
    if not media_type:
        return None, "研磨介质不能为空"
    if len(media_type) > 64:
        return None, "研磨介质名称不能超过 64 个字符"

    operator_name = str(body.get("operatorName") or "").strip()
    if not operator_name:
        return None, "操作员不能为空"
    if len(operator_name) > 128:
        return None, "操作员姓名不能超过 128 个字符"

    return {
        "mill_id": mill_id,
        "started_at": started_at,
        "pass_no": pass_no,
        "duration_min": duration,
        "media_type": media_type,
        "operator_name": operator_name,
    }, None


@bp.get("")
@jwt_required()
def list_passes():
    db = SessionLocal()
    try:
        rows = (
            db.query(GrindPass)
            .order_by(GrindPass.started_at.desc(), GrindPass.id.desc())
            .all()
        )
        return jsonify([grind_pass_json(r) for r in rows])
    finally:
        db.close()


@bp.post("")
@jwt_required()
def create_pass():
    body = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        values, msg = _validate(db, body)
        if msg:
            return error(msg, 400)

        row = GrindPass(**values)
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return error("研磨遍次保存失败，请检查输入", 400)
        db.refresh(row)
        return jsonify(grind_pass_json(row)), 201
    finally:
        db.close()


@bp.put("/<int:item_id>")
@jwt_required()
def update_pass(item_id: int):
    body = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        row = db.get(GrindPass, item_id)
        if not row:
            return error("研磨遍次不存在", 404)

        values, msg = _validate(db, body)
        if msg:
            return error(msg, 400)

        for key, value in values.items():
            setattr(row, key, value)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return error("研磨遍次保存失败，请检查输入", 400)
        db.refresh(row)
        return jsonify(grind_pass_json(row))
    finally:
        db.close()


@bp.delete("/<int:item_id>")
@jwt_required()
def delete_pass(item_id: int):
    db = SessionLocal()
    try:
        row = db.get(GrindPass, item_id)
        if not row:
            return error("研磨遍次不存在", 404)
        db.delete(row)
        db.commit()
        return jsonify({"ok": True})
    finally:
        db.close()
