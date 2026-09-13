"""Offline synthetic catalog jobs; artifacts are independent of serving services."""
import argparse
import hashlib
import gzip
import io
import json
import os
import random
import sqlite3
from pathlib import Path
from typing import Any, Iterator, Literal
from urllib.request import Request, urlopen

from shop.catalog import CATEGORY_IDS, DEPARTMENT_IDS, DEPARTMENTS, CatalogProduct
from dataclasses import fields
from shop.models import Product
from pydantic import ConfigDict, Field

SCHEMA_VERSION = "synthetic-catalog-v1"
GENERATOR_VERSION = "category-facts-v1"

# Category values are product measurements (not package measurements).
PROFILES: dict[str, tuple[tuple[int, int], tuple[float, float, float], tuple[float, float]]] = {
    "Headphones": ((2000, 25000), (19, 17, 8), (.15, .45)),
    "Portable speakers": ((1500, 20000), (18, 8, 8), (.2, 1.8)),
    "Electric kettles": ((1800, 14000), (22, 17, 25), (.6, 1.8)),
    "Table lamps": ((1500, 16000), (20, 20, 38), (.4, 2.5)),
    "Keyboards": ((2000, 20000), (36, 14, 4), (.35, 1.2)),
    "Desk organizers": ((700, 6500), (28, 18, 12), (.2, 1.5)),
    "Yoga mats": ((1500, 12000), (183, 61, .6), (.5, 3.0)),
    "Dumbbells": ((2000, 45000), (28, 15, 15), (1, 30)),
    "Backpacks": ((2500, 25000), (48, 30, 20), (.3, 2.5)),
    "Camping lanterns": ((1500, 15000), (14, 14, 22), (.15, 1.2)),
}

ATTRIBUTE_RULES: dict[str, dict[str, tuple[Any, ...]]] = {
    "Headphones": {"connection": ("wired", "bluetooth"), "battery_hours": (int, 0, 60), "noise_cancelling": (bool,)},
    "Portable speakers": {"connection": ("bluetooth",), "battery_hours": (int, 8, 40), "water_resistance": ("IPX4", "IPX6", "IPX7")},
    "Electric kettles": {"capacity_l": (float, .5, 2), "power_w": (int, 800, 2200)},
    "Table lamps": {"brightness_lm": (int, 200, 1600), "dimmable": (bool,)},
    "Keyboards": {"layout": ("compact", "tenkeyless", "full-size"), "connection": ("USB", "bluetooth")},
    "Desk organizers": {"material": ("bamboo", "steel", "recycled plastic"), "compartments": (int, 2, 16)},
    "Yoga mats": {"material": ("cork", "rubber", "TPE"), "thickness_mm": (int, 3, 12)},
    "Dumbbells": {"adjustable": (bool,), "piece_count": (int, 1, 2), "per_piece_kg": (int, 1, 30)},
    "Backpacks": {"capacity_l": (int, 10, 65), "rain_cover": (bool,)},
    "Camping lanterns": {"brightness_lm": (int, 100, 1500), "runtime_hours": (int, 4, 60)},
}


class GeneratedProduct(Product):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)
    id: str = Field(pattern=r"^(review|load)-[0-9]+-[0-9]{6,}$")
    name: str = Field(min_length=1)
    brand: str = Field(min_length=1)
    currency: Literal["USD"]
    available: bool
    url: str
    image_url: Literal["/static/product-placeholder.svg"]
    measurement_configuration: str = Field(min_length=1)
    price_cents: int = Field(ge=0)
    stock: int = Field(ge=0)
    rating_count: int = Field(ge=0)
    rating_average: float | None = Field(ge=1, le=5)
    length_cm: float = Field(gt=0)
    width_cm: float = Field(gt=0)
    height_cm: float = Field(gt=0)
    weight_kg: float = Field(gt=0)
    description_sentences: list[str] = Field(default_factory=list)


