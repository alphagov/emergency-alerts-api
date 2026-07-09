from bs4 import BeautifulSoup


def cap_xml_to_dict(cap_xml):
    # This function assumes that it's being passed validated CAP XML
    # We explicitly tell BS4 that we're expecting utf-8 here, otherwise it uses encoding detection heuristics that
    # can sometimes make the wrong call.
    cap = BeautifulSoup(cap_xml, "xml", from_encoding="utf-8")
    alert = cap.alert
    # <info> is optional in the CAP 1.2 schema (minOccurs=0). A Cancel only needs
    # <references>, so we guard every <info> access here rather than dereferencing
    # blindly — missing fields then surface as schema validation errors (400) rather
    # than an AttributeError (500).
    info = alert.info

    broadcast = {
        "msgType": alert.msgType.text,
        "reference": alert.identifier.text,
        "references": (
            # references to previous events belonging to the same alert
            alert.references.text
            if alert.references
            else None
        ),
        "cap_event": None,
        "category": None,
        "expires": None,
        "content": None,
        "areas": [],
    }

    if info is not None:
        broadcast["cap_event"] = info.event.text if info.event else None
        broadcast["category"] = info.category.text if info.category else None
        broadcast["expires"] = info.expires.text if info.expires else None
        broadcast["content"] = info.description.text if info.description else None
        broadcast["areas"] = [
            {
                "name": area.areaDesc.text,
                "polygons": [cap_xml_polygon_to_list(polygon.text) for polygon in area.find_all("polygon")],
            }
            for area in info.find_all("area")
        ]

    return broadcast


def cap_xml_polygon_to_list(polygon_string):
    return [[float(coordinate) for coordinate in pair.split(",")] for pair in polygon_string.strip().split(" ")]
