import unittest

from sepa_bot.product_catalog import encontrar_items, normalizar_texto


class ProductCatalogTests(unittest.TestCase):
    def test_normaliza_tildes_y_mayusculas(self):
        self.assertEqual(normalizar_texto("Taragüí Clásica"), "TARAGUI CLASICA")

    def test_reconoce_marca_y_producto(self):
        items = encontrar_items({"productos_descripcion": "Azúcar común tipo A Chango 1 kg"})

        self.assertEqual([item.key for item in items], ["azucar_chango"])

    def test_requiere_ambos_terminos_de_la_regla(self):
        items = encontrar_items({"productos_descripcion": "Chango yerba mate"})

        self.assertEqual(items, [])


if __name__ == "__main__":
    unittest.main()