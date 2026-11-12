from abc import ABC, abstractmethod
from collections import defaultdict

import shapely

from app.areas.utils import (
    convert_to_long_lat_coordinates,
    get_parent_area_name,
)
from app.dao.areas_dao import AreasDAO


class AreaResolutionError(Exception):
    """Raised when an area ID cannot be resolved."""


class AreaResolver(ABC):
    @classmethod
    @abstractmethod
    def can_resolve(cls, area_id: str) -> bool:
        pass

    @classmethod
    @abstractmethod
    def resolve_all(cls, area_ids: list[str]) -> list[dict]:
        pass


class PostcodeAreaResolver(AreaResolver):
    @classmethod
    def can_resolve(cls, area_id):
        return area_id.startswith("postcodes_")

    @classmethod
    def resolve_all(cls, area_ids):
        areas = []

        for area_id in area_ids:
            try:
                _, x_coordinate, y_coordinate, radius, postcode = area_id.split("_", 4)

                radius = float(radius)
                x_coordinate = float(x_coordinate)
                y_coordinate = float(y_coordinate)

            except (TypeError, ValueError):
                raise AreaResolutionError(f"Invalid postcode area ID: '{area_id}'.")

            centroid = shapely.Point(x_coordinate, y_coordinate).wkt

            name = f"{radius:g}km around the postcode {postcode}"

            parent_area = get_parent_area_name(centroid)

            if parent_area:
                name = f"{name}, in {parent_area}"

            areas.append(
                {
                    "id": area_id,
                    "name": name,
                    "geographic_id": postcode,
                    "geography_type_name": "postcodes",
                }
            )

        return areas


class CoordinateAreaResolver(AreaResolver):
    @classmethod
    def can_resolve(cls, area_id):
        return area_id.startswith("coordinates_")

    @classmethod
    def resolve_all(cls, area_ids):
        areas = []

        for area_id in area_ids:
            try:
                (
                    _,
                    first_coordinate,
                    second_coordinate,
                    radius,
                    coordinate_type,
                ) = area_id.split("_", 4)

                radius = float(radius)
                first_coordinate = float(first_coordinate)
                second_coordinate = float(second_coordinate)

            except (TypeError, ValueError):
                raise AreaResolutionError(f"Invalid coordinate area ID: '{area_id}'")

            try:
                longitude, latitude = convert_to_long_lat_coordinates(
                    first_coordinate,
                    second_coordinate,
                    coordinate_type,
                )
            except Exception:
                raise AreaResolutionError("Invalid coordinate values or coordinate type")

            if coordinate_type == "latitude_longitude":
                name = f"{radius:g}km around " f"{first_coordinate:g} latitude, " f"{second_coordinate:g} longitude"
            elif coordinate_type == "easting_northing":
                name = (
                    f"{radius:g}km around the easting of "
                    f"{first_coordinate:g} and the northing of "
                    f"{second_coordinate:g}"
                )
            else:
                raise AreaResolutionError("Invalid coordinate values or coordinate type")

            centroid = shapely.Point(longitude, latitude).wkt

            parent_area = get_parent_area_name(centroid)

            if parent_area:
                name = f"{name}, in {parent_area}"

            areas.append(
                {
                    "id": area_id,
                    "name": name,
                    "geographic_id": None,
                    "geography_type_name": "coordinates",
                }
            )

        return areas


class LegacyAreaResolver(AreaResolver):

    LEGACY_PREFIXES = (
        "Flood_Warning_Target_Areas-",
        "REPPIR_DEPZ_sites-",
        "test-",
        "ctry19-",
        "wd21-",
        "wd23-",
        "wd25-",
        "lad21-",
        "lad23-",
        "lad25-",
        "ctyua23-",
        "ctyua25-",
    )

    @classmethod
    def can_resolve(cls, area_id):
        return area_id.startswith(cls.LEGACY_PREFIXES)

    @classmethod
    def resolve_all(cls, area_ids):
        geographic_ids = [area_id.split("-", 1)[1] for area_id in area_ids]

        areas = AreasDAO.get_areas_by_geographic_ids(geographic_ids)

        if len(areas) != len(geographic_ids):
            raise AreaResolutionError("No area could be found for one or more geographic IDs.")

        return [
            {
                **area.serialize(),
                "geography_type_name": None,  # see note below
            }
            for area in areas
        ]


class GeographyAreaResolver(AreaResolver):
    """
    Default resolver.

    Anything not matching postcode, coordinate
    or legacy formats is treated as a geography UUID.
    """

    @classmethod
    def can_resolve(cls, area_id):
        return True

    @classmethod
    def resolve_all(cls, area_ids):
        areas = AreasDAO.get_areas_by_ids(set(area_ids))

        if len(areas) != len(set(area_ids)):
            raise AreaResolutionError("No area could be found for one or more area IDs")

        return [
            {
                **area_data["area"].serialize(),
                "geography_type_name": area_data["geography_type_name"],
            }
            for area_data in areas
        ]


class AreaResolverRegistry:
    RESOLVERS = (
        PostcodeAreaResolver,
        CoordinateAreaResolver,
        LegacyAreaResolver,
        GeographyAreaResolver,
    )

    @classmethod
    def get_resolver(cls, area_id):
        for resolver in cls.RESOLVERS:
            if resolver.can_resolve(area_id):
                return resolver

        raise AreaResolutionError(f"Unsupported area ID: '{area_id}'.")

    @classmethod
    def resolve_all(cls, area_ids):
        groups = defaultdict(list)

        for area_id in area_ids:
            resolver = cls.get_resolver(area_id)
            groups[resolver].append(area_id)

        resolved = []

        for resolver, ids in groups.items():
            resolved.extend(resolver.resolve_all(ids))

        return resolved
