from datetime import datetime, timezone

from app import db
from app.models import RouteAdvisor


def dao_set_route_for_mno(mno, proxy, target):
    db.session.query(RouteAdvisor).filter_by(mno=mno).update(
        {"proxy": proxy, "target": target, "updated_at": datetime.now(timezone.utc)}
    )
    db.session.commit()


def dao_get_route_for_mno(mno):
    return RouteAdvisor.query.filter_by(mno=mno).first()
