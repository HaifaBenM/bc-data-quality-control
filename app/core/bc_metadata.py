"""
Module de lecture de la metadata BC via OData API.
"""
import requests
import xml.etree.ElementTree as ET
from app.core.bc_connector import get_bc_token


EDM_TYPE_MAP = {
    "Edm.String":         "Text",
    "Edm.Int16":          "Integer",
    "Edm.Int32":          "Integer",
    "Edm.Int64":          "Integer",
    "Edm.Decimal":        "Decimal",
    "Edm.Double":         "Decimal",
    "Edm.Single":         "Decimal",
    "Edm.Boolean":        "Boolean",
    "Edm.Date":           "Date",
    "Edm.DateTimeOffset": "DateTime",
    "Edm.Guid":           "Text",
    "Edm.Binary":         "Binary",
    "Edm.Stream":         "Binary",
}

REFERENCE_ENTITIES = {
    "paymentTerms":                "Conditions de paiement",
    "currencies":                  "Devises",
    "dimensions":                  "Sections analytiques",
    "unitsOfMeasure":              "Unités de mesure",
    "shipmentMethods":             "Conditions de livraison",
    "paymentMethods":              "Modes de règlement",
    "countriesRegions":            "Pays/Régions",
    "taxGroups":                   "Groupes TVA",
    "itemCategories":              "Catégories article",
    "salespeople":                 "Vendeurs",
    "locations":                   "Magasins",
    "generalProductPostingGroups": "Groupes compta. produit",
    "vatBusinessPostingGroups":    "Groupes compta. marché TVA",
    "vatProductPostingGroups":     "Groupes compta. produit TVA",
    "customerPostingGroups":       "Groupes compta. client",
    "vendorPostingGroups":         "Groupes compta. fournisseur",
    "inventoryPostingGroups":      "Groupes compta. stock",
    "itemDiscountGroups":          "Groupes remises article",
    "customers":                   "Clients",
    "vendors":                     "Fournisseurs",
    "items":                       "Articles",
    "glAccounts":                  "Comptes généraux",
}


def read_bc_metadata(
    tenant_id:     str,
    client_id:     str,
    client_secret: str,
    environment:   str = "",
) -> dict:
    result = {
        "success":     False,
        "entities":    {},
        "error":       "",
        "nb_entities": 0,
        "nb_fields":   0,
    }

    ok, token_or_err = get_bc_token(tenant_id, client_id, client_secret)
    if not ok:
        result["error"] = token_or_err
        return result

    base = f"https://api.businesscentral.dynamics.com/v2.0/{tenant_id.strip()}"
    if environment and environment.strip():
        base += f"/{environment.strip()}"
    meta_url = f"{base}/api/v2.0/$metadata"

    try:
        resp = requests.get(
            meta_url,
            headers={
                "Authorization": f"Bearer {token_or_err}",
                "Accept":        "application/xml",
            },
            timeout=30,
        )
        if resp.status_code != 200:
            result["error"] = f"Erreur lecture metadata ({resp.status_code})."
            return result

        entities              = _parse_metadata_xml(resp.text)
        result["entities"]    = entities
        result["success"]     = True
        result["nb_entities"] = len(entities)
        result["nb_fields"]   = sum(
            len(e.get("fields", [])) for e in entities.values()
        )
    except requests.exceptions.Timeout:
        result["error"] = "Délai dépassé lors de la lecture du metadata."
    except Exception as e:
        result["error"] = f"Erreur inattendue : {str(e)}"

    return result


def _parse_metadata_xml(xml_text: str) -> dict:
    entities = {}
    try:
        root = ET.fromstring(xml_text)
        ns   = {
            "edmx": "http://docs.oasis-open.org/odata/ns/edmx",
            "edm":  "http://docs.oasis-open.org/odata/ns/edm",
        }
        for schema in root.findall(".//edm:Schema", ns):
            for entity_type in schema.findall("edm:EntityType", ns):
                name = entity_type.get("Name", "")
                if not name:
                    continue
                fields = []
                for prop in entity_type.findall("edm:Property", ns):
                    field_name = prop.get("Name", "")
                    raw_type   = prop.get("Type", "Edm.String")
                    max_length = prop.get("MaxLength")
                    nullable   = prop.get("Nullable", "true").lower()
                    if "." in raw_type:
                        parts    = raw_type.split(".")
                        raw_type = f"{parts[-2]}.{parts[-1]}" if len(parts) >= 2 else raw_type
                    field_def = {
                        "name":      field_name,
                        "type":      EDM_TYPE_MAP.get(raw_type, "Text"),
                        "raw_type":  raw_type,
                        "mandatory": nullable == "false",
                    }
                    if max_length:
                        try:
                            field_def["maxLength"] = int(max_length)
                        except ValueError:
                            pass
                    fields.append(field_def)
                if fields:
                    entities[name] = {"label": name, "fields": fields}
    except Exception:
        pass
    return entities


def read_reference_data(
    tenant_id:     str,
    client_id:     str,
    client_secret: str,
    environment:   str,
    company_id:    str,
    entity_path:   str,
) -> dict:
    result = {"success": False, "data": [], "count": 0, "error": ""}

    ok, token_or_err = get_bc_token(tenant_id, client_id, client_secret)
    if not ok:
        result["error"] = token_or_err
        return result

    base = f"https://api.businesscentral.dynamics.com/v2.0/{tenant_id.strip()}"
    if environment and environment.strip():
        base += f"/{environment.strip()}"
    url = f"{base}/api/v2.0/companies({company_id})/{entity_path}?$top=5000"

    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {token_or_err}"},
            timeout=20,
        )
        if resp.status_code == 200:
            data              = resp.json().get("value", [])
            result["success"] = True
            result["data"]    = data
            result["count"]   = len(data)
        elif resp.status_code == 404:
            result["error"] = f"Table '{entity_path}' non disponible."
        else:
            result["error"] = f"Erreur API ({resp.status_code})"
    except requests.exceptions.Timeout:
        result["error"] = "Délai dépassé."
    except Exception as e:
        result["error"] = str(e)

    return result


def load_all_reference_data(
    tenant_id:     str,
    client_id:     str,
    client_secret: str,
    environment:   str,
    company_id:    str,
) -> dict:
    results = {}
    for entity_path, label in REFERENCE_ENTITIES.items():
        res = read_reference_data(
            tenant_id, client_id, client_secret,
            environment, company_id, entity_path,
        )
        if res["success"] and res["count"] > 0:
            results[entity_path] = {
                "label": label,
                "data":  res["data"],
                "count": res["count"],
            }
    return results