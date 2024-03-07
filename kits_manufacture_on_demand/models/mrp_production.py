from odoo import fields, models, api

class mrp_production(models.Model):
    _inherit = 'mrp.production'

    sale_order_id = fields.Many2one('sale.order','Source Document')
    sale_order_line_ids = fields.One2many('sale.order.line','production_id',string='Sale Order Line')

