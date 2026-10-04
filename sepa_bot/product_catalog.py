"""Catalog and matching rules for the basket products tracked by the bot."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CatalogItem:
    key: str
    category: str
    option: int | None
    label: str
    aliases: tuple[str, ...]
    unit: str
    monthly_quantity: float | None = None


def _item(
    key: str,
    category: str,
    option: int | None,
    label: str,
    aliases: tuple[str, ...],
    unit: str = "kg",
    monthly_quantity: float | None = None,
) -> CatalogItem:
    return CatalogItem(key, category, option, label, aliases, unit, monthly_quantity)


CATALOG = (
    _item("pan_frances", "Pan", 1, "Pan francés / flautita", ("PAN FRANCES|FLAUTITA",), "kg"),
    _item("pan_lactal", "Pan", 2, "Pan de mesa / lactal Fargo", ("FARGO", "PAN LACTAL", "PAN DE MESA"), "kg"),
    _item("galletitas_agua_criollitas", "Galletitas de agua", 1, "Criollitas", ("CRIOLLITAS",)),
    _item("galletitas_agua_express", "Galletitas de agua", 2, "Express", ("EXPRESS",)),
    _item("galletitas_dulces_vocacion", "Galletitas dulces", 1, "Vocación", ("VOCACION",)),
    _item("galletitas_dulces_mana", "Galletitas dulces", 2, "Maná vainilla", ("MANA", "VAINILLA")),
    _item("arroz_gallo_oro", "Arroz", 1, "Gallo Oro", ("GALLO ORO",)),
    _item("arroz_lucchetti", "Arroz", 2, "Lucchetti largo fino", ("LUCCHETTI", "ARROZ")),
    _item("harina_canuelas", "Harina de trigo", 1, "Cañuelas 000", ("CANUELAS", "000")),
    _item("harina_favorita", "Harina de trigo", 2, "Favorita 000", ("FAVORITA", "000")),
    _item("fideos_matarazzo", "Fideos", 1, "Matarazzo", ("MATARAZZO",)),
    _item("fideos_lucchetti", "Fideos", 2, "Lucchetti", ("LUCCHETTI", "FIDEOS")),
    _item("papa_negra", "Papa", 1, "Papa negra seleccionada", ("PAPA NEGRA",)),
    _item("papa_blanca", "Papa", 2, "Papa blanca lavada", ("PAPA BLANCA",)),
    _item("batata_colorada", "Batata", 1, "Batata colorada / boniato", ("BATATA COLORADA", "BONIATO"), "kg"),
    _item("batata_blanca", "Batata", 2, "Batata blanca", ("BATATA BLANCA",), "kg"),
    _item("azucar_ledesma", "Azúcar", 1, "Ledesma clásica", ("LEDESMA", "AZUCAR"), "kg"),
    _item("azucar_chango", "Azúcar", 2, "Chango común tipo A", ("CHANGO", "AZUCAR"), "kg"),
    _item("dulce_leche_serenisima", "Dulces", 1, "Dulce de leche La Serenísima", ("DULCE DE LECHE", "SERENISIMA")),
    _item("dulce_batata_arcor", "Dulces", 1, "Dulce de batata Arcor", ("DULCE DE BATATA", "ARCOR")),
    _item("dulce_leche_ilolay", "Dulces", 2, "Dulce de leche Ilolay", ("DULCE DE LECHE", "ILOLAY")),
    _item("mermelada_campagnola", "Dulces", 2, "Mermelada BC La Campagnola", ("MERMELADA", "CAMPAGNOLA")),
    _item("lentejas_arcor", "Legumbres secas", 1, "Lentejas Arcor", ("LENTEJAS", "ARCOR")),
    _item("lentejas_ciudad_lago", "Legumbres secas", 2, "Lentejas Ciudad del Lago", ("LENTEJAS", "CIUDAD DEL LAGO")),
    _item("lentejas_lucchetti", "Legumbres secas", 2, "Lentejas Lucchetti", ("LENTEJAS", "LUCCHETTI")),
    _item("cebolla", "Hortalizas", 1, "Cebolla", ("CEBOLLA",), "kg"),
    _item("lechuga", "Hortalizas", 1, "Lechuga", ("LECHUGA",), "kg"),
    _item("zapallo", "Hortalizas", 1, "Zapallo anco", ("ZAPALLO",), "kg"),
    _item("zanahoria", "Hortalizas", 1, "Zanahoria", ("ZANAHORIA",), "kg"),
    _item("acelga", "Hortalizas", 1, "Acelga", ("ACELGA",), "kg"),
    _item("tomate_fresco", "Hortalizas", 1, "Tomate fresco", ("TOMATE", "FRESCO|PERITA"), "kg"),
    _item("tomate_envasado_noel", "Hortalizas", 2, "Tomate triturado Noel", ("TOMATE", "NOEL"), "kg"),
    _item("tomate_envasado_de_la_huerta", "Hortalizas", 2, "Tomate triturado De la Huerta", ("TOMATE", "DE LA HUERTA"), "kg"),
    _item("manzana_delicious", "Frutas", 1, "Manzana roja Delicious", ("MANZANA", "DELICIOUS"), "kg"),
    _item("banana_ecuatoriana", "Frutas", 1, "Banana comercial ecuatoriana", ("BANANA", "ECUATORIANA"), "kg"),
    _item("naranja_jugo", "Frutas", 2, "Naranja de jugo", ("NARANJA",), "kg"),
    _item("pera_williams", "Frutas", 2, "Pera Williams", ("PERA", "WILLIAMS"), "kg"),
    _item("mandarina", "Frutas", None, "Mandarina", ("MANDARINA",), "kg"),
    _item("asado", "Carnes", 2, "Asado", ("ASADO",), "kg"),
    _item("carne_picada", "Carnes", 2, "Carne picada", ("CARNE PICADA", "PICADA ESPECIAL"), "kg"),
    _item("paleta_vacuna", "Carnes", 2, "Paleta vacuna", ("PALETA",), "kg"),
    _item("pollo_entero", "Carnes", 1, "Pollo entero", ("POLLO ENTERO", "GRANJA TRES ARROYOS"), "kg"),
    _item("pescado", "Carnes", 2, "Pescado", ("PESCADO",), "kg"),
    _item("higado", "Menudencias", 1, "Hígado vacuno fresco", ("HIGADO",), "kg"),
    _item("paleta_cocida", "Fiambres", 1, "Paleta cocida Paladini", ("PALETA COCIDA", "PALADINI"), "kg"),
    _item("salame_milan", "Fiambres", 2, "Salame tipo Milán", ("SALAME", "MILAN"), "kg"),
    _item("huevos_blancos", "Huevos", 1, "Huevos blancos grandes", ("HUEVOS", "BLANCOS"), "unidad", 30),
    _item("huevos_colorados", "Huevos", 2, "Huevos colorados", ("HUEVOS", "COLORADOS"), "unidad", 30),
    _item("leche_serenisima", "Leche", 1, "La Serenísima clásica", ("LECHE", "SERENISIMA"), "litro"),
    _item("leche_tregar", "Leche", 2, "Tregar", ("LECHE", "TREGAR"), "litro"),
    _item("queso_la_paulina", "Queso", 1, "Queso cremoso La Paulina", ("QUESO", "PAULINA"), "kg"),
    _item("queso_cremon", "Queso", 2, "Queso Cremón", ("QUESO", "CREMON"), "kg"),
    _item("yogur_yogurisimo", "Yogur", 1, "Yogurísimo", ("YOGURISIMO",), "litro"),
    _item("yogur_ilolay", "Yogur", 2, "Ilolay", ("YOGUR", "ILOLAY"), "litro"),
    _item("manteca_serenisima", "Manteca", 1, "Manteca La Serenísima", ("MANTECA", "SERENISIMA"), "kg"),
    _item("manteca_ilolay", "Manteca", 2, "Manteca Ilolay / Primer Premio", ("MANTECA", "ILOLAY", "PRIMER PREMIO"), "kg"),
    _item("aceite_natura", "Aceite", 1, "Aceite Natura", ("ACEITE", "NATURA"), "litro"),
    _item("aceite_cocinero", "Aceite", 2, "Aceite Cocinero", ("ACEITE", "COCINERO"), "litro"),
    _item("gaseosa_manaos", "Bebidas no alcohólicas", 1, "Manaos", ("MANAOS",), "litro"),
    _item("gaseosa_cunnington", "Bebidas no alcohólicas", 1, "Cunnington", ("CUNNINGTON",), "litro"),
    _item("soda_ivess", "Bebidas no alcohólicas", 2, "Soda Ivess", ("SODA", "IVESS"), "litro"),
    _item("soda_cindor", "Bebidas no alcohólicas", 2, "Soda Cindor", ("SODA", "CINDOR"), "litro"),
    _item("jugo_tang", "Bebidas no alcohólicas", 2, "Jugo Tang", ("TANG",), "litro"),
    _item("jugo_bc", "Bebidas no alcohólicas", 2, "Jugo BC", ("JUGO", "BC"), "litro"),
    _item("cerveza_quilmes", "Bebidas alcohólicas", 1, "Cerveza Quilmes", ("CERVEZA", "QUILMES"), "litro"),
    _item("cerveza_brahma", "Bebidas alcohólicas", 1, "Cerveza Brahma", ("CERVEZA", "BRAHMA"), "litro"),
    _item("vino_toro", "Bebidas alcohólicas", 2, "Vino Toro", ("VINO", "TORO"), "litro"),
    _item("vino_termidor", "Bebidas alcohólicas", 2, "Vino Termidor", ("VINO", "TERMIDOR"), "litro"),
    _item("sal_dos_anclas", "Sal fina", 1, "Dos Anclas", ("SAL", "DOS ANCLAS"), "kg"),
    _item("sal_celusal", "Sal fina", 2, "Celusal", ("SAL", "CELUSAL"), "kg"),
    _item("mayonesa_hellmanns", "Condimentos", 1, "Mayonesa Hellmann's", ("MAYONESA", "HELLMANNS"), "kg"),
    _item("caldos_knorr", "Condimentos", 2, "Caldos Knorr", ("CALDO", "KNORR")),
    _item("mayonesa_natura", "Condimentos", 2, "Mayonesa Natura", ("MAYONESA", "NATURA"), "kg"),
    _item("vinagre_menoyo", "Vinagre", 1, "Vinagre Menoyo", ("VINAGRE", "MENOYO"), "litro"),
    _item("vinagre_dos_anclas", "Vinagre", 2, "Vinagre Dos Anclas", ("VINAGRE", "DOS ANCLAS"), "litro"),
    _item("cafe_dolca", "Café", 1, "Nescafé Dolca", ("DOLCA",), "kg"),
    _item("cafe_arlistan", "Café", 2, "Arlistán", ("ARLISTAN",), "kg"),
    _item("yerba_playadito", "Yerba", 1, "Playadito", ("PLAYADITO",), "kg"),
    _item("yerba_taragui", "Yerba", 2, "Taragüí", ("TARAGUI",), "kg"),
)


def normalizar_texto(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.upper().split())


def texto_producto(row: dict[str, Any]) -> str:
    fields = (
        "productos_descripcion", "descripcion", "producto_descripcion",
        "nombre_producto", "productos_nombre", "nombre", "marca",
        "productos_marca", "ean", "codigo_barras",
    )
    return normalizar_texto(" ".join(str(row.get(field) or "") for field in fields))


def encontrar_items(row: dict[str, Any]) -> list[CatalogItem]:
    text = texto_producto(row)
    return [
        item for item in CATALOG
        if all(
            any(normalizar_texto(alternative) in text for alternative in alias_group.split("|"))
            for alias_group in item.aliases
        )
    ]