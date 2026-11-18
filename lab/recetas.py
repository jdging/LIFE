"""Payload validation shared by recipe write endpoints."""

import math

SECTIONS = {"titulo", "ingredientes", "pasos"}
EDIT_FIELDS = SECTIONS | {"porciones"}


def _text(value, limit):
    return (isinstance(value, str) and 0 < len(value) <= limit and bool(value.strip())
            and "\x00" not in value and not any(0xD800 <= ord(c) <= 0xDFFF for c in value))


def validate(data, *, create):
    if not create:
        version = data.get("version")
        if type(version) is not int or not 1 <= version <= 2**63 - 1:
            raise ValueError("se requiere una versión válida.")
        if "activa" in data:
            if set(data) != {"version", "activa"} or type(data["activa"]) is not bool:
                raise ValueError("para archivar o restaurar, enviá solo versión y activa (booleano).")
            return dict(data)
    allowed = EDIT_FIELDS | ({"clave_ingesta", "allow_duplicado"} if create else {"version"})
    if set(data) - allowed:
        raise ValueError("campos de receta desconocidos.")
    if create and not SECTIONS <= data.keys():
        raise ValueError("se requieren titulo, ingredientes y pasos.")
    if not create and not EDIT_FIELDS.intersection(data):
        raise ValueError("se requiere al menos una sección para editar.")
    result = dict(data)
    if "porciones" in data and (type(data["porciones"]) is not int or not 1 <= data["porciones"] <= 9999):
        raise ValueError("porciones debe ser un entero entre 1 y 9999.")
    if "titulo" in data:
        if not _text(data["titulo"], 200):
            raise ValueError("titulo inválido.")
        result["titulo"] = data["titulo"].strip()
    if "pasos" in data:
        steps = data["pasos"]
        if not isinstance(steps, list) or (create and not steps) or len(steps) > 200 or not all(_text(s, 4000) for s in steps):
            raise ValueError("pasos inválidos.")
        result["pasos"] = [s.strip() for s in steps]
    if "ingredientes" in data:
        ingredients = data["ingredientes"]
        if not isinstance(ingredients, list) or (create and not ingredients) or len(ingredients) > 200:
            raise ValueError("ingredientes inválidos.")
        result["ingredientes"] = []
        for ingredient in ingredients:
            if not isinstance(ingredient, dict) or set(ingredient) - {"nombre", "cantidad", "unidad"}:
                raise ValueError("ingrediente inválido.")
            name, quantity, unit = (ingredient.get(k) for k in ("nombre", "cantidad", "unidad"))
            if not _text(name, 300) or (unit is not None and not _text(unit, 400)):
                raise ValueError("nombre o unidad de ingrediente inválidos.")
            if quantity is not None and (type(quantity) not in (int, float) or not 0 < quantity <= 1e12 or not math.isfinite(quantity)):
                raise ValueError("cantidad de ingrediente inválida.")
            result["ingredientes"].append({"nombre": name.strip(), "cantidad": quantity,
                                          "unidad": unit.strip() if isinstance(unit, str) else None})
    if "clave_ingesta" in data and not _text(data["clave_ingesta"], 200):
        raise ValueError("clave_ingesta inválida.")
    if "allow_duplicado" in data and type(data["allow_duplicado"]) is not bool:
        raise ValueError("allow_duplicado debe ser booleano.")
    return result