def _validate_product(record: dict[str, Any]) -> None:
    product = GeneratedProduct.model_validate(record)
    category = product.category
    if (category not in PROFILES or product.department not in DEPARTMENTS
            or category not in DEPARTMENTS[product.department]
            or product.category_id != CATEGORY_IDS[category]
            or product.department_id != DEPARTMENT_IDS[product.department]):
        raise ValueError("invalid product hierarchy")
    if (product.available != (product.stock > 0) or (product.rating_count == 0) != (product.rating_average is None)
            or product.url != f"/products/{product.id}"):
        raise ValueError("inconsistent availability, rating, or local link")
    price_range, dimensions, weight_range = PROFILES[category]
    if not price_range[0] <= product.price_cents <= price_range[1]:
        raise ValueError("price outside category range")
    attrs = product.attributes
    rules = ATTRIBUTE_RULES[category]
    if set(attrs) != set(rules):
        raise ValueError("incorrect category attributes")
    for key, rule in rules.items():
        value = attrs[key]
        if rule[0] in (int, float, bool):
            if type(value) is not rule[0] or (len(rule) == 3 and not rule[1] <= value <= rule[2]):
                raise ValueError(f"invalid attribute {key}")
        elif value not in rule:
            raise ValueError(f"invalid attribute {key}")
    for measured, basis in zip((product.length_cm, product.width_cm, product.height_cm), dimensions):
        if category != "Yoga mats" and not round(basis * .8, 2) <= measured <= round(basis * 1.2, 2):
            raise ValueError("dimensions outside category range")
    if category != "Dumbbells" and not weight_range[0] <= product.weight_kg <= weight_range[1]:
        raise ValueError("weight outside category range")
    if category == "Headphones" and ((attrs["connection"] == "wired" and attrs["battery_hours"] != 0)
                                      or (attrs["connection"] == "bluetooth" and float(attrs["battery_hours"]) < 12)):
        raise ValueError("connection and battery disagree")
    if category == "Yoga mats" and product.height_cm != int(attrs["thickness_mm"]) / 10:
        raise ValueError("mat thickness and dimensions disagree")
    if category == "Dumbbells" and product.weight_kg != float(attrs["per_piece_kg"]) * int(attrs["piece_count"]):
        raise ValueError("set weight and piece weights disagree")


