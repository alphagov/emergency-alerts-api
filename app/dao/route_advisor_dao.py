from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app import db
from app.models import RouteAdvisor


def dao_set_route_for_mno(mno, proxy, target):
    sql = (
        pg_insert(RouteAdvisor)
        .values(
            mno=mno,
            proxy=proxy,
            target=target,
            updated_at=datetime.now(timezone.utc),
        )
        .on_conflict_do_update(
            index_elements=["mno"],
            set_={"proxy": proxy, "target": target, "updated_at": datetime.now(timezone.utc)},
        )
    )
    db.session.execute(sql)
    db.session.commit()


def dao_get_route_for_mno(mno):
    return RouteAdvisor.query.filter_by(mno=mno).first()
