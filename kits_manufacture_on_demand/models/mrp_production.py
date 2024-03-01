from odoo import fields, models, api

class mrp_production(models.Model):
    _inherit = 'mrp.production'

    sale_order_id = fields.Many2one('sale.order','Source Document')

    @api.model
    def create(self,vals):

        res = super(mrp_production,self).create(vals)
    
        return res