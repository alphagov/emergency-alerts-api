# Broadcast CAP XML request format

The public `POST /v2/broadcast` endpoint (see [`app/v2/broadcast/post_broadcast.py`](../app/v2/broadcast/post_broadcast.py))
accepts a [CAP 1.2](https://docs.oasis-open.org/emergency/cap/v1.2/CAP-v1.2.html) `<alert>`
document. The request `Content-Type` **must** be `application/cap+xml`; any other content
type returns `415`.

The payload is validated in three stages, in this order:

1. **CAP 1.2 schema** (`CAP-v1.2.xsd`) — structural validation. CAP defines `<alert>` as an
   `xs:sequence`, so child elements must appear in the schema-mandated order, not just be
   present (see [element ordering](#element-ordering) below).
2. **Translation** — [`cap_xml_to_dict`](../app/broadcast_message/translators.py) extracts the
   fields we use into a JSON object.
3. **JSON schema** — [`broadcast_schemas.py`](../app/v2/broadcast/broadcast_schemas.py)
   validates that object. A different schema applies depending on `<msgType>`.

## Message types

We support two `<msgType>` values: `Alert` (create a new broadcast) and `Cancel`
(cancel/reject an existing one). `Update`, `Ack`, and `Error` are valid CAP but not
currently supported.

The required elements differ significantly between the two, because a `Cancel` only needs to
identify the alert being cancelled — it does not carry any content of its own.

### Alert

A new broadcast must supply the full alert. Required elements:

| Element | Notes |
| --- | --- |
| `<identifier>` | Becomes the broadcast `reference`. |
| `<sender>` | Must match the CAP `sender` pattern. |
| `<sent>` | `YYYY-MM-DDThh:mm:ss±hh:mm`. |
| `<status>` | e.g. `Actual`. |
| `<msgType>` | `Alert`. |
| `<scope>` | e.g. `Public`. |
| `<info>` | Required. Must contain the elements below. |
| `<info><category>` | Must be one of the CAP categories (`Geo`, `Met`, `Safety`, …). |
| `<info><event>` | Free text; becomes `cap_event`. |
| `<info><urgency>` / `<severity>` / `<certainty>` | Required by the CAP schema. The values are not used by us, but must be valid CAP enum values. |
| `<info><description>` | The broadcast content. May be empty, but the element must be present. |
| `<info><area>` | At least one. Each `<area>` needs an `<areaDesc>` and at least one `<polygon>` of **4 or more** coordinate pairs. |

`<info><expires>` is accepted but ignored — expiry for API-created broadcasts follows the
same rules as those created in the admin app.

### Cancel

A `Cancel` is matched against existing broadcasts using `<references>`, so that is the only
content-bearing element it needs. The entire `<info>` block is **optional** and is ignored if
present.

Required elements:

| Element | Notes |
| --- | --- |
| `<identifier>` | Required by the CAP schema. |
| `<sender>` | Required by the CAP schema. |
| `<sent>` | Required by the CAP schema. |
| `<status>` | Required by the CAP schema. |
| `<msgType>` | `Cancel`. |
| `<scope>` | Required by the CAP schema. |
| `<references>` | The alert(s) to cancel, conventionally comma-separated `sender,identifier,sent` triples (the code splits on `,` and matches against stored references). An absent `<references>` element returns `400`; an empty one (`<references></references>`) is treated as a reference that matches nothing and returns `404`. |

If `<references>` matches a broadcast that is still `pending-approval` it is **rejected**;
otherwise it is **cancelled**. If `<references>` lists more than one distinct broadcast the
request is rejected with `400` (it must uniquely identify a single alert).

A minimal valid `Cancel`:

```xml
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
    <identifier>5fc99d720abb86020b233422a503af78E</identifier>
    <sender>www.gov.uk/environment-agency</sender>
    <sent>2020-02-16T23:02:26-00:00</sent>
    <status>Actual</status>
    <msgType>Cancel</msgType>
    <scope>Public</scope>
    <references>www.gov.uk/environment-agency,50385fcb0ab7aa447bbd46d848ce8466E,2020-02-16T23:01:13-00:00</references>
</alert>
```

A `Cancel` may still include a full `<info>` block (it is simply ignored), so existing
integrations that send one continue to work unchanged.

## Element ordering

Because `<alert>` is a CAP `xs:sequence`, elements must appear in this order. A common
mistake is placing `<references>` before `<scope>`, which fails schema validation with
`Element '…references': This element is not expected.`

```
identifier → sender → sent → status → msgType
→ source (optional) → scope → restriction (optional) → addresses (optional)
→ code (optional) → note (optional) → references (optional) → incidents (optional) → info
```

So `<references>` must come **after** `<scope>`, not immediately after `<msgType>`.
