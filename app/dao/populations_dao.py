from app import db


def dao_estimate_population_for_area(polygon):
    # Estimates population by calculating the intersection of the area
    # with areas with known population counts
    query = """WITH proposed_polygon AS (
                SELECT ST_GeomFromText(:polygon, 4326) AS geom
            )
            SELECT
                SUM(
                    t.density * (ST_Area(ST_Intersection(t.geometry, proposed_polygon.geom))/ ST_Area(t.geometry))
                ) AS estimated_population
            FROM populations t, proposed_polygon
            WHERE ST_Intersects(t.geometry, proposed_polygon.geom)
        """
    result = db.session.execute(query, {"polygon": polygon}).fetchone()
    return result[0] or 0
