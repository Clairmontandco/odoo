from odoo import models, fields, api

COLUMN_SELECTION = [('title', 'Product Title',),
                    ('type', 'Product Type'),
                    ('vendor', 'Product Vendor'),
                    ('variant_title', 'Variant Title'),
                    ('variant_compare_at_price', 'Compare at Price'),
                    ('variant_weight', 'Weight'),
                    ('variant_inventory', 'Inventory Stock'),
                    ('variant_price', 'Price'),
                    ('product_taxonomy_node_id', 'Product Category'),
                    ('tag', 'Tag')]

RELATION_SELECTION = [('greater_than', 'greater_than'),
                      ('less_than', 'less_than'),
                      ('equals', 'equals'),
                      ('is_set', 'is_set'),
                      ('is_not_set', 'is_not_set'),
                      ('not_equals', 'not_equals'),
                      ('starts_with', 'starts_with'),
                      ('ends_with', 'ends_with'),
                      ('contains', 'contains'),
                      ('not_contains', 'not_contains')]


class ShopifyCollectionCondition(models.Model):
    _name = "shopify.collection.condition.ts"
    _description = "Shopify Collection Condition"

    column = fields.Selection(COLUMN_SELECTION, "Column",
                              help="The property of a product being used to populate the smart collection.")
    relation = fields.Selection(RELATION_SELECTION, "Relation",
                                help="The relationship between the column choice, and the condition")
    condition = fields.Char("Condition", help="Select products for a smart collection using a condition. "
                                              "Values are either strings or numbers, depending on the relation value.")
    shopify_collection_id = fields.Many2one("shopify.collection.ts", "Collection ID")

    def action_redirect_product_taxonomy(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'target': 'new',
            'url': 'https://help.shopify.com/txt/product_taxonomy/en.txt',
        }

    @api.onchange('column', 'relation')
    def _onchange_column_relation(self):
        if self.column == 'product_taxonomy_node_id' and self.relation != 'equals':
            self.relation = 'equals'
        if self.column == 'variant_compare_at_price' and self.relation in ['is_set', 'is_not_set']:
            self.condition = ''
