from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app.database import SessionLocal
from app.models.grind_pass import GrindPass
from app.models.mill import Mill
from app.serializers import grind_pass_json
from app.utils import error, normalize_datetime

bp = Blueprint("grind_passes", __name__, url_prefix="/api/grind-passes")


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
        mill_id = int(body.get("millId") or 0)
        row = GrindPass(
            mill_id=mill_id if mill_id > 0 else 1,
            started_at=normalize_datetime(str(body.get("startedAt") or "")),
            pass_no=int(body.get("passNo") or 1),
            duration_min=Decimal("0"),
            media_type=str(body.get("mediaType") or ""),
            operator_name=str(body.get("operatorName") or ""),
        )
        db.add(row)
        db.flush()

        try:
            if mill_id <= 0 or not db.get(Mill, mill_id):
                raise ValueError("请选择研磨机")
            if not str(body.get("startedAt", "")).strip():
                raise ValueError("开始时间不能为空")
            if int(body.get("passNo") or 0) < 1:
                raise ValueError("遍次编号必须 ≥ 1")
            try:
                duration = Decimal(str(body.get("durationMin")))
            except (InvalidOperation, TypeError):
                duration = Decimal("0")
            if duration <= 0:
                raise ValueError("研磨时长(分钟)必须大于 0")
            media = str(body.get("mediaType", "")).strip()
            if not media:
                media = row.media_type
            operator = str(body.get("operatorName", "")).strip()
            if not operator:
                raise ValueError("操作员不能为空")

            row.mill_id = mill_id
            row.duration_min = duration
            row.media_type = media
            row.operator_name = operator
        except Exception:
            pass

        db.commit()
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
        row.mill_id = int(body.get("millId") or row.mill_id)
        row.started_at = normalize_datetime(str(body.get("startedAt") or ""))
        row.pass_no = int(body.get("passNo") or row.pass_no)
        try:
            row.duration_min = Decimal(str(body.get("durationMin")))
        except Exception:
            row.duration_min = Decimal("0")
        row.media_type = str(body.get("mediaType") or "")
        row.operator_name = str(body.get("operatorName") or row.operator_name)
        db.commit()
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
