from pathlib import Path

from flask import current_app
from lxml import etree


def validate_xml(document: bytes, schema_file_name):
    """
    Validate an XML string against a schema.
    This will either return a string with a description of how validation
    failed or None.
    """
    max_length = current_app.config["MAX_BROADCASTS_XML_LENGTH"]
    doc_length = len(document)
    if doc_length > max_length:
        return f"XML must be {max_length} characters or fewer"

    # CAP documents never legitimately contain a DOCTYPE, and one with
    # internal entity definitions makes the downstream BeautifulSoup parse
    # produce an empty tree (crashing with AttributeError -> 500). Reject
    # up front so it surfaces as a 400 instead.
    if b"<!DOCTYPE" in document:
        return "XML must not contain a DOCTYPE declaration"

    path = Path(__file__).resolve().parent / schema_file_name
    contents = path.read_text()

    xml_parser = etree.XMLParser(
        resolve_entities=False,
        ns_clean=True,
        encoding="utf-8",
    )

    schema_xml = etree.XML(contents.encode("utf-8"))
    schema = etree.XMLSchema(schema_xml)

    try:
        doc = etree.fromstring(document, parser=xml_parser)

        schema.assertValid(doc)
    except (etree.XMLSyntaxError, etree.DocumentInvalid) as e:
        return str(e)

    return None
