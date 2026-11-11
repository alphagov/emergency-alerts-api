from abc import ABC, abstractmethod

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
    def can_resolve(cls, area_id):
        pass

    @classmethod
    @abstractmethod
    def resolve(cls, area_id):
        pass


class PostcodeAreaResolver(AreaResolver):
    @classmethod
    def can_resolve(cls, area_id):
        return area_id.startswith("postcodes_")

    @classmethod
    def resolve(cls, area_id):
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

        return {
            "id": area_id,
            "name": name,
            "geographic_id": postcode,
            "geography_type_name": "postcodes",
        }


class CoordinateAreaResolver(AreaResolver):
    @classmethod
    def can_resolve(cls, area_id):
        return area_id.startswith("coordinates_")

    @classmethod
    def resolve(cls, area_id):
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
            raise AreaResolutionError(f"Invalid coordinate area ID: '{area_id}'.")

        try:
            longitude, latitude = convert_to_long_lat_coordinates(
                first_coordinate,
                second_coordinate,
                coordinate_type,
            )
        except Exception:
            raise AreaResolutionError("Invalid coordinate values or coordinate type.")

        if coordinate_type == "latitude_longitude":
            name = f"{radius:g}km around " f"{first_coordinate:g} latitude, " f"{second_coordinate:g} longitude"
        elif coordinate_type == "easting_northing":
            name = (
                f"{radius:g}km around the easting of "
                f"{first_coordinate:g} and the northing of "
                f"{second_coordinate:g}"
            )
        else:
            raise AreaResolutionError("Invalid coordinate values or coordinate type.")

        centroid = shapely.Point(longitude, latitude).wkt

        parent_area = get_parent_area_name(centroid)

        if parent_area:
            name = f"{name}, in {parent_area}"

        return {
            "id": area_id,
            "name": name,
            "geographic_id": None,
            "geography_type_name": "coordinates",
        }


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
    def resolve(cls, area_id):
        _, geographic_id = area_id.split("-", 1)

        #
        # You'll need a DAO method that returns the same
        # structure as get_area() does.
        #
        area_data = AreasDAO.get_area_by_geographic_id(geographic_id)

        if area_data is None:
            raise AreaResolutionError(f"No area could be found for geographic ID '{geographic_id}'.")

        return {
            **area_data["area"].serialize(),
            "geography_type_name": area_data["geography_type_name"],
        }


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
    def resolve(cls, area_id):
        area_data = AreasDAO.get_area(area_id)

        if area_data is None:
            raise AreaResolutionError(f"No area could be found for area ID '{area_id}'.")

        return {
            **area_data["area"].serialize(),
            "geography_type_name": area_data["geography_type_name"],
        }


class AreaResolverRegistry:
    RESOLVERS = (
        PostcodeAreaResolver,
        CoordinateAreaResolver,
        LegacyAreaResolver,
        GeographyAreaResolver,
    )

    @classmethod
    def resolve(cls, area_id):
        for resolver in cls.RESOLVERS:
            if resolver.can_resolve(area_id):
                return resolver.resolve(area_id)

        raise AreaResolutionError(f"Unsupported area ID: '{area_id}'.")
