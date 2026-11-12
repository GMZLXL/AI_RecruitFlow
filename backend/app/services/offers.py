from sqlalchemy import select

from app import schemas as s
from app.db import Offer, utcnow
from app.domain import Stage

from .common import conditional_update, fail, record_change, snapshot
from .recruitment import touch_application


def create_offer(db, actor, application, data: s.OfferCreate, expected: int):
    if application.version != expected:
        fail(409, "VERSION_CONFLICT", "申请版本已更新，请刷新")
    if application.stage != Stage.OFFER:
        fail(409, "INVALID_STAGE_TRANSITION", "只有Offer阶段可登记已发出记录")
    if db.scalar(select(Offer.id).where(Offer.application_id == application.id)):
        fail(409, "OFFER_EXISTS", "该申请已有Offer记录")
    if data.sent_at > utcnow() or data.sent_at < application.created_at:
        fail(400, "INVALID_OFFER_TIME", "发出时间应介于申请创建时间和当前时间之间")
    offer = Offer(application_id=application.id, sent_at=data.sent_at)
    db.add(offer)
    record_change(db, offer, actor, "record_offer_sent", reason=data.change_reason)
    touch_application(db, actor, application)
    return s.OfferRead.model_validate(offer)


def respond_offer(db, actor, application, offer, data: s.OfferPatch, expected: int):
    if offer.status != "sent":
        fail(409, "INVALID_OFFER_TRANSITION", "Offer已反馈，不能直接覆盖或逆转")
    if data.responded_at < offer.sent_at or data.responded_at > utcnow():
        fail(400, "INVALID_OFFER_TIME", "反馈时间应介于发出时间和当前时间之间")
    before = snapshot(offer)
    conditional_update(db, offer, expected, {"status": data.status, "responded_at": data.responded_at})
    record_change(db, offer, actor, "record_offer_response", before, data.change_reason)
    touch_application(db, actor, application)
    return s.OfferRead.model_validate(offer)
