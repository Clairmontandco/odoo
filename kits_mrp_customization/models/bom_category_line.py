from odoo import _, api, fields, models, tools

class BomCategoryLine(models.Model):
    _name = 'bom.category.line'

    categ_id = fields.Many2one('product.category','Category')

    product_id = fields.Many2one('product.product','Component')
    product_qty = fields.Float('Quantity')
    product_uom_id = fields.Many2one('uom.uom','Product Unit of Measure',related='product_id.uom_id')
