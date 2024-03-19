from odoo import fields, models

class sale_order_line(models.Model):
    _inherit = 'sale.order.line'

    production_id = fields.Many2one('mrp.production', string='Manufacture Order')