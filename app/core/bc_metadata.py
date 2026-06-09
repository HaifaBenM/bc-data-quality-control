"""
Module de lecture de la metadata BC via OData API.
Lit les définitions de champs depuis BC et les met en cache dans Supabase.
"""
import requests
import xml.etree.ElementTree as ET
from app.core.bc_connector import get_bc_token


# ── Mapping des types OData → types simples ───────────────────────────────────
EDM_TYPE_MAP = {
    "Edm.String":          "Text",
    "Edm.Int16":           "Integer",
    "Edm.Int32":           "Integer",
    "Edm.Int64":           "Integer",
    "Edm.Decimal":         "Decimal",
    "Edm.Double":          "Decimal",
    "Edm.Single":          "Decimal",
    "Edm.Boolean":         "Boolean",
    "Edm.Date":            "Date",
    "Edm.DateTimeOffset":  "DateTime",
    "Edm.Guid":            "Text",
    "Edm.Binary":          "Binary",
    "Edm.Stream":          "Binary",
}

# ── Tables prioritaires à charger ─────────────────────────────────────────────
PRIORITY_ENTITIES = [
    "customer", "vendor", "item", "account",
    "employee", "contact", "dimension",
    "paymentTerm", "currency", "countryRegion",
    "unitOfMeasure", "salesInvoice", "purchaseInvoice",
]

# ── Tables de référence disponibles via API v2.0 ──────────────────────────────
REFERENCE_ENTITIES = {
    "paymentTerms":    "Conditions de paiement",
    "currencies":      "Devises",
    "dimensions":      "Sections analytiques",
    "unitOfMeasures":  "Unités de mesure",
    "shipmentMethods": "Conditions de livraison",
    "paymentMethods":  "Modes de règlement",
    "countriesRegions": "Pays/Régions",
    "taxGroups":       "Groupes TVA",
    "itemCategories":  "Catégories d'articles",
    "salespeople":     "Vendeurs",
    "locations":       "Magasins",
}


def read_bc_metadata(
    tenant_id:     str,
    client_id:     str,
    client_secret: str,
    environment:   str = ""
) -> dict:
    """
    Lit et parse le $metadata OData BC.
    Retourne un dict : {entity_name: {label, fields: [...]}}
    """
    result = {
        "success":  False,
        "entities": {},
        "error":    "",
        "nb_entities": 0,
        "nb_fields":   0,
    }

    # Obtenir le token
    ok, token_or_err = get_bc_token(tenant_id, client_id, client_secret)
    if not ok:
        result["error"] = token_or_err
        return result

    # URL du $metadata
    base = f"https://api.businesscentral.dynamics.com/v2.0/{tenant_id.strip()}"
    if environment and environment.strip():
        base += f"/{environment.strip()}"
    meta_url = f"{base}/api/v2.0/$metadata"

    try:
        resp = requests.get(
            meta_url,
            headers={
                "Authorization": f"Bearer {token_or_err}",
                "Accept": "application/xml",
            },
            timeout=30
        )

        if resp.status_code != 200:
            result["error"] = (
                f"Erreur lecture metadata ({resp.status_code}). "
                "Vérifiez les permissions API."
            )
            return result

        entities = _parse_metadata_xml(resp.text)
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
    """
    Parse le CSDL XML OData et extrait les définitions d'entités.
    Retourne {entity_name: {label, fields: [{name, type, maxLength, mandatory}]}}
    """
    entities = {}

    try:
        # Nettoyer les namespaces pour simplifier le parsing
        xml_clean = xml_text
        root = ET.fromstring(xml_clean)

        # Namespace OData CSDL
        ns = {
            "edmx": "http://docs.oasis-open.org/odata/ns/edmx",
            "edm":  "http://docs.oasis-open.org/odata/ns/edm",
        }

        # Parcourir tous les EntityType
        for schema in root.findall(".//edm:Schema", ns):
            for entity_type in schema.findall("edm:EntityType", ns):
                name = entity_type.get("Name", "")
                if not name:
                    continue

                fields = []
                for prop in entity_type.findall("edm:Property", ns):
                    field_name   = prop.get("Name", "")
                    raw_type     = prop.get("Type", "Edm.String")
                    max_length   = prop.get("MaxLength")
                    nullable     = prop.get("Nullable", "true").lower()
                    is_mandatory = nullable == "false"

                    # Nettoyer le type (enlever le namespace)
                    if "." in raw_type:
                        type_parts = raw_type.split(".")
                        raw_type_clean = f"{type_parts[-2]}.{type_parts[-1]}" \
                            if len(type_parts) >= 2 else raw_type
                    else:
                        raw_type_clean = raw_type

                    simple_type = EDM_TYPE_MAP.get(raw_type_clean, "Text")

                    field_def = {
                        "name":      field_name,
                        "type":      simple_type,
                        "raw_type":  raw_type_clean,
                        "mandatory": is_mandatory,
                    }
                    if max_length:
                        try:
                            field_def["maxLength"] = int(max_length)
                        except ValueError:
                            pass

                    fields.append(field_def)

                if fields:
                    entities[name] = {
                        "label":  name,
                        "fields": fields,
                    }

    except ET.ParseError as e:
        # Retourner dict vide si XML malformé
        pass
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
    """
    Lit les données d'une table de référence BC via l'API.
    Ex: entity_path = "paymentTerms", "currencies", "countriesRegions"

    Retourne {success, data: [{id, code, name, ...}], count, error}
    """
    result = {"success": False, "data": [], "count": 0, "error": ""}

    ok, token_or_err = get_bc_token(tenant_id, client_id, client_secret)
    if not ok:
        result["error"] = token_or_err
        return result

    base = f"https://api.businesscentral.dynamics.com/v2.0/{tenant_id.strip()}"
    if environment and environment.strip():
        base += f"/{environment.strip()}"

    url = f"{base}/api/v2.0/companies({company_id})/{entity_path}?$top=500"

    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {token_or_err}"},
            timeout=20
        )

        if resp.status_code == 200:
            data = resp.json().get("value", [])
            result["success"] = True
            result["data"]    = data
            result["count"]   = len(data)
        elif resp.status_code == 404:
            result["error"] = f"Table '{entity_path}' non disponible dans cet environnement."
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
    """
    Charge toutes les tables de référence disponibles.
    Retourne {entity_path: {label, data, count}}
    """
    results = {}

    for entity_path, label in REFERENCE_ENTITIES.items():
        res = read_reference_data(
            tenant_id, client_id, client_secret,
            environment, company_id, entity_path
        )
        if res["success"] and res["count"] > 0:
            results[entity_path] = {
                "label": label,
                "data":  res["data"],
                "count": res["count"],
            }

    return results