def _attributes(category: str, rng: random.Random) -> dict[str, str | int | float | bool]:
    if category == "Headphones":
        connection = rng.choice(["wired", "bluetooth"])
        return {"connection": connection, "battery_hours": rng.randint(12, 60) if connection == "bluetooth" else 0,
                "noise_cancelling": rng.choice([True, False])}
    if category == "Portable speakers":
        return {"connection": "bluetooth", "battery_hours": rng.randint(8, 40), "water_resistance": rng.choice(["IPX4", "IPX6", "IPX7"])}
    if category == "Electric kettles":
        return {"capacity_l": round(rng.randint(5, 20) / 10, 1), "power_w": rng.randrange(800, 2201, 100)}
    if category == "Table lamps":
        return {"brightness_lm": rng.randrange(200, 1601, 50), "dimmable": rng.choice([True, False])}
    if category == "Keyboards":
        return {"layout": rng.choice(["compact", "tenkeyless", "full-size"]), "connection": rng.choice(["USB", "bluetooth"])}
    if category == "Desk organizers":
        return {"material": rng.choice(["bamboo", "steel", "recycled plastic"]), "compartments": rng.randint(2, 16)}
    if category == "Yoga mats":
        return {"material": rng.choice(["cork", "rubber", "TPE"]), "thickness_mm": rng.randint(3, 12)}
    if category == "Dumbbells":
        return {"adjustable": rng.choice([True, False]), "piece_count": rng.choice([1, 2]), "per_piece_kg": rng.randint(1, 30)}
    if category == "Backpacks":
        return {"capacity_l": rng.randint(10, 65), "rain_cover": rng.choice([True, False])}
    return {"brightness_lm": rng.randrange(100, 1501, 50), "runtime_hours": rng.randint(4, 60)}


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def _checksum(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _records(path: Path) -> Iterator[dict[str, Any]]:
    with (gzip.open(path, "rt", encoding="utf-8") if path.suffix == ".gz" else path.open(encoding="utf-8")) as source:
        for line in source:
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError("product must be an object")
            yield record


def generate_facts(output: Path, count: int, seed: int, profile: str) -> None:
    if count < 10 or seed < 0:
        raise ValueError("count must cover all ten categories and seed must be nonnegative")
    rng = random.Random(seed)
    categories = list(CATEGORY_IDS)
    parents = {category: department for department, children in DEPARTMENTS.items() for category in children}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as target:
        for index in range(count):
            category = categories[index % 10]
            department = parents[category]
            price, dimensions, weight = PROFILES[category]
            attrs = _attributes(category, rng)
            length, width, height = [round(d * rng.uniform(.8, 1.2), 2) for d in dimensions]
            mass = round(rng.uniform(*weight), 3)
            configuration = "assembled product"
            if category == "Yoga mats":
                height = int(attrs["thickness_mm"]) / 10
                configuration = "unrolled flat mat"
            if category == "Dumbbells":
                mass = float(attrs["per_piece_kg"]) * int(attrs["piece_count"])
                configuration = "one dumbbell at maximum setting; weight is complete set"
            if category == "Backpacks":
                configuration = "empty backpack, extended"
            product_id = f"{profile}-{seed}-{index + 1:06d}"
            rating_count = 0 if index % 7 == 0 else rng.randint(1, 900)
            stock = 0 if index % 9 == 0 else rng.randint(1, 120)
            facts = {"id": product_id, "name": f"{rng.choice(['Aurora', 'Summit', 'Drift', 'Ember', 'Cloud'])} {category}",
                     "brand": {"Electronics": "Northstar", "Home": "Hearthline", "Office": "Worksmith", "Sports": "Motionary", "Outdoors": "Wayfound"}[department],
                     "department": department, "department_id": DEPARTMENT_IDS[department],
                     "category": category, "category_id": CATEGORY_IDS[category], "description": "",
                     "price_cents": rng.randint(*price), "currency": "USD", "stock": stock, "available": stock > 0,
                     "rating_count": rating_count, "rating_average": round(rng.uniform(1, 5), 1) if rating_count else None,
                     "length_cm": length, "width_cm": width, "height_cm": height, "weight_kg": mass,
                     "measurement_configuration": configuration, "attributes": attrs,
                     "url": f"/products/{product_id}", "image_url": "/static/product-placeholder.svg"}
            target.write(_json(facts) + "\n")
    metadata = {"schema_version": SCHEMA_VERSION, "generator_version": GENERATOR_VERSION,
                "count": count, "seed": seed, "profile": profile, "sha256": _checksum(output)}
    output.with_suffix(".manifest.json").write_text(_json(metadata) + "\n", encoding="utf-8")
    print(_json({"status": "facts_generated", **metadata}))


def _facts_metadata(path: Path) -> dict[str, Any]:
    metadata: dict[str, Any] = json.loads(path.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    if metadata["sha256"] != _checksum(path):
        raise ValueError("facts checksum mismatch")
    if metadata["schema_version"] != SCHEMA_VERSION or metadata["generator_version"] != GENERATOR_VERSION:
        raise ValueError("unsupported facts version")
    seen: set[str] = set()
    for record in _records(path):
        _validate_product(record)
        if record["description"] or record["id"] in seen:
            raise ValueError("facts must have unique IDs and no generated descriptions")
        seen.add(record["id"])
    if len(seen) != metadata["count"]:
        raise ValueError("facts count mismatch")
    return metadata


def _sentences(product: dict[str, Any]) -> dict[str, str]:
    result = {"identity": f"{product['name']} is a fictional product in the {product['category'].lower()} category from {product['brand']}.",
              "dimensions": f"It measures {product['length_cm']:g} by {product['width_cm']:g} by {product['height_cm']:g} cm ({product['measurement_configuration']}).",
              "weight": f"The product weighs {product['weight_kg']:g} kg, excluding packaging."}
    labels = {"battery_hours": "Battery life (hours)", "capacity_l": "Capacity (litres)", "power_w": "Power (watts)",
              "brightness_lm": "Brightness (lumens)", "thickness_mm": "Thickness (mm)", "per_piece_kg": "Weight per piece (kg)",
              "runtime_hours": "Runtime (hours)"}
    for key, value in product["attributes"].items():
        rendered = ("yes" if value else "no") if isinstance(value, bool) else str(value)
        result[key] = f"{labels.get(key, key.replace('_', ' ').capitalize())}: {rendered}."
    return result


def _description(product: dict[str, Any], selected: Any) -> str:
    sentences = _sentences(product)
    if (not isinstance(selected, list) or not selected or any(not isinstance(key, str) for key in selected)
            or len(set(selected)) != len(selected) or set(selected) != set(sentences)):
        raise ValueError("unsupported or missing description claims")
    return " ".join(sentences[key] for key in selected)


def describe(facts: Path, progress: Path, url: str, model: str, mode: str, maximum: int | None) -> None:
    metadata = _facts_metadata(facts) | {"description_model": model, "description_mode": mode}
    progress.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(progress) as db:
        db.execute("CREATE TABLE IF NOT EXISTS metadata (value TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS approved (id TEXT PRIMARY KEY, selected TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS templates (category TEXT PRIMARY KEY, selected TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS rejections (id TEXT, reason TEXT)")
        previous = db.execute("SELECT value FROM metadata").fetchone()
        if previous and previous[0] != _json(metadata):
            raise ValueError("progress belongs to different facts/model/mode")
        if not previous:
            db.execute("INSERT INTO metadata VALUES (?)", (_json(metadata),))
        db.commit()
        completed = 0
        for product in _records(facts):
            if db.execute("SELECT 1 FROM approved WHERE id = ?", (product["id"],)).fetchone():
                continue
            if maximum is not None and completed >= maximum:
                break
            template = db.execute("SELECT selected FROM templates WHERE category = ?", (product["category"],)).fetchone() if mode == "templates" else None
            try:
                if template:
                    selected = json.loads(template[0])
                else:
                    payload = {"model": model, "temperature": 0, "max_tokens": 256,
                               "chat_template_kwargs": {"enable_thinking": False},
                               "response_format": {"type": "json_schema", "json_schema": {"name": "grounded_description", "schema": {
                                   "type": "object", "properties": {"sentences": {"type": "array", "items": {"type": "string", "enum": list(_sentences(product))},
                                                                                  "minItems": len(_sentences(product)), "maxItems": len(_sentences(product))}},
                                   "required": ["sentences"], "additionalProperties": False}}},
                               "messages": [{"role": "system", "content": "Compose a concise English product description using the supplied factual sentences. Return only JSON {\"sentences\":[sentence IDs in reading order]}. Include every supplied sentence ID exactly once. Put identity first, then useful attributes, then measurements. Never invent IDs or claims."},
                                            {"role": "user", "content": _json({"facts": product, "sentences": _sentences(product)})}]}
                    request = Request(url.rstrip("/") + "/v1/chat/completions", data=_json(payload).encode(), headers={"Content-Type": "application/json"})
                    with urlopen(request, timeout=120) as response:
                        answer = json.load(response)
                    content = json.loads(answer["choices"][0]["message"]["content"])
                    if not isinstance(content, dict) or set(content) != {"sentences"}:
                        raise ValueError("unsupported description response")
                    selected = content["sentences"]
                _description(product, selected)
            except (ValueError, KeyError, TypeError) as error:
                db.execute("INSERT INTO rejections VALUES (?, ?)", (product["id"], str(error)))
                db.commit()
                raise ValueError(f"description rejected for {product['id']}: {error}") from error
            db.execute("INSERT INTO approved VALUES (?, ?)", (product["id"], _json(selected)))
            if mode == "templates" and template is None:
                db.execute("INSERT INTO templates VALUES (?, ?)", (product["category"], _json(selected)))
            db.commit()
            completed += 1
            if completed % 100 == 0:
                print(_json({"status": "checkpoint", "newly_approved": completed}), flush=True)
        approved = db.execute("SELECT count(*) FROM approved").fetchone()[0]
    print(_json({"status": "descriptions_complete" if approved == metadata["count"] else "paused", "approved": approved, "count": metadata["count"]}))


def freeze(facts: Path, progress: Path, output: Path, compressed: bool = False) -> None:
    metadata = _facts_metadata(facts)
    with sqlite3.connect(f"file:{progress.as_posix()}?mode=ro", uri=True) as db:
        stored = json.loads(db.execute("SELECT value FROM metadata").fetchone()[0])
        approved = db.execute("SELECT count(*) FROM approved").fetchone()[0]
        if any(stored.get(key) != value for key, value in metadata.items()) or approved != metadata["count"]:
            raise ValueError("descriptions are incomplete or facts changed")
        if output.exists():
            raise ValueError("frozen output already exists")
        staging = output.with_name(output.name + ".partial")
        staging.mkdir(parents=True, exist_ok=True)
        products_path = staging / ("products.jsonl.gz" if compressed else "products.jsonl")
        with products_path.open("wb") as raw:
            target = io.TextIOWrapper(gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) if compressed else raw,
                                      encoding="utf-8", newline="\n")
            for product in _records(facts):
                row = db.execute("SELECT selected FROM approved WHERE id = ?", (product["id"],)).fetchone()
                if row is None:
                    raise ValueError("missing description")
                selected = json.loads(row[0])
                product["description"] = _description(product, selected)
                product["description_sentences"] = selected
                target.write(_json(product) + "\n")
            target.flush()
            if compressed:
                target.close()
        manifest = stored | {"facts_sha256": metadata["sha256"], "sha256": _checksum(products_path), "products_file": products_path.name,
                             "release": f"{metadata['profile']}-{metadata['seed']}-{_checksum(products_path)[:16]}"}
        (staging / "manifest.json").write_text(_json(manifest) + "\n", encoding="utf-8")
        validate_artifact(staging)
        staging.rename(output)
    print(_json({"status": "frozen", **manifest}))


def validate_artifact(artifact: Path) -> dict[str, Any]:
    manifest: dict[str, Any] = json.loads((artifact / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("products_file") not in ("products.jsonl", "products.jsonl.gz"):
        raise ValueError("invalid products filename")
    products_path = artifact / manifest["products_file"]
    if manifest["schema_version"] != SCHEMA_VERSION or manifest["generator_version"] != GENERATOR_VERSION:
        raise ValueError("unsupported artifact version")
    if manifest["sha256"] != _checksum(products_path):
        raise ValueError("artifact checksum mismatch")
    seen: set[str] = set()
    for product in _records(products_path):
        _validate_product(product)
        if product["id"] in seen:
            raise ValueError("duplicate product identity")
        seen.add(product["id"])
        if product["description"] != _description(product, product["description_sentences"]):
            raise ValueError("description contains unsupported claims")
    if len(seen) != manifest["count"]:
        raise ValueError("artifact count mismatch")
    return manifest


def load_artifact(artifact: Path) -> tuple[dict[str, Any], list[CatalogProduct]]:
    """Load validated, frozen input at the ingestion job boundary."""
    manifest = validate_artifact(artifact)
    names = {field.name for field in fields(CatalogProduct)}
    products = [CatalogProduct(**{key: value for key, value in product.items() if key in names})
                for product in _records(artifact / manifest["products_file"])]
    return manifest, products


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    facts = commands.add_parser("facts")
    facts.add_argument("--output", type=Path, required=True)
    facts.add_argument("--count", type=int, default=300)
    facts.add_argument("--seed", type=int, default=42)
    facts.add_argument("--profile", choices=["review", "load"], default="review")
    descriptions = commands.add_parser("describe")
    descriptions.add_argument("--facts", type=Path, required=True)
    descriptions.add_argument("--progress", type=Path, required=True)
    descriptions.add_argument("--url", default=os.environ.get("VLLM_URL", "http://127.0.0.1:8000"))
    descriptions.add_argument("--model", default=os.environ.get("VLLM_MODEL", "Qwen/Qwen3-1.7B"))
    descriptions.add_argument("--mode", choices=["individual", "templates"], default="individual")
    descriptions.add_argument("--max-products", type=int)
    frozen = commands.add_parser("freeze")
    frozen.add_argument("--facts", type=Path, required=True)
    frozen.add_argument("--progress", type=Path, required=True)
    frozen.add_argument("--output", type=Path, required=True)
    frozen.add_argument("--gzip", action="store_true")
    validation = commands.add_parser("validate")
    validation.add_argument("--artifact", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "facts":
        generate_facts(args.output, args.count, args.seed, args.profile)
    elif args.command == "describe":
        describe(args.facts, args.progress, args.url, args.model, args.mode, args.max_products)
    elif args.command == "freeze":
        freeze(args.facts, args.progress, args.output, args.gzip)
    else:
        print(_json({"status": "valid", **validate_artifact(args.artifact)}))


if __name__ == "__main__":
    main()
