# This script should convert GeoJSON source data, for specified areas, to CSV.
# CSV columns: geographic_id,name,geometry,parent_geography_id

# First, rename the geojson file with the name of the CSV you want exported,
# this should correspond with the area type i.e. countries or wards

# Then in AREAS dictionary, specify the names of the columns storing data
# like the Area ID or Name, this will likely end in "CD" for ID (As in, "Area CoDe")
# or "NM" for Name (As in, "Area NaMe")

import csv
import json
import os
from math import isclose

from emergency_alerts_utils.polygons import Polygons
from shapely import wkt
from shapely.geometry import MultiPolygon, Polygon

MAX_NUMBER_OF_POINTS_PER_POLYGON = 250


def clean_up_invalid_polygons(polygons, indent="    "):
    # Taken from Admin SQLite DB scripts but adjusted
    for polygon in polygons:
        shapely_polygon = Polygon(polygon)

        simplified_polygon = wkt.loads(
            wkt.dumps(
                shapely_polygon,
                rounding_precision=5,
            )
        ).simplify(0)

        if simplified_polygon.is_valid:
            yield simplified_polygon
        else:
            invalid_polygons.append(shapely_polygon)

            if simplified_polygon.area == 0:
                # We don't want a polygon with 0 area
                continue

            buffered = shapely_polygon.buffer(0)

            if isinstance(buffered, MultiPolygon):
                yield from clean_up_invalid_polygons(buffered, indent="        ")
                continue

            fixed_polygon = Polygon(buffered.exterior)
            assert fixed_polygon.is_valid
            assert isclose(fixed_polygon.area, shapely_polygon.area, rel_tol=0.001)

            yield fixed_polygon


def simplify_geometry(feature):
    geometry_type = feature["type"]

    if geometry_type == "Polygon":
        return [feature["coordinates"][0]]

    if geometry_type == "MultiPolygon":
        return [polygon for polygon, *_ in feature["coordinates"]]

    raise ValueError(f"unknown geometry type: {geometry_type}")


def polygons_and_simplified_polygons(feature, area_type):
    # Returns full_resolution_polygons, simplified_polygons, utm_crs

    raw_polygons = simplify_geometry(feature)
    clean_raw_polygons = [
        [[x, y] for x, y in polygon.exterior.coords] for polygon in clean_up_invalid_polygons(raw_polygons)
    ]
    polygons = Polygons(clean_raw_polygons)

    # TODO: if flood wrning areas -> don't remove polygons that are too small
    full_resolution = polygons
    smoothed = full_resolution.smooth
    simplified = smoothed.simplify

    if not (len(full_resolution) or len(simplified)):
        raise RuntimeError("Polygon of 0 size found")

    point_counts.append(simplified.point_count)

    if simplified.point_count >= MAX_NUMBER_OF_POINTS_PER_POLYGON:
        raise RuntimeError(
            "Too many points "
            "(adjust Polygons.perimeter_to_simplification_ratio or "
            "Polygons.perimeter_to_buffer_ratio)"
        )

    fixed_output = []

    for polygons_to_check in (
        full_resolution.as_coordinate_pairs_long_lat,
        simplified.as_coordinate_pairs_long_lat,
    ):
        fixed_polygons = []

        for polygon in polygons_to_check:
            shapely_polygon = Polygon(polygon)

            if not shapely_polygon.is_valid:
                shapely_polygon = shapely_polygon.buffer(0)

            if shapely_polygon.is_empty:
                continue

            if isinstance(shapely_polygon, MultiPolygon):
                repaired_polygons = shapely_polygon.geoms
            else:
                repaired_polygons = (shapely_polygon,)

            for repaired_polygon in repaired_polygons:
                if not repaired_polygon.is_valid:
                    raise RuntimeError("Polygon remains invalid after simplification")

                fixed_polygons.append(list(repaired_polygon.exterior.coords))

        fixed_output.append(fixed_polygons)

    return (
        Polygons(fixed_output[0]),
        Polygons(fixed_output[1]),
        simplified.utm_crs,
    )


