"""The small frozen catalog used by the first retrieval demonstration."""
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CatalogProduct:
    id: str
    name: str
    brand: str
    description: str
    department: str
    category: str
    price_cents: int
    stock: int
    rating_average: float
    rating_count: int
    length_cm: float
    width_cm: float
    height_cm: float
    weight_kg: float
    attributes: dict[str, str | int | float | bool]

    @property
    def department_id(self) -> str:
        return DEPARTMENT_IDS[self.department]

    @property
    def category_id(self) -> str:
        return CATEGORY_IDS[self.category]

    def facts(self) -> dict[str, Any]:
        facts = asdict(self)
        facts["department_id"] = self.department_id
        facts["category_id"] = self.category_id
        return facts

    def text(self) -> str:
        return f"{self.name} {self.brand} {self.department} {self.category} {self.description} {' '.join(map(str, self.attributes.values()))}"


CATALOG: tuple[CatalogProduct, ...] = (
    CatalogProduct("aurora-headphones", "Aurora Headphones", "Northstar", "Fictional wireless over-ear headphones with comfortable memory foam and active noise reduction.", "Electronics", "Headphones", 8999, 18, 4.4, 61, 18, 16, 8, .31, {"connection": "bluetooth", "battery": "32 hours"}),
    CatalogProduct("echo-speaker", "Echo Portable Speaker", "Northstar", "Fictional compact waterproof speaker for picnics and small rooms.", "Electronics", "Portable speakers", 5499, 25, 4.2, 44, 18, 7, 7, .52, {"waterproof": "IPX6", "battery": "16 hours"}),
    CatalogProduct("ember-kettle", "Ember Electric Kettle", "Hearthline", "Fictional fast boiling electric kettle with a clear water gauge.", "Home", "Electric kettles", 4299, 12, 4.5, 37, 22, 16, 24, .9, {"capacity": "1.7 litres", "power": "1500 W"}),
    CatalogProduct("glow-lamp", "Glow Table Lamp", "Hearthline", "Fictional warm LED table lamp with adjustable brightness for a desk or bedside table.", "Home", "Table lamps", 3299, 31, 4.1, 19, 18, 18, 32, .8, {"bulb": "LED", "dimming": "three levels"}),
    CatalogProduct("keyforge-keyboard", "Keyforge Keyboard", "Worksmith", "Fictional quiet mechanical keyboard with a compact layout for daily typing.", "Office", "Keyboards", 7499, 9, 4.7, 82, 36, 13, 4, .74, {"layout": "compact", "switches": "quiet tactile"}),
    CatalogProduct("tidy-desk", "Tidy Desk Organizer", "Worksmith", "Fictional modular organizer with compartments for stationery and small accessories.", "Office", "Desk organizers", 1999, 45, 4.0, 13, 28, 18, 12, .44, {"material": "recycled plastic", "compartments": "six"}),
    CatalogProduct("cloud-mat", "Cloud Yoga Mat", "Motionary", "Fictional cushioned yoga mat with a textured non-slip surface.", "Sports", "Yoga mats", 3899, 22, 4.6, 52, 183, 61, .6, 2.1, {"thickness": "6 mm", "surface": "non-slip"}),
    CatalogProduct("ironbell-dumbbell", "Ironbell Dumbbells", "Motionary", "Fictional pair of balanced coated dumbbells for strength exercises at home.", "Sports", "Dumbbells", 4599, 16, 4.3, 29, 22, 10, 10, 5.0, {"set": "two", "per dumbbell": "5 kg"}),
    CatalogProduct("summit-pack", "Summit Backpack", "Wayfound", "Fictional day backpack with padded storage and a rain cover for short hikes.", "Outdoors", "Backpacks", 6799, 14, 4.8, 73, 48, 30, 18, .82, {"capacity": "24 litres", "cover": "included"}),
    CatalogProduct("nightbeam-lantern", "Nightbeam Camping Lantern", "Wayfound", "Fictional rechargeable lantern with a soft light mode for campsites.", "Outdoors", "Camping lanterns", 2999, 27, 4.3, 35, 14, 14, 22, .38, {"battery": "20 hours", "modes": "three"}),
)

BY_ID = {product.id: product for product in CATALOG}
DEPARTMENT_IDS = {"Electronics": "dept-electronics", "Home": "dept-home", "Office": "dept-office", "Sports": "dept-sports", "Outdoors": "dept-outdoors"}
CATEGORY_IDS = {"Headphones": "cat-headphones", "Portable speakers": "cat-portable-speakers", "Electric kettles": "cat-electric-kettles", "Table lamps": "cat-table-lamps", "Keyboards": "cat-keyboards", "Desk organizers": "cat-desk-organizers", "Yoga mats": "cat-yoga-mats", "Dumbbells": "cat-dumbbells", "Backpacks": "cat-backpacks", "Camping lanterns": "cat-camping-lanterns"}
DEPARTMENTS = {"Electronics": {"Headphones", "Portable speakers"}, "Home": {"Electric kettles", "Table lamps"}, "Office": {"Keyboards", "Desk organizers"}, "Sports": {"Yoga mats", "Dumbbells"}, "Outdoors": {"Backpacks", "Camping lanterns"}}
