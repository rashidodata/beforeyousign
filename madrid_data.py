"""Read-only Madrid open-data queries; conservative house-number verification.

No inference that an empty search means 'no permits' or 'no fines'.
"""
from __future__ import annotations
import re
import unicodedata
from typing import Any
import requests

API_URL = "https://datos.madrid.es/api/3/action/datastore_search"
SOURCES = {
    "Urban planning licences (2023 onward)": {
        "id":"640505-1-licencias-urbanisticas-otorgadas",
        "url":"https://datos.madrid.es/dataset/640505-0-licencias-urbanisticas-otorgadas",
    },
    "Responsible declarations (2023 onward)": {
        "id":"133556-0-declaraciones-responsables",
        "url":"https://datos.madrid.es/dataset/133556-0-declaraciones-responsables",
    },
}
REVIEW_SOURCES = {
    "Entertainment premises inspections": "https://datos.madrid.es/dataset/300160-0-inspecciones-industrias-lepar",
    "Urban-planning sanctions / restitution": "https://datos.madrid.es/dataset/300234-0-urbanismo-sanciones-medidas",
    "Buildings declared in ruin": "https://datos.madrid.es/dataset/300378-0-edificios-ruina",
}
STREET_TYPES = {"CALLE","C","CL","C.","AV","AVENIDA","PASEO","PZA","PLAZA","TRAVESIA","TRVA","GLORIETA","CAMINO","RONDA","DE","DEL","LA","LAS","LOS","EL"}
SAFE_FIELDS = (
    "No_EXPEDIENTE", "NUM_EXPEDIENTE", "N_EXPEDIENTE", "TIPO", "ORGANO_COMPETENTE",
    "NORMA_ZONAL", "NIVEL_PROTECCION", "FECHA_ALTA", "FECHA_FIRMA_RESOLUCION",
    "RESOLUCION", "VIA", "DIRECCION", "No", "NDP", "EMPLAZAMIENTO", "OBJETO",
    "USO", "REGIMEN_USO", "ACTIVIDAD", "TIPO_PROCEDIMIENTO", "FECHA_PRESENTACION"
)


def normalized(value: Any) -> str:
    value = unicodedata.normalize("NFKD", str(value or "")).encode("ascii","ignore").decode().upper()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", value)).strip()


def parse_address(address: str) -> tuple[str, str]:
    # Accept Calle de X, 41, Madrid; fail closed if street or number missing.
    parts=[p.strip() for p in address.split(",")]
    left=parts[0]
    if len(parts)>1 and re.fullmatch(r"\d{1,4}[A-Za-z]?",parts[1]):
        left += " " + parts[1]
    m=re.search(r"\b(\d{1,4})(?:\s*[A-Za-z])?\s*$",left)
    if not m:
        raise ValueError("Enter street and house number, e.g. Calle Caceres 41, Madrid")
    num=str(int(m.group(1)))
    words=normalized(left[:m.start()]).split()
    words=[w for w in words if w not in STREET_TYPES]
    if not words:
        raise ValueError("A named street is required")
    return " ".join(words),num


def record_matches(record: dict, address: str) -> bool:
    street, number = parse_address(address)
    d={normalized(k).replace(" ","_"): str(v or "") for k,v in record.items()}
    # Particular Madrid dataset has DIRECCION=street, No=house-number.
    street_fields=["DIRECCION","VIA","VIAL","VIAL_INDUSTRIA","NOMBRE_VIA","CALLE","EMPLAZAMIENTO"]
    num_fields=["NO","NUMERO","NUM","NUM_VIAL","NUMERO_DEL_VIAL","NUM_PORTAL","PORTAL"]
    found_street = any(bool(re.search(r"\b"+re.escape(street)+r"\b",normalized(d.get(k)))) for k in street_fields if d.get(k))
    if not found_street:
        return False
    numbers = [d[k].strip() for k in num_fields if d.get(k) and d[k].strip()]
    # Require exact portal via explicit number field when possible.
    if numbers:
        return any(re.fullmatch(r"0*"+re.escape(number)+r"(?:\s*[A-Za-z])?",v.strip(),re.I) for v in numbers)
    # If no house number field exists, only permit explicit street+number match in full address field.
    for k in ("EMPLAZAMIENTO","DIRECCION"):
        full=normalized(d.get(k))
        if re.search(r"\b"+re.escape(number)+r"\b",full):
            return True
    return False


def safe_excerpt(rec: dict) -> dict:
    keys={normalized(x).replace(" ","_") for x in SAFE_FIELDS}
    return {str(k):str(v)[:350] for k,v in rec.items()
            if normalized(k).replace(" ","_") in keys and v is not None and str(v).strip()}


def query_source(address: str, resource_id: str, *, session=None, limit: int=200) -> list[dict]:
    street,_=parse_address(address)
    # CKAN 'q' is full-text, not a reliable address filter: verify exact street and number below.
    s=session or requests
    response=s.get(API_URL, params={"resource_id":resource_id,"q":street,"limit":limit},timeout=16,
                   headers={"User-Agent":"BeforeYouSign/0.1 (property research; source attribution)"})
    response.raise_for_status()
    payload=response.json()
    if not payload.get("success"):
        raise RuntimeError("Madrid API reported failure")
    records=payload.get("result",{}).get("records",[])
    return [safe_excerpt(x) for x in records if record_matches(x,address)]


def inspect_address(address: str, *, session=None) -> dict:
    parse_address(address)
    out={}
    for title,source in SOURCES.items():
        try:
            matched=query_source(address,source["id"],session=session)
            status=(f"{len(matched)} address-matched open-data records"
                    if matched else "No exact address match in this API query — NOT proof of no records")
            out[title]={"status":status,"records":matched,"url":source["url"],"checked":True}
        except Exception as exc:
            out[title]={"status":f"Lookup unavailable: {type(exc).__name__}: {str(exc)[:120]}",
                        "records":[],"url":source["url"],"checked":False}
    for title,url in REVIEW_SOURCES.items():
        out[title]={"status":"Manual review required; not queried automatically in this MVP",
                    "records":[],"url":url,"checked":False}
    return out