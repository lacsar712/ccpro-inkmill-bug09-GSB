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

# duration_min 列为 Numeric(8, 2)，最大 999999.99
MAX_DURATION_MIN = Decimal("999999.99")


def _to_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _validate(body: dict) -> str | None:
    mill_id = _to_int(body.get("millId"))
    if mill_id is None or mill_id <= 0:
        return "请选择研磨机"

    if not str(body.get("startedAt") or "").strip():
        return "开始时间不能为空"

    pass_no = _to_int(body.get("passNo"))
    if pass_no is None or pass_no < 1:
        return "遍次编号必须 ≥ 1"

    try:
        duration = Decimal(str(body.get("durationMin")))
    except (InvalidOperation, TypeError, ValueError):
        return "研磨时长(分钟)必须是有效数字"
    if not duration.is_finite():
        return "研磨时长(分钟)必须是有效数字"
    if duration <= 0:
        return "研磨时长(分钟)必须大于 0"
    if duration > MAX_DURATION_MIN:
        return "研磨时长(分钟)超出允许范围"

    media = str(body.get("mediaType") or "").strip()
    if not media:
        return "研磨介质不能为空"
    if len(media) > 64:
        return "研磨介质过长（最多 64 字符）"

    operator = str(body.get("operatorName") or "").strip()
    if not operator:
        return "操作员不能为空"
    if len(operator) > 128:
        return "操作员名称过长（最多 128 字符）"

    db = SessionLocal()
    try:
        if not db.get(Mill, mill_id):
            return "研磨机不存在"
    finally:
        db.close()

    return None


def _apply(row: GrindPass, body: dict) -> GrindPass:
    """把已校验通过的字段写入行对象。调用前必须先通过 _validate。"""
    row.mill_id = int(body["millId"])
    row.started_at = normalize_datetime(str(body["startedAt"]).strip())
    row.pass_no = int(body["passNo"])
    row.duration_min = Decimal(str(body["durationMin"]))
    row.media_type = str(body["mediaType"]).strip()
    row.operator_name = str(body["operatorName"]).strip()
    return row


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
    err = _validate(body)
    if err:
        return error(err, 400)

    db = SessionLocal()
    try:
        row = _apply(GrindPass(), body)
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return error("研磨遍次保存失败，请重试", 400)
        db.refresh(row)
        return jsonify(grind_pass_json(row)), 201
    finally:
        db.close()


@bp.put("/<int:item_id>")
@jwt_required()
def update_pass(item_id: int):
    body = request.get_json(silent=True) or {}
    err = _validate(body)
    if err:
        return error(err, 400)

    db = SessionLocal()
    try:
        row = db.get(GrindPass, item_id)
        if not row:
            return error("研磨遍次不存在", 404)

        _apply(row, body)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return error("研磨遍次保存失败，请重试", 400)
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
