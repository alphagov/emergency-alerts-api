from pathlib import Path

from lxml import etree


def validate_xml(document: str, schema_file_name):
    """
    Validate an XML string against a schema.
    This will either return a string with a description of how validation
    failed or None.
    """
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