def load_parent_lookup(area_config):
    """Return a geographic ID to parent geographic ID dictionary."""
    lookup_file = area_config.get("lookup_file")

    if not lookup_file:
        return {}

    lookup_path = os.path.join(LOOKUP_FILES_DIR, lookup_file)
    lookup_id_column = area_config.get(
        "lookup_id_column",
        "geographic_id",
    )
    lookup_parent_column = area_config.get(
        "lookup_parent_column",
        "parent_geography_id",
    )

    with open(lookup_path, newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        parent_lookup = {}

        for row in reader:
            geographic_id = str(row[lookup_id_column] or "").strip()
            parent_geography_id = str(row[lookup_parent_column] or "").strip()

            # Returning parent geography id from lookup
            parent_lookup[geographic_id] = parent_geography_id or None

        return parent_lookup


AREAS = {
    "countries": {
        "id_column": "ctry19cd",
        "name_column": "ctry19nm",
    },
    "local_authority_districts": {
        "id_column": "LAD25CD",
        "name_column": "LAD25NM",
        "lookup_file": ("local_authority_districts_to_counties_and_unitary_authorities_lookup.csv"),
        "lookup_id_column": "LAD25CD",
        "lookup_parent_column": "CTYUA25CD",
    },
    "wards": {
        "id_column": "WD25CD",
        "name_column": "WD25NM",
        "lookup_file": "wards_to_local_authority_districts_lookup.csv",
        "lookup_id_column": "WD25CD",
        "lookup_parent_column": "LAD25CD",
    },
    # This has been created by hand - just checking against a document that stores area and parent
    "reppir_sites": {
        "id_column": "id",
        "name_column": "name",
        "lookup_file": "reppir_sites_to_local_authorities_lookup.csv",
        "lookup_id_column": "geographic_id",
        "lookup_parent_column": "parent_geography_id",
    },
    "counties_and_unitary_authorities": {
        "id_column": "CTYUA24CD",
        "name_column": "CTYUA24NM",
    },
    "police_force_areas": {
        "id_column": "PFA24CD",
        "name_column": "PFA24NM",
    },
}

SOURCE_FILES_DIR = "./source_data"  # The directory where source data is stored
OUTPUT_FILES_DIR = "./output_data"  # The directory where output data is stored
LOOKUP_FILES_DIR = "./lookups"  # The directory where lookup data is stored

point_counts = []
invalid_polygons = []

os.makedirs(OUTPUT_FILES_DIR, exist_ok=True)

for area in AREAS:
    print(f"processing {area}")

    area_config = AREAS[area]
    id_column = area_config["id_column"]
    name_column = area_config["name_column"]

    # Sources lookup file containing parent - child area mapping and returns as a dict
    parent_lookup = load_parent_lookup(area_config)

    with open(f"{SOURCE_FILES_DIR}/{area}.geojson", "r", encoding="utf-8") as f:
        geojsons = json.load(f)

    # Make CSV
    output_path = os.path.join(OUTPUT_FILES_DIR, f"{area}.csv")
    column_names = [
        "geographic_id",
        "name",
        "geometry",
        "parent_geography_id",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as output_file:
        # Writes first the CSV header, then iterates through GeoJSON features,
        # performs simplication & then converts to WKT to be added to CSV
        writer = csv.DictWriter(output_file, fieldnames=column_names)
        writer.writeheader()

        for feature in geojsons["features"]:
            properties = feature["properties"]
            print(properties[name_column])
            _, simplified_polygons, _ = polygons_and_simplified_polygons(
                feature["geometry"],
                area,
            )

            geographic_id = str(properties[id_column]).strip()

            # Areas not present in a lookup have no parent
            parent_geography_id = parent_lookup.get(geographic_id, "")
            if parent_geography_id == geographic_id:
                parent_geography_id = ""

            writer.writerow(
                {
                    "geographic_id": geographic_id,
                    "name": properties[name_column],
                    "geometry": simplified_polygons.as_wkt,
                    "parent_geography_id": parent_geography_id or "",
                }
            )
